"""RLS / grant posture of the public schema (read-only checks, rolled back)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from tests.integration.test_database import EXPECTED_TABLES

API_ROLES = ("anon", "authenticated")


def test_api_roles_have_no_table_privileges(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "select grantee, table_name, privilege_type from information_schema.role_table_grants "
                "where table_schema='public' and grantee = any(:roles)"
            ),
            {"roles": list(API_ROLES)},
        ).all()
    assert rows == [], f"unexpected grants: {rows}"


def test_no_policies_and_rls_on(engine):
    with engine.connect() as conn:
        policies = conn.execute(text("select tablename, policyname from pg_policies where schemaname='public'")).all()
        unprotected = conn.execute(
            text(
                "select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                "where nspname='public' and relkind='r' and not relrowsecurity"
            )
        ).all()
    assert policies == [] and unprotected == []


@pytest.mark.parametrize("role", API_ROLES)
@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_api_role_is_denied(engine, role, table):
    """Simulate a PostgREST request: switch to the API role inside a rolled-back txn."""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text(f"set local role {role}"))
            with pytest.raises(ProgrammingError, match="permission denied"):
                conn.execute(text(f'select 1 from public."{table}" limit 1'))
        finally:
            trans.rollback()


def test_backend_role_bypasses_rls(engine):
    """Backend connects as the table owner (postgres, BYPASSRLS) so RLS without policies does not block it."""
    with engine.connect() as conn:
        user, bypass = conn.execute(
            text("select current_user, rolbypassrls from pg_roles where rolname = current_user")
        ).one()
        owners = set(
            conn.execute(
                text(
                    "select distinct pg_get_userbyid(relowner) from pg_class c join pg_namespace n on n.oid=c.relnamespace "
                    "where nspname='public' and relkind='r'"
                )
            ).scalars()
        )
    assert bypass is True or owners == {user}


def test_storage_has_no_public_policies(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text("select policyname, roles from pg_policies where schemaname='storage' and 'anon' = any(roles)")
        ).all()
        public_bucket = conn.execute(text("select public from storage.buckets where id='zebra_images'")).scalar_one()
    assert rows == [] and public_bucket is False
