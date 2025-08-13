import os
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

OUTPUT_DIR = Path(os.environ.get("BACKUP_OUTPUT_DIR", "backups")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def detect() -> bool:
    return shutil.which("pg_dump") is not None or shutil.which("pg_dumpall") is not None


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip() or default


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown-host"


def _base_env() -> dict:
    env = dict(os.environ)
    # Respect standard libpq env vars if set; otherwise use provided fallbacks
    if _env("PGHOST") is None and _env("POSTGRES_HOST"):
        env["PGHOST"] = _env("POSTGRES_HOST") or ""
    if _env("PGPORT") is None and _env("POSTGRES_PORT"):
        env["PGPORT"] = _env("POSTGRES_PORT") or ""
    if _env("PGUSER") is None and _env("POSTGRES_USER"):
        env["PGUSER"] = _env("POSTGRES_USER") or ""
    if _env("PGPASSWORD") is None and _env("POSTGRES_PASSWORD"):
        env["PGPASSWORD"] = _env("POSTGRES_PASSWORD") or ""
    return env


def _databases_from_env() -> list[str] | None:
    dblist = _env("PGDATABASES") or _env("POSTGRES_DATABASES")
    if dblist:
        return [d.strip() for d in dblist.split(",") if d.strip()] or None
    single = _env("PGDATABASE") or _env("POSTGRES_DB") or _env("POSTGRES_DATABASE")
    if single:
        return [single]
    return None


def _list_databases(env: dict) -> list[str]:
    """Return list of PostgreSQL databases (excluding templates) using psql."""
    psql = shutil.which("psql")
    if not psql:
        print("[postgres] psql not found; cannot enumerate databases.")
        return []
    # Exclude templates and rdsadmin (AWS RDS), and restrict to connectable DBs
    query = (
        "SELECT datname FROM pg_database "
        "WHERE datistemplate = false AND datallowconn = true AND datname NOT IN ('rdsadmin');"
    )
    try:
        res = subprocess.run(
            [psql, "-Atc", query],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
    except FileNotFoundError:
        return []
    if res.returncode != 0:
        err = res.stderr.decode(errors="ignore")
        print(f"[postgres] Failed to list databases via psql: {err}")
        return []
    names = [ln.strip() for ln in res.stdout.decode().splitlines() if ln.strip()]
    return names


def backup() -> List[Path]:
    if not detect():
        print("[postgres] pg_dump/pg_dumpall not found; skipping Postgres backup.")
        return []

    created: list[Path] = []
    timestamp = _timestamp()
    host = _hostname()
    env = _base_env()

    dbs = _databases_from_env()

    # If no databases specified via env, enumerate them and dump each separately
    if not dbs:
        dbs = _list_databases(env)
        if not dbs:
            print("[postgres] No databases found to back up (or unable to enumerate). Skipping.")
            return []

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        print("[postgres] pg_dump not found; cannot dump individual databases.")
        return []

    for db in dbs:
        out_file = OUTPUT_DIR / f"postgres_{host}_{db}_{timestamp}.sql.gz"
        cmd = [pg_dump, "-d", db, "-Fc"]  # custom format; we'll gzip the binary output
        print(f"[postgres] Dumping database '{db}' to {out_file} ...")
        _run_and_gzip(cmd, out_file, env)
        created.append(out_file)

    return created


def _run_and_gzip(cmd: list[str], out_gz: Path, env: dict) -> None:
    import gzip

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "dump.sql"
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
        except FileNotFoundError:
            raise
        if res.returncode != 0:
            stderr = res.stderr.decode(errors="ignore")
            raise RuntimeError(f"postgres dump failed with code {res.returncode}: {stderr}")
        tmp_path.write_bytes(res.stdout)
        with gzip.open(out_gz, "wb") as gz:
            gz.write(tmp_path.read_bytes())
    os.chmod(out_gz, 0o600)
