import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .db import LoginSession, RateBucket, User, Workspace, digest, now

PERMISSIONS = {
    "owner": {"read", "run", "approve", "manage"},
    "admin": {"read", "run", "approve", "manage"},
    "operator": {"read", "run"},
    "approver": {"read", "approve"},
    "viewer": {"read"},
}


def user(request: Request) -> User:
    token = request.cookies.get("relay_session", "")
    if not token:
        raise HTTPException(401, "Sign in to continue")
    with request.app.state.db.sessions() as session:
        record = session.get(LoginSession, digest(token))
        if not record or record.expires_at <= now():
            raise HTTPException(401, "Session expired; start a new demo workspace")
        current = session.get(User, record.user_id)
        workspace = session.get(Workspace, current.workspace_id)
        if workspace.expires_at and workspace.expires_at <= now():
            raise HTTPException(401, "Workspace expired")
        return current


def require(permission: str):
    def dependency(current: User = Depends(user)):
        if permission not in PERMISSIONS.get(current.role, set()):
            raise HTTPException(403, "Your role does not permit this operation")
        return current

    return dependency


def issue_session(session, current: User, hours: int) -> str:
    token = secrets.token_urlsafe(48)
    session.add(
        LoginSession(token_hash=digest(token), user_id=current.id, expires_at=now() + hours * 3600)
    )
    return token


def rate_limit(session, key: str, limit: int, seconds: int):
    bucket_key = f"{key}:{int(now() // seconds)}"
    bucket = session.scalar(
        select(RateBucket).where(RateBucket.key == bucket_key).with_for_update()
    )
    if not bucket:
        bucket = RateBucket(key=bucket_key, count=0, expires_at=now() + seconds)
        session.add(bucket)
    if bucket.count >= limit:
        raise HTTPException(429, "Resource limit reached; try again later")
    bucket.count += 1
