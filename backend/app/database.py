"""SQLAlchemy engine/session for Supabase PostgreSQL."""

import logging
from collections.abc import Iterator
from functools import lru_cache
from urllib.parse import unquote

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)


def parse_database_url(raw: str) -> URL:
    """Parse a Postgres connection string, tolerating unescaped special
    characters (such as '@' or ':') in the password.

    Standard URL parsing breaks when a password contains '@', which is common
    with Supabase connection strings copied straight from the dashboard.
    Splitting credentials from host on the *last* '@' avoids that.
    """
    scheme, sep, rest = raw.strip().partition("://")
    if not sep:
        raise ValueError("DATABASE_URL must look like postgresql+psycopg://user:password@host:port/db")

    # Always use the psycopg (v3) driver.
    drivername = "postgresql+psycopg" if scheme in {"postgres", "postgresql"} else scheme

    credentials, at, location = rest.rpartition("@")
    if not at:
        raise ValueError("DATABASE_URL is missing credentials (user:password@host)")
    username, _, password = credentials.partition(":")

    location, _, query = location.partition("?")
    hostport, _, database = location.partition("/")
    host, _, port = hostport.partition(":")

    return URL.create(
        drivername=drivername,
        username=unquote(username),
        password=unquote(password) or None,
        host=host,
        port=int(port) if port else None,
        database=database or "postgres",
        query=dict(pair.split("=", 1) for pair in query.split("&") if "=" in pair),
    )


@lru_cache
def get_engine() -> Engine:
    url = parse_database_url(get_settings().database_url.get_secret_value())
    logger.info("Creating database engine for host=%s db=%s", url.host, url.database)
    return create_engine(
        url,
        pool_pre_ping=True,  # drop dead connections (poolers close idle ones)
        pool_size=5,
        max_overflow=5,
        pool_recycle=300,
        connect_args={"connect_timeout": 10},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def check_database() -> dict[str, str | bool]:
    """Connectivity check: server version and pgvector availability."""
    with get_engine().connect() as conn:
        version = conn.execute(text("SHOW server_version")).scalar_one()
        vector_available = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')")
        ).scalar_one()
        vector_installed = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar_one()
    return {
        "postgres_version": str(version),
        "pgvector_available": bool(vector_available),
        "pgvector_enabled": bool(vector_installed),
    }
