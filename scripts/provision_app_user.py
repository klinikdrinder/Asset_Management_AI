"""Provision one approved KDI application user through a direct PostgreSQL session.

The database connection string is requested with hidden input and is never stored
or printed. Run only after applying 202608030001_add_individual_app_user_auth.sql.
"""
from __future__ import annotations

from getpass import getpass
import re

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def yes_no(prompt: str) -> bool:
    value = input(f"{prompt} [y/N]: ").strip().lower()
    if value not in {"", "y", "yes", "n", "no"}:
        raise SystemExit("INVALID_BOOLEAN_RESPONSE")
    return value in {"y", "yes"}


def main() -> int:
    try:
        import psycopg
    except ImportError:
        raise SystemExit("PSYCOPG_REQUIRED") from None

    email = input("Approved Google email: ").strip().lower()
    if not EMAIL.fullmatch(email) or len(email) > 254:
        raise SystemExit("INVALID_EMAIL")
    role = input("Role [STAFF/ADMIN]: ").strip().upper()
    if role not in {"STAFF", "ADMIN"}:
        raise SystemExit("INVALID_ROLE")
    clinical = yes_no("Can view clinical media?")
    download = yes_no("Can download media?")
    active = yes_no("Activate this user?")
    dsn = getpass("Supabase direct database connection string (hidden): ").strip()
    if not dsn:
        raise SystemExit("DATABASE_CONNECTION_REQUIRED")

    statement = """
      insert into public.approved_app_users
        (normalized_email, role, is_active, can_view_clinical, can_download)
      values (%s, %s::public.app_role, %s, %s, %s)
      on conflict (normalized_email) do update set
        role=excluded.role, is_active=excluded.is_active,
        can_view_clinical=excluded.can_view_clinical,
        can_download=excluded.can_download, updated_at=now();

      update public.app_users u set
        role=%s::public.app_role, is_active=%s,
        can_view_clinical=%s, can_download=%s,
        disabled_at=case when %s then null else now() end,
        updated_at=now()
      where u.email=%s;
    """
    try:
        with psycopg.connect(dsn, connect_timeout=15) as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (email, role, active, clinical, download, role, active, clinical, download, active, email))
            connection.commit()
    except Exception:
        raise SystemExit("PROVISIONING_FAILED") from None
    finally:
        dsn = ""
    print("APP_USER_PROVISIONED")
    print(f"ROLE={role}")
    print(f"ACCOUNT={email[:2]}***@{email.split('@', 1)[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
