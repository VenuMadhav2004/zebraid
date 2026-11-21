import pytest
from sqlalchemy import inspect, select, text

from app.config import get_settings
from app.database import session as session_mod
from app.models import Zebra
from app.schemas import ZebraCreate

EXPECTED_TABLES = {
    "zebras",
    "image_assets",
    "gallery_entries",
    "identification_runs",
    "identification_candidates",
    "sightings",
    "verifications",
}


def test_select_one(engine):
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1


def test_driver_and_pool(engine):
    s = get_settings()
    assert engine.dialect.driver == "psycopg"
    assert engine.pool.size() == s.db_pool_size


def test_schema_applied(engine):
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_rls_enabled_on_all_tables(engine):
    with engine.connect() as conn:
        rows = dict(
            conn.execute(
                text(
                    "select c.relname, c.relrowsecurity from pg_class c "
                    "join pg_namespace n on n.oid=c.relnamespace "
                    "where n.nspname='public' and c.relkind='r'"
                )
            ).tuples().all()
        )
    assert all(rows[t] for t in EXPECTED_TABLES)


def test_migration_at_head(engine):
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    with engine.connect() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar_one() == head


def test_get_db_dependency_yields_and_closes(engine):
    gen = session_mod.get_db()
    db = next(gen)
    assert db.execute(text("select 1")).scalar_one() == 1
    with pytest.raises(StopIteration):
        next(gen)


def test_session_scope_rolls_back_on_error(engine):
    code = "T-rollback-check"
    with pytest.raises(RuntimeError):
        with session_mod.session_scope() as db:
            db.add(Zebra(**ZebraCreate(code=code).model_dump()))
            db.flush()
            raise RuntimeError("boom")
    with session_mod.session_scope() as db:
        assert db.scalar(select(Zebra).where(Zebra.code == code)) is None


def test_session_isolation(db):
    """Fixture session runs inside a rolled-back transaction."""
    assert db.execute(text("select 1")).scalar_one() == 1
    assert db.in_transaction()
