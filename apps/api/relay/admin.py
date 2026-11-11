"""Local administrator CLI. Requires database credentials; never exposed as a public API."""

import argparse
import secrets

from sqlalchemy import delete, select

from .auth import PERMISSIONS
from .config import Settings
from .db import AccessCode, Database, LoginSession, User, Workspace, digest, now


def provision(db: Database, name: str, role: str = "owner", workspace_id: str | None = None):
    if role not in PERMISSIONS or not 1 <= len(name) <= 120:
        raise ValueError("Invalid name or role")
    with db.transaction() as session:
        workspace = (
            session.get(Workspace, workspace_id)
            if workspace_id
            else Workspace(name="Private workspace")
        )
        if workspace is None or workspace.expires_at:
            raise ValueError("Choose an existing permanent workspace")
        session.add(workspace)
        session.flush()
        current = User(name=name, role=role, workspace_id=workspace.id)
        session.add(current)
        session.flush()
        code = secrets.token_urlsafe(48)
        session.add(
            AccessCode(token_hash=digest(code), user_id=current.id, expires_at=now() + 3600)
        )
        return {"user_id": current.id, "workspace_id": workspace.id, "access_code": code}


def main():
    parser = argparse.ArgumentParser(description="Relay local administrator")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user")
    create.add_argument("--name", required=True)
    create.add_argument("--role", choices=PERMISSIONS, default="owner")
    create.add_argument("--workspace")
    code = commands.add_parser("issue-code")
    code.add_argument("--user", required=True)
    revoke = commands.add_parser("revoke")
    revoke.add_argument("--user", required=True)
    args = parser.parse_args()
    db = Database(Settings().database_url)
    db.initialize()
    if args.command == "create-user":
        result = provision(db, args.name, args.role, args.workspace)
        for key, value in result.items():
            print(f"{key}: {value}")
    else:
        with db.transaction() as session:
            current = session.scalar(select(User).where(User.id == args.user))
            if not current:
                parser.error("Unknown user")
            session.execute(delete(AccessCode).where(AccessCode.user_id == args.user))
            if args.command == "revoke":
                session.execute(delete(LoginSession).where(LoginSession.user_id == args.user))
                print("Sessions and outstanding access codes revoked")
            else:
                value = secrets.token_urlsafe(48)
                session.add(
                    AccessCode(token_hash=digest(value), user_id=args.user, expires_at=now() + 3600)
                )
                print(f"access_code: {value}")
    db.engine.dispose()


if __name__ == "__main__":
    main()
