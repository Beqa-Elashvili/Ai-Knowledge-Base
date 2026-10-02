"""Supabase client (service role) for Storage, Auth verification and RPC.

The service role key bypasses Row Level Security, so this client must only
ever be used server-side, and every query made with it must be scoped to the
authenticated user explicitly.
"""

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import TypeVar

import httpx
from supabase import Client, create_client

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    logger.info("Creating Supabase client for %s", settings.supabase_url)
    return create_client(settings.supabase_url, settings.supabase_service_key.get_secret_value())


def with_reconnect(call: Callable[[], T], what: str) -> T:
    """Run a Supabase call, retrying once if the connection failed.

    The client keeps idle HTTP connections open; Supabase closes them after a
    while, and the next request on such a connection fails with "Server
    disconnected" before reaching the server. httpx drops the broken
    connection, so one retry runs on a fresh one. A second failure is
    raised (httpx.TransportError) for the caller to turn into a 502.
    """
    try:
        return call()
    except httpx.TransportError as exc:
        logger.warning("%s: %s (%s); retrying once", what, type(exc).__name__, exc)
        return call()


def check_supabase() -> dict[str, list[str] | bool]:
    """Connectivity check: authenticate with the service key and list buckets.

    Raises if the documents bucket is missing, so readiness reports an error
    until the storage migration has been applied.
    """
    buckets = [bucket.name for bucket in get_supabase().storage.list_buckets()]
    bucket_name = get_settings().storage_bucket
    if bucket_name not in buckets:
        raise RuntimeError(f"Storage bucket '{bucket_name}' does not exist")
    return {"buckets": buckets, "documents_bucket": True}
