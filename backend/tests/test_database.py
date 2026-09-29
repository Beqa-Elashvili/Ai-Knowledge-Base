import pytest

from app.database import parse_database_url


def test_parses_standard_url() -> None:
    url = parse_database_url("postgresql+psycopg://postgres.ref:secret@aws-0.pooler.supabase.com:5432/postgres")
    assert url.drivername == "postgresql+psycopg"
    assert url.username == "postgres.ref"
    assert url.password == "secret"
    assert url.host == "aws-0.pooler.supabase.com"
    assert url.port == 5432
    assert url.database == "postgres"


def test_password_with_unescaped_special_characters() -> None:
    url = parse_database_url("postgresql://postgres:p@ss:w/rd@@db.example.com:6543/postgres")
    assert url.password == "p@ss:w/rd@"
    assert url.host == "db.example.com"
    assert url.port == 6543


def test_percent_encoded_password_is_decoded() -> None:
    url = parse_database_url("postgresql://postgres:p%40ss@db.example.com/postgres")
    assert url.password == "p@ss"


def test_plain_postgres_scheme_uses_psycopg_driver() -> None:
    assert parse_database_url("postgres://u:p@h/db").drivername == "postgresql+psycopg"


def test_query_parameters_are_kept() -> None:
    url = parse_database_url("postgresql://u:p@h:5432/db?sslmode=require")
    assert url.query == {"sslmode": "require"}


@pytest.mark.parametrize("raw", ["not-a-url", "postgresql://hostonly/db"])
def test_invalid_urls_raise(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_database_url(raw)
