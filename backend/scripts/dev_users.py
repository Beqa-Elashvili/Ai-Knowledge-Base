"""Helpers for creating confirmed Supabase users and access tokens in dev.

Uses the Supabase Admin API (service key), so it must only run locally.
A fresh client is created for each sign-in so the shared application client
never picks up a user session.
"""

from supabase import create_client

from app.config import get_settings
from app.supabase_client import get_supabase


def _fresh_client():
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key.get_secret_value())


def find_user_id(email: str) -> str | None:
    page = 1
    while True:
        users = get_supabase().auth.admin.list_users(page=page, per_page=200)
        for user in users:
            if (user.email or "").lower() == email.lower():
                return user.id
        if len(users) < 200:
            return None
        page += 1


def ensure_confirmed_user(email: str, password: str) -> str:
    """Create the user with a confirmed email if needed; return the user id."""
    existing = find_user_id(email)
    if existing:
        get_supabase().auth.admin.update_user_by_id(existing, {"password": password, "email_confirm": True})
        return existing
    response = get_supabase().auth.admin.create_user({"email": email, "password": password, "email_confirm": True})
    return response.user.id


def sign_in(email: str, password: str) -> str:
    """Return an access token (JWT) for the user."""
    session = _fresh_client().auth.sign_in_with_password({"email": email, "password": password}).session
    if session is None:
        raise RuntimeError("Sign-in did not return a session")
    return session.access_token


def delete_user(user_id: str) -> None:
    get_supabase().auth.admin.delete_user(user_id)
