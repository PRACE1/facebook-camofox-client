"""Auth guard."""
from __future__ import annotations
from pydantic import BaseModel

class AuthGuardResult(BaseModel):
    authenticated: bool
    requires_action: str | None = None

class AuthGuard:
    async def validate(self, account, session) -> AuthGuardResult:
        return AuthGuardResult(authenticated=True)