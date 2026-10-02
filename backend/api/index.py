"""Vercel entrypoint: every request is routed here (see vercel.json)."""

from app.main import app

__all__ = ["app"]
