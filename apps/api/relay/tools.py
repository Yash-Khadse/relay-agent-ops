"""Only registered tools are callable; agents have no shell or arbitrary filesystem access."""

import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from .db import digest


@dataclass(frozen=True)
class ToolSpec:
    name: str
    roles: frozenset[str]
    requires_approval: bool = False


REGISTRY = {
    name: ToolSpec(name, frozenset(roles), approval)
    for name, roles, approval in [
        ("retrieve_documents", ["research"], False),
        ("structured_data", ["research", "analysis"], False),
        ("calculate", ["analysis"], False),
        ("report", ["writer"], False),
        ("record_update", ["execution"], True),
        ("ticket_update", ["execution"], True),
        ("export", ["execution"], True),
        ("workflow_status", ["supervisor"], False),
    ]
}


def authorize_tool(name: str, agent: str, approved: bool = False):
    spec = REGISTRY.get(name)
    if not spec or agent not in spec.roles or (spec.requires_approval and not approved):
        raise PermissionError("Tool invocation is outside permission scope")


def calculate(expression: str) -> float:
    if len(expression) > 100:
        raise ValueError("Expression too long")
    ops: dict[type, Callable] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            numeric = float(cast(int | float, node.value))
            if abs(numeric) > 1e12:
                raise ValueError("Operand too large")
            return numeric
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            result = ops[type(node.op)](visit(node.left), visit(node.right))
            if abs(result) > 1e12:
                raise ValueError("Result too large")
            return result
        raise ValueError("Only bounded arithmetic is supported")

    return float(visit(ast.parse(expression, mode="eval").body))


def validate_evidence(result, sources: list[dict]):
    originals = {s["id"]: s["content"] for s in sources}
    for evidence in result.evidence:
        if (
            evidence.source_id not in originals
            or evidence.quote not in originals[evidence.source_id]
        ):
            raise ValueError("Research returned an unknown source or unsupported quotation")


def artifact_hash(content: str) -> str:
    return digest(content)
