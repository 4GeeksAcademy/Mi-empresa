from sqlalchemy.engine import make_url

from database import _resolve_database_url


def test_database_url_keeps_supabase_pooler_and_drops_psycopg_unsupported_option(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres:example@pooler.supabase.com:6543/postgres?pgbouncer=true&sslmode=require",
    )

    resolved = make_url(_resolve_database_url())

    assert resolved.host == "pooler.supabase.com"
    assert resolved.port == 6543
    assert resolved.query == {"sslmode": "require"}