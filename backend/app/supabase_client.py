"""Supabase client (service role) for Storage, Auth verification and RPC.

The service role key bypasses Row Level Security, so this client must only
ever be used server-side, and every query made with it must be scoped to the
authenticated user explicitly.
"""

import logging
from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    logger.info("Creating Supabase client for %s", settings.supabase_url)
    return create_client(settings.supabase_url, settings.supabase_service_key.get_secret_value())


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
