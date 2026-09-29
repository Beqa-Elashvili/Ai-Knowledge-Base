"""Apply SQL migrations from supabase/migrations to the Supabase database.

Usage (from backend/, venv active):
    python -m scripts.migrate            # apply pending migrations
    python -m scripts.migrate --status   # list applied / pending

Each migration runs in its own transaction and is recorded in
private.schema_migrations (a schema not exposed through the Supabase API),
so re-running the command is safe.
"""

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import text

from app.database import get_engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate")


def ensure_tracking_table() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("create schema if not exists private"))
        conn.execute(
            text(
                """
                create table if not exists private.schema_migrations (
                    version     text primary key,
                    applied_at  timestamptz not null default now()
                )
                """
            )
        )


def applied_versions() -> set[str]:
    with get_engine().connect() as conn:
        return {row[0] for row in conn.execute(text("select version from private.schema_migrations"))}


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true", help="show migration status without applying")
    args = parser.parse_args()

    ensure_tracking_table()
    done = applied_versions()
    files = migration_files()

    if args.status:
        for path in files:
            print(f"{'applied' if path.name in done else 'pending':8} {path.name}")
        return 0

    pending = [path for path in files if path.name not in done]
    if not pending:
        logger.info("Database is up to date (%d migrations applied).", len(done))
        return 0

    for path in pending:
        logger.info("Applying %s ...", path.name)
        sql = path.read_text(encoding="utf-8")
        try:
            with get_engine().begin() as conn:
                # exec_driver_sql sends the file as-is (multiple statements,
                # $$-quoted bodies) without SQLAlchemy parameter parsing.
                conn.exec_driver_sql(sql)
                conn.execute(
                    text("insert into private.schema_migrations (version) values (:v)"),
                    {"v": path.name},
                )
        except Exception as exc:
            logger.error("Failed to apply %s: %s", path.name, str(exc).splitlines()[0])
            return 1
        logger.info("Applied %s", path.name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
