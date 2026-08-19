"""Safely connect, apply, and verify only Step 10 migration 004."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
from typing import Any, Callable, Iterable, NamedTuple
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from dotenv import load_dotenv


WORKSPACE = Path(r"D:\Asset_Management_AI")
MIGRATION = Path("supabase/migrations/202607310004_fix_step10_exact_legacy_status_contract.sql")
VERIFIER = Path("supabase/verification/verify_step10_legacy_status_mapping.sql")
MARKER = "STEP_10_LEGACY_STATUS_MAPPING_VERIFIED"
TIMEOUT_SECONDS = 5


class DeploymentSafetyError(RuntimeError):
    """A configuration or safety gate failed."""


class Candidate(NamedTuple):
    endpoint_type: str
    host: str
    port: int
    username: str
    database: str
    dsn: str
    transaction_pooler: bool = False

    def metadata(self) -> dict[str, Any]:
        return {
            "endpoint_type": self.endpoint_type,
            "host": redact_hostname(self.host),
            "port": self.port,
            "username_pattern": redact_username(self.username),
            "database": self.database,
            "sslmode": "require",
            "connect_timeout_seconds": TIMEOUT_SECONDS,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--diagnostic", action="store_true",
                        help="Test connectivity only; never execute DDL.")
    parser.add_argument("--database-only", action="store_true")
    parser.add_argument("--prompt-database-password", action="store_true")
    parser.add_argument("--supabase-region")
    parser.add_argument("--database-host")
    parser.add_argument("--database-port", type=int)
    parser.add_argument("--database-user")
    parser.add_argument("--expected-migration", required=True, type=Path)
    parser.add_argument("--report-path", required=True, type=Path)
    return parser


def validate_scope(args: argparse.Namespace) -> None:
    if Path.cwd().resolve() != WORKSPACE.resolve():
        raise DeploymentSafetyError("Working directory is not the workspace")
    if bool(args.execute) == bool(args.diagnostic):
        raise DeploymentSafetyError("Select exactly one of --execute or --diagnostic")
    if not args.database_only:
        raise DeploymentSafetyError("The database-only gate is required")
    if args.expected_migration.resolve() != MIGRATION.resolve():
        raise DeploymentSafetyError("Only migration 202607310004 is allowed")
    if not MIGRATION.is_file() or not VERIFIER.is_file():
        raise DeploymentSafetyError("Migration or verifier file is missing")


def project_reference(supabase_url: str) -> str:
    parsed = urlparse(supabase_url)
    host = parsed.hostname or ""
    ref = host.split(".", 1)[0]
    if parsed.scheme != "https" or not host.endswith(".supabase.co"):
        raise DeploymentSafetyError("SUPABASE_URL has no valid project reference")
    if not re.fullmatch(r"[a-z0-9]{20}", ref):
        raise DeploymentSafetyError("SUPABASE_URL project reference is invalid")
    return ref


def validate_region(region: str) -> str:
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d", region):
        raise DeploymentSafetyError("Supabase region format is invalid")
    return region


def validate_port(port: int) -> int:
    if isinstance(port, bool) or not 1 <= port <= 65535:
        raise DeploymentSafetyError("Database port must be between 1 and 65535")
    return port


def validate_host(host: str) -> str:
    if not host or len(host) > 253 or not re.fullmatch(
        r"(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
        r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", host
    ):
        raise DeploymentSafetyError("Database hostname is malformed")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise DeploymentSafetyError("Database host must be a hostname, not an IP address")
    return host.lower()


def redact_hostname(host: str) -> str:
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return "db.[project-ref].supabase.co"
    return re.sub(r"(?<=\.)[a-z0-9]{20}(?=\.)", "[project-ref]", host)


def redact_username(username: str) -> str:
    return "postgres.[project-ref]" if username.startswith("postgres.") else username


def pooler_hostname(region: str) -> str:
    return f"aws-0-{validate_region(region)}.pooler.supabase.com"


def _dsn(host: str, port: int, username: str, password: str,
         database: str = "postgres") -> str:
    query = urlencode({"sslmode": "require", "connect_timeout": TIMEOUT_SECONDS})
    return (
        f"postgresql://{quote(username, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}?{query}"
    )


def _explicit_candidate(url: str, ref: str, password: str | None) -> Candidate:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise DeploymentSafetyError("SUPABASE_DB_URL must be a PostgreSQL URL")
    username = parsed.username or ""
    host = parsed.hostname
    if ref not in f"{host} {username}":
        raise DeploymentSafetyError("SUPABASE_DB_URL does not match the project")
    supplied_password = parsed.password or password
    if not supplied_password:
        raise DeploymentSafetyError("The explicit database URL has no password")
    query = dict(parse_qsl(parsed.query))
    query["sslmode"] = "require"
    query["connect_timeout"] = str(TIMEOUT_SECONDS)
    netloc = (
        f"{quote(username, safe='')}:{quote(supplied_password, safe='')}"
        f"@{host}:{parsed.port or 5432}"
    )
    safe_url = urlunparse(("postgresql", netloc, parsed.path or "/postgres",
                           "", urlencode(query), ""))
    endpoint_type = "explicit_pooler" if "pooler.supabase.com" in host else "explicit"
    return Candidate(endpoint_type, host, parsed.port or 5432, username,
                     (parsed.path or "/postgres").lstrip("/"), safe_url,
                     parsed.port == 6543)


def connection_candidates(
    supabase_url: str,
    password: str | None,
    environment: dict[str, str] | None = None,
    *,
    region: str | None = None,
    database_host: str | None = None,
    database_port: int | None = None,
    database_user: str | None = None,
) -> list[Candidate]:
    env = environment if environment is not None else os.environ
    ref = project_reference(supabase_url)
    explicit = env.get("SUPABASE_DB_URL", "").strip()
    candidates: list[Candidate] = []
    override_values = (database_host, database_port, database_user)
    if any(value is not None for value in override_values):
        if not all(value is not None for value in override_values):
            raise DeploymentSafetyError(
                "Explicit endpoint requires --database-host, --database-port, and --database-user"
            )
        host = validate_host(str(database_host))
        port = validate_port(int(database_port))
        username = str(database_user)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
            raise DeploymentSafetyError("Database username is malformed")
        if ref not in f"{host} {username}":
            raise DeploymentSafetyError("Explicit endpoint does not match the project")
        if password:
            candidates.append(Candidate(
                "explicit", host, port, username, "postgres",
                _dsn(host, port, username, password), port == 6543,
            ))
    if explicit:
        candidates.append(_explicit_candidate(explicit, ref, password))
    if password and not candidates:
        direct = Candidate(
            "direct", f"db.{ref}.supabase.co", 5432, "postgres", "postgres",
            _dsn(f"db.{ref}.supabase.co", 5432, "postgres", password),
        )
        pooler_host = env.get("SUPABASE_DB_POOLER_HOST", "").strip()
        effective_region = (region or env.get("SUPABASE_REGION", "")).strip()
        if not pooler_host and not effective_region:
            raise DeploymentSafetyError(
                "Missing Supabase region; pass --supabase-region or a complete "
                "explicit database endpoint"
            )
        if not pooler_host and effective_region:
            pooler_host = pooler_hostname(effective_region)
        if pooler_host:
            pooler_host = validate_host(pooler_host)
            if not re.fullmatch(
                r"(?:aws-\d+-[a-z]{2}-[a-z]+-\d|[a-z0-9-]+)\.pooler\.supabase\.com",
                pooler_host,
            ):
                raise DeploymentSafetyError("Supavisor pooler host format is invalid")
            username = f"postgres.{ref}"
            candidates.append(
                Candidate("session_pooler", pooler_host, 5432, username,
                          "postgres", _dsn(pooler_host, 5432, username, password))
            )
            if transaction_pooler_compatible(
                MIGRATION.read_text(encoding="utf-8")
                + "\n"
                + VERIFIER.read_text(encoding="utf-8")
            ):
                candidates.append(
                    Candidate("transaction_pooler", pooler_host, 6543, username,
                              "postgres", _dsn(pooler_host, 6543, username, password),
                              True)
                    )
        candidates.append(direct)
    if not candidates:
        raise DeploymentSafetyError("No PostgreSQL connection candidates are configured")
    return candidates


def candidate_summary(
    supabase_url: str,
    environment: dict[str, str] | None = None,
    **overrides: Any,
) -> list[dict[str, Any]]:
    """Validate and describe candidates without retaining or requiring a password."""
    return [
        candidate.metadata()
        for candidate in connection_candidates(
            supabase_url, "__ENDPOINT_PREFLIGHT_ONLY__", environment, **overrides
        )
    ]


def transaction_pooler_compatible(sql: str) -> bool:
    """Reject SQL that requires session affinity before offering port 6543."""
    normalized = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.DOTALL).lower()
    session_only = (
        r"\blisten\b", r"\bunlisten\b", r"\bprepare\b", r"\bdeallocate\b",
        r"\bcreate\s+temp(?:orary)?\b", r"\bset\s+session\b",
        r"\bpg_advisory_lock\b",
    )
    return not any(re.search(pattern, normalized) for pattern in session_only)


def classify_exception(exc: Exception) -> str:
    name = type(exc).__name__
    text = " ".join(str(exc).lower().split())
    if name in {"InvalidPassword", "InvalidAuthorizationSpecification"} or \
            "password authentication failed" in text:
        return "authentication"
    if "ssl" in text or "certificate" in text:
        return "ssl"
    if isinstance(exc, (socket.gaierror, TimeoutError)) or any(
        token in text for token in (
            "getaddrinfo", "name or service not known", "could not translate host",
            "nodename nor servname", "connection timed out", "timeout expired",
            "network is unreachable", "no route to host", "connection refused",
        )
    ):
        return "network_dns" if any(
            token in text for token in ("getaddrinfo", "translate host", "name or service", "nodename")
        ) else "network"
    if isinstance(exc, DeploymentSafetyError):
        return "configuration"
    return "postgresql"


def safe_error(exc: Exception, secrets: Iterable[str] = ()) -> str:
    text = " ".join(str(exc).split())
    for secret in (*secrets, os.environ.get("SUPABASE_DB_URL", ""),
                   os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"postgres(?:ql)?://\S+", "[REDACTED_DATABASE_URL]",
                  text, flags=re.IGNORECASE)
    text = re.sub(r"password\s*=\s*\S+", "password=[REDACTED]",
                  text, flags=re.IGNORECASE)
    return text[:500]


def _connect_first(candidates: list[Candidate], connection_factory: Callable[..., Any],
                   password: str | None) -> tuple[Any, Candidate, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            connection = connection_factory(candidate.dsn, autocommit=True)
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                if cursor.fetchone()[0] != 1:
                    raise DeploymentSafetyError("Connectivity query returned an unexpected value")
            return connection, candidate, attempts
        except Exception as exc:
            attempts.append({
                **candidate.metadata(),
                "exception_class": type(exc).__name__,
                "failure_category": classify_exception(exc),
                "message": safe_error(exc, (password or "", candidate.dsn)),
            })
    raise ConnectionCandidatesFailed(attempts)


class ConnectionCandidatesFailed(RuntimeError):
    def __init__(self, attempts: list[dict[str, Any]]):
        super().__init__("All configured PostgreSQL connection candidates failed")
        self.attempts = attempts


def deploy(args: argparse.Namespace, connection_factory: Callable[..., Any],
           password: str | None = None) -> dict[str, Any]:
    validate_scope(args)
    supabase_url = _required_environment("SUPABASE_URL")
    candidates = connection_candidates(
        supabase_url, password,
        region=getattr(args, "supabase_region", None),
        database_host=getattr(args, "database_host", None),
        database_port=getattr(args, "database_port", None),
        database_user=getattr(args, "database_user", None),
    )
    report: dict[str, Any] = {
        "migration": str(MIGRATION),
        "migration_sha256": hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),
        "verifier": str(VERIFIER),
        "database_only": True,
        "diagnostic_only": bool(args.diagnostic),
        "unrelated_migrations_applied": 0,
        "deployed": False,
        "verification_marker": None,
        "ssl_required": True,
    }
    connection, candidate, attempts = _connect_first(candidates, connection_factory, password)
    report["connection_attempts"] = attempts
    report["successful_endpoint"] = candidate.metadata()
    try:
        if args.diagnostic:
            report["verdict"] = "CONNECTIVITY_VERIFIED"
            return report
        with connection.cursor() as cursor:
            cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            cursor.execute(VERIFIER.read_text(encoding="utf-8"))
            marker = _find_marker(cursor)
        if marker != MARKER:
            raise DeploymentSafetyError("Required verification marker was not returned")
        report.update(deployed=True, verification_marker=marker,
                      verdict="DEPLOYED_AND_VERIFIED")
        return report
    finally:
        connection.close()


def _find_marker(cursor: Any) -> str | None:
    while True:
        if cursor.description:
            for row in cursor.fetchall():
                if row and row[0] == MARKER:
                    return str(row[0])
        if not cursor.nextset():
            return None


def _load_connection_factory() -> Callable[..., Any]:
    if importlib.util.find_spec("psycopg") is None:
        raise DeploymentSafetyError("Missing PostgreSQL driver: psycopg")
    import psycopg
    return psycopg.connect


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DeploymentSafetyError(f"Missing database deployment prerequisite: {name}")
    return value


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def prompt_password() -> str:
    password = getpass.getpass("Supabase database password (input hidden): ")
    if not password:
        raise DeploymentSafetyError("Supabase database password was not provided")
    return password


def _blocked_verdict(category: str) -> str:
    if category == "authentication":
        return "BLOCKED_DATABASE_AUTHENTICATION"
    if category in {"network", "network_dns"}:
        return "BLOCKED_DATABASE_NETWORK"
    if category == "configuration":
        return "BLOCKED_DATABASE_ENDPOINT_CONFIGURATION"
    return "BLOCKED_DATABASE_OPERATION"


def main() -> int:
    args = build_parser().parse_args()
    load_dotenv(".env")
    password: str | None = None
    report: dict[str, Any]
    try:
        supabase_url = _required_environment("SUPABASE_URL")
        summary = candidate_summary(
            supabase_url,
            region=args.supabase_region,
            database_host=args.database_host,
            database_port=args.database_port,
            database_user=args.database_user,
        )
        print(json.dumps({"connection_candidates": summary}, sort_keys=True),
              file=sys.stderr)
        if args.prompt_database_password:
            password = prompt_password()
        report = deploy(args, _load_connection_factory(), password)
        exit_code = 0
    except ConnectionCandidatesFailed as exc:
        category = exc.attempts[-1]["failure_category"] if exc.attempts else "configuration"
        report = {
            "migration": str(MIGRATION), "database_only": True, "deployed": False,
            "verification_marker": None, "connection_attempts": exc.attempts,
            "verdict": _blocked_verdict(category),
            "failure_category": category,
            "exception_class": exc.attempts[-1]["exception_class"] if exc.attempts else None,
            "failure": safe_error(exc, (password or "",)),
        }
        exit_code = 2
    except Exception as exc:
        category = classify_exception(exc)
        report = {
            "migration": str(MIGRATION), "database_only": True, "deployed": False,
            "verification_marker": None, "verdict": _blocked_verdict(category),
            "failure_category": category, "exception_class": type(exc).__name__,
            "failure": safe_error(exc, (password or "",)),
        }
        exit_code = 2
    finally:
        password = None
    write_report(args.report_path, report)
    print(json.dumps({"report_path": str(args.report_path),
                      "verdict": report["verdict"]}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
