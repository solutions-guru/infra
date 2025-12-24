import os
import sys
import socket
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
import mongo
import mysql
import postgres
from upload import upload_files

load_dotenv()


def main() -> int:
    # Validate S3 bucket
    bucket = os.environ.get("S3_BUCKET")
    prefix = os.environ.get("S3_PREFIX", "")
    if not bucket:
        print("[main] S3_BUCKET environment variable is required.")
        return 2

    created_files: list[Path] = []

    # MySQL
    try:
        if mysql.detect():
            created = mysql.backup()
            created_files.extend(created)
        else:
            print("[main] MySQL tools not found; skipping.")
    except Exception as e:
        print(f"[main] MySQL backup failed: {e}")

    # PostgreSQL
    try:
        if postgres.detect():
            created = postgres.backup()
            created_files.extend(created)
        else:
            print("[main] Postgres tools not found; skipping.")
    except Exception as e:
        print(f"[main] Postgres backup failed: {e}")

    # MongoDB
    try:
        if mongo.detect():
            created = mongo.backup()
            created_files.extend(created)
        else:
            print("[main] MongoDB tools not found; skipping.")
    except Exception as e:
        print(f"[main] MongoDB backup failed: {e}")

    if not created_files:
        print("[main] No backups were created. Nothing to upload.")
        return 1

    # Upload to S3
    try:
        uploaded_files = upload_files(created_files, bucket=bucket, prefix=prefix)
    except Exception as e:
        print(f"[main] Upload to S3 failed: {e}")
        print(f"[main] Local backup files preserved due to upload failure.")
        return 3

    # Prepare and write a log file before deleting local backups
    output_dir = Path(os.environ.get("BACKUP_OUTPUT_DIR", "backups")).resolve()
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_path = output_dir / f"backup_log_{timestamp}.txt"

    try:
        lines: list[str] = []
        lines.append("Backup run summary")
        lines.append(f"UTC Timestamp: {timestamp}")
        lines.append(f"S3 Bucket: {bucket}")
        lines.append(f"S3 Prefix: {prefix}")
        lines.append("")
        lines.append("Uploaded files:")
        date_folder = datetime.utcnow().strftime("%Y-%m-%d")

        # Determine server identifier (prefer IP, fallback to hostname)
        def _server_id() -> str:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(("8.8.8.8", 80))
                    ip = s.getsockname()[0]
                finally:
                    s.close()
                if ip:
                    return ip
            except Exception:
                pass
            try:
                host = socket.gethostname()
                if host:
                    return host
            except Exception:
                pass
            return "unknown-host"

        server = _server_id()

        for p in created_files:
            try:
                size = p.stat().st_size if p.exists() else 0
            except Exception:
                size = 0
            # Infer db type from filename prefix (must mirror upload.py logic)
            name_lower = p.name.lower()
            if name_lower.startswith("mysql_"):
                db_type = "mysql"
            elif name_lower.startswith("postgres_"):
                db_type = "postgres"
            elif name_lower.startswith("mongo_"):
                db_type = "mongo"
            else:
                db_type = "unknown"
            key_prefix = f"{prefix.strip('/')}/" if prefix else ""
            key = f"{key_prefix}{server}/{db_type}/{date_folder}/{p.name}"
            lines.append(f"- {p} | size={size} bytes | s3://{bucket}/{key}")
        log_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[main] Wrote backup log to {log_path}")
    except Exception as e:
        print(f"[main] Failed to write backup log: {e}")


    # Delete local backup files after successful upload and log creation
    # Only delete files that were successfully uploaded to S3
    deleted = 0
    failed_deletions = []
    for p in uploaded_files:
        try:
            if p.exists():
                p.unlink()
                deleted += 1
                print(f"[main] Deleted local backup file: {p}")
            else:
                print(f"[main] Backup file already removed: {p}")
        except Exception as e:
            failed_deletions.append((p, str(e)))
            print(f"[main] Failed to delete {p}: {e}")

    if failed_deletions:
        print(f"[main] Warning: Failed to delete {len(failed_deletions)} local file(s). They may need manual cleanup.")
    
    print(f"[main] Backup and upload completed successfully. Deleted {deleted} local file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
