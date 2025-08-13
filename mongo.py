import os
import shutil
import socket
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

import bson
from pymongo import MongoClient

OUTPUT_DIR = Path(os.environ.get("BACKUP_OUTPUT_DIR", "backups")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def detect() -> bool:
    try:
        # Ensure PyMongo is available
        import pymongo  # noqa: F401
        import bson  # noqa: F401
        return True
    except Exception:
        return False


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


def _databases_from_env() -> list[str] | None:
    dblist = _env("MONGO_DATABASES")
    if dblist:
        return [d.strip() for d in dblist.split(",") if d.strip()] or None
    single = _env("MONGO_DATABASE")
    if single:
        return [single]
    return None


def _conn_args_from_env() -> list[str]:
    """Build connection flag args for mongo/mongosh/mongodump from env vars.

    Supported env vars:
      - MONGO_HOST (default 127.0.0.1)
      - MONGO_PORT (default 27017)
      - MONGO_USER (optional)
      - MONGO_PASSWORD (optional)
      - MONGO_AUTH_DB (default admin)
    """
    host = _env("MONGO_HOST", "127.0.0.1")
    port = _env("MONGO_PORT", "27017")
    user = _env("MONGO_USER")
    pwd = _env("MONGO_PASSWORD")
    auth_db = _env("MONGO_AUTH_DB", "admin")

    args: list[str] = []
    # Combine host and port in the format host:port
    if host and port:
        args += ["--host", f"{host}:{port}"]
    elif host:
        args += ["--host", host]

    if user:
        args += ["--username", user]
        # Only pass password if provided to avoid interactive prompts in non-interactive runs
        if pwd:
            args += ["--password", pwd]
        if auth_db:
            args += ["--authenticationDatabase", auth_db]
    return args


def _list_databases() -> list[str]:
    """Return list of MongoDB databases using PyMongo."""
    dump_uri = _env("MONGO_URI")
    if not dump_uri:
        print("[mongo] MONGO_URI env var is required to list databases. Skipping MongoDB enumeration.")
        return []
    try:
        client = MongoClient(dump_uri)
        names = client.list_database_names()
        # Ensure they are strings and strip whitespace
        return [n.strip() for n in names if isinstance(n, str) and n.strip()]
    except Exception as e:
        print(f"[mongo] Failed to list databases via PyMongo: {e}")
        return []


def backup() -> List[Path]:
    if not detect():
        print("[mongo] PyMongo/bson not available; skipping MongoDB backup.")
        return []

    created: list[Path] = []
    timestamp = _timestamp()
    host = _hostname()
    dump_uri = _env("MONGO_URI")

    if not dump_uri:
        print("[mongo] MONGO_URI env var is required for MongoDB backup. Skipping.")
        return []

    # Build database list
    dbs = _databases_from_env()
    if not dbs:
        dbs = _list_databases()
        if not dbs:
            print("[mongo] No databases found to back up (or unable to enumerate). Skipping.")
            return []

    # Connect once
    try:
        client = MongoClient(dump_uri)
    except Exception as e:
        print(f"[mongo] Failed to connect to MongoDB via URI: {e}")
        return []

    for db_name in dbs:
        out_file = OUTPUT_DIR / f"mongo_{host}_{db_name}_{timestamp}.archive.gz"
        print(f"[mongo] Dumping database '{db_name}' to {out_file} ...")
        # Create a temporary directory to store .bson files for each collection
        with tempfile.TemporaryDirectory(prefix=f"mongo_{db_name}_") as tmpdir:
            tmp_path = Path(tmpdir)
            try:
                db = client[db_name]
                # List collections in the database
                collections = db.list_collection_names()
                if not collections:
                    # Create an empty marker file so the archive is not empty
                    (tmp_path / "EMPTY_DB.txt").write_text("No collections", encoding="utf-8")
                for coll in collections:
                    coll_path = tmp_path / f"{coll}.bson"
                    with open(coll_path, "wb+") as f:
                        # Stream documents to BSON in order
                        cursor = db[coll].find({})
                        for doc in cursor:
                            f.write(bson.BSON.encode(doc))
            except Exception as e:
                print(f"[mongo] Failed dumping database '{db_name}': {e}")
                continue

            # Package all .bson files into a gzip tar archive to keep a single artifact per DB
            try:
                with tarfile.open(out_file, mode="w:gz") as tar:
                    for p in tmp_path.iterdir():
                        if p.is_file():
                            tar.add(p, arcname=p.name)
            except Exception as e:
                print(f"[mongo] Failed to write archive for '{db_name}': {e}")
                # If writing archive failed, skip adding to created
                continue

        created.append(out_file)

    # Secure file permissions
    for f in created:
        try:
            os.chmod(f, 0o600)
        except Exception:
            pass

    return created
