"""Opt-in MCP retrieval. Registration is administrator code/config, never remote discovery."""

import asyncio
import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class MCPServer:
    name: str
    url: str
    read_tools: frozenset[str]
    workspaces: frozenset[str]
    credential_env: str = ""
    timeout_seconds: int = 20


class MCPRegistry:
    def __init__(self, servers: list[MCPServer]):
        self.servers = {server.name: server for server in servers}

    def authorize(self, name: str, tool: str, workspace_id: str, role: str) -> MCPServer:
        server = self.servers.get(name)
        if (
            not server
            or tool not in server.read_tools
            or workspace_id not in server.workspaces
            or role not in {"owner", "admin", "operator"}
        ):
            raise PermissionError("MCP tool is outside registered workspace permissions")
        parsed = urlsplit(server.url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError("MCP servers require an administrator-approved HTTPS URL")
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(item[4][0]).is_global for item in addresses
        ):
            raise PermissionError("Private and special-address MCP endpoints are prohibited")
        return server

    async def retrieve(
        self, name: str, tool: str, arguments: dict, workspace_id: str, role: str
    ) -> dict:
        server = self.authorize(name, tool, workspace_id, role)
        if len(json.dumps(arguments).encode()) > 8000:
            raise ValueError("MCP arguments exceed limit")
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        headers = {}
        if server.credential_env:
            credential = os.environ.get(server.credential_env)
            if not credential:
                raise ValueError("Registered MCP credential unavailable")
            headers["Authorization"] = f"Bearer {credential}"
        async with asyncio.timeout(server.timeout_seconds):
            async with httpx.AsyncClient(
                headers=headers,
                timeout=server.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with streamable_http_client(server.url, http_client=client) as (
                    read,
                    write,
                    _,
                ):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool, arguments)
        if result.isError:
            raise RuntimeError("Registered MCP tool reported an error")
        text = "\n".join(block.text for block in result.content if block.type == "text")
        if len(text.encode()) > 24000:
            raise ValueError("MCP output exceeds source limit")
        # Caller may save this as an untrusted source; never dispatch returned tool instructions.
        return {"server": name, "tool": tool, "content": text, "trusted": False}
