"""Auth guard with explicit state boundaries — not a boolean stub."""
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel


class AuthState(str, Enum):
    authenticated = "authenticated"
    auth_required = "auth_required"
    session_expired = "session_expired"
    surface_unavailable = "surface_unavailable"


class AuthGuardResult(BaseModel):
    state: AuthState
    requires_action: str | None = None

    @property
    def authenticated(self) -> bool:
        return self.state == AuthState.authenticated


class AuthGuard:
    """Validates session state after cookies are loaded and before surface opens.

    Must never receive a Camofox object — it operates on the session's reported
    DOM state only.
    """

    async def validate(self, page_title: str, page_url: str) -> AuthGuardResult:
        """Inspect the landed page to determine real auth state."""
        title_lower = page_title.lower()
        url_lower = page_url.lower()

        if "log in" in title_lower or "login" in url_lower:
            return AuthGuardResult(
                state=AuthState.auth_required,
                requires_action="supply_cookies",
            )
        if "session expired" in title_lower or "checkpoint" in url_lower:
            return AuthGuardResult(
                state=AuthState.session_expired,
                requires_action="refresh_cookies",
            )
        if "unavailable" in title_lower or "content not found" in title_lower:
            return AuthGuardResult(state=AuthState.surface_unavailable)

        return AuthGuardResult(state=AuthState.authenticated)