import os
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import List


OUTPUT_DIR = Path(os.environ.get("BACKUP_OUTPUT_DIR", "backups")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def detect() -> bool:
    """Return True if mysqldump is available on the system PATH."""
    return shutil.which("mysqldump") is not None


def _env(var: str, default: str | None = None) -> str | None:
    val = os.environ.get(var)
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


def _mysql_base_args() -> list[str]:
    args: list[str] = []
    host = _env("MYSQL_HOST", "127.0.0.1")
    port = _env("MYSQL_PORT", "3306")
    user = _env("MYSQL_USER")
    password = _env("MYSQL_PASSWORD")

    if host:
        args += ["-h", host]
    if port:
        args += ["-P", str(port)]
    if user:
        args += ["-u", user]

    # Use MYSQL_PWD to avoid showing the password in process list
    if password:
        os.environ["MYSQL_PWD"] = password

    ssl_mode = _env("MYSQL_SSL_MODE")  # e.g., REQUIRED
    if ssl_mode:
        args += ["--ssl-mode", ssl_mode]

    return args


def _databases_from_env() -> list[str] | None:
    # Prefer MYSQL_DATABASES (comma-separated). Fallback to MYSQL_DATABASE.
    dblist = _env("MYSQL_DATABASES")
    if dblist:
        dbs = [d.strip() for d in dblist.split(",") if d.strip()]
        return dbs or None
    single = _env("MYSQL_DATABASE")
    if single:
        return [single]
    return None


def _list_databases(base_args: list[str]) -> list[str]:
    """Return list of MySQL databases using mysql CLI, excluding system schemas."""
    mysql_cli = shutil.which("mysql")
    if not mysql_cli:
        print("[mysql] mysql client not found; cannot enumerate databases.")
        return []
    cmd = [mysql_cli, *base_args, "-N", "-e", "SHOW DATABASES;"]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError:
        return []
    if res.returncode != 0:
        err = res.stderr.decode(errors="ignore")
        print(f"[mysql] Failed to list databases via mysql: {err}")
        return []
    names = [ln.strip() for ln in res.stdout.decode().splitlines() if ln.strip()]
    # Exclude common system databases
    exclude = {"information_schema", "performance_schema", "mysql", "sys"}
    return [n for n in names if n not in exclude]


def backup() -> List[Path]:
    """
    Create MySQL backups using mysqldump.
    - If MYSQL_DATABASES or MYSQL_DATABASE is provided, dumps each DB separately.
    - Otherwise, enumerates databases and dumps each separately.
    Returns list of created file paths.
    """
    if not detect():
        print("[mysql] mysqldump not found; skipping MySQL backup.")
        return []

    created: list[Path] = []
    base_args = _mysql_base_args()
    timestamp = _timestamp()
    host = _hostname()

    dbs = _databases_from_env()

    if not dbs:
        dbs = _list_databases(base_args)
        if not dbs:
            print("[mysql] No databases found to back up (or unable to enumerate). Skipping.")
            return []

    for db in dbs:
        out_file = OUTPUT_DIR / f"mysql_{host}_{db}_{timestamp}.sql.gz"
        cmd = ["mysqldump", *base_args, "--single-transaction", "--routines", "--triggers", db]
        print(f"[mysql] Dumping database '{db}' to {out_file} ...")
        _run_and_gzip(cmd, out_file)
        created.append(out_file)

    return created


def _run_and_gzip(cmd: list[str], out_gz: Path) -> None:
    """Run the dump command, stream output through gzip into out_gz."""
    import gzip

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "dump.sql"
        # Run dump to temp file first to detect errors cleanly
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        except FileNotFoundError:
            raise
        if res.returncode != 0:
            stderr = res.stderr.decode(errors="ignore")
            raise RuntimeError(f"mysqldump failed with code {res.returncode}: {stderr}")
        tmp_path.write_bytes(res.stdout)
        # Gzip it
        with gzip.open(out_gz, "wb") as gz:
            gz.write(tmp_path.read_bytes())
    # Ensure permissions are reasonable
    os.chmod(out_gz, 0o600)
