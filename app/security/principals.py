from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Identity resolved from a verified API key.

    Carries just enough information for route handlers and audit logging
    to make authorization decisions without touching the database again.
    """

    client_id: str
    display_name: str | None
    role: str
    key_id: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
