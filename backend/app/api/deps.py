"""Shared FastAPI dependencies."""

import logging
import uuid
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_auth.errors import AuthError

from app.errors import AuthenticationError
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# auto_error=False so a missing header goes through our own 401 handling.
bearer_scheme = HTTPBearer(auto_error=False, description="Supabase access token (JWT)")


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str | None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """Verify the Supabase access token and return the authenticated user.

    The token is validated by Supabase Auth itself (signature, expiry,
    revocation), so the backend never trusts a user id sent by the client.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError()

    try:
        response = get_supabase().auth.get_user(credentials.credentials)
    except AuthError as exc:
        logger.info("Rejected access token: %s", exc.code or "invalid")
        raise AuthenticationError("Invalid or expired session.") from exc

    if response is None or response.user is None:
        raise AuthenticationError("Invalid or expired session.")

    return CurrentUser(id=uuid.UUID(response.user.id), email=response.user.email)
