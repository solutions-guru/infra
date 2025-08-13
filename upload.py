import os
import socket
from pathlib import Path
from typing import Iterable
from datetime import datetime


def upload_files(files: Iterable[Path], bucket: str, prefix: str | None = None) -> None:
    """
    Upload the given files to S3 using boto3.
    - bucket: S3 bucket name (required)
    - prefix: optional key prefix (e.g., backups/infra)
    
    Keys layout:
    {prefix(optional)}/{server-ip-or-host}/{db_type}/{YYYY-MM-DD}/{filename}
    - server-ip is preferred; falls back to hostname; then 'unknown-host'.
    - db_type is inferred from filename (mysql_, postgres_, mongo_). Falls back to 'unknown'.
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except Exception as e:
        raise RuntimeError("boto3 is required for S3 uploads. Please install boto3.") from e

    # Build boto3 client with optional explicit credentials and region from environment variables.
    # Falls back to boto3's default credential chain if not provided.
    region = os.getenv("S3_REGION")
    access_key = os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_KEY")
    endpoint = os.getenv("S3_ENDPOINT") or os.getenv("S3_ENDPOINT_URL")

    client_kwargs: dict = {}
    if region:
        client_kwargs["region_name"] = region
    if access_key and secret_key:
        client_kwargs["aws_access_key_id"] = access_key
        client_kwargs["aws_secret_access_key"] = secret_key
    if endpoint:
        client_kwargs["endpoint_url"] = endpoint

    s3 = boto3.client("s3", **client_kwargs)

    # Safe debug info (do not print secrets)
    cfg = []
    if "region_name" in client_kwargs:
        cfg.append(f"region={client_kwargs['region_name']}")
    if "endpoint_url" in client_kwargs:
        cfg.append("custom_endpoint")
    if "aws_access_key_id" in client_kwargs:
        cfg.append("static_credentials")
    if cfg:
        print(f"[upload] boto3 client configured with {'; '.join(cfg)}")

    date_folder = datetime.utcnow().strftime("%Y-%m-%d")

    # Determine server identifier (prefer IP, fallback to hostname)
    def _server_id() -> str:
        try:
            # Attempt to discover primary outbound IP without sending data
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

    for path in files:
        p = Path(path)
        if not p.exists():
            print(f"[upload] File does not exist, skipping: {p}")
            continue

        # Infer db type from filename prefix
        name_lower = p.name.lower()
        if name_lower.startswith("mysql_"):
            db_type = "mysql"
        elif name_lower.startswith("postgres_"):
            db_type = "postgres"
        elif name_lower.startswith("mongo_"):
            db_type = "mongo"
        else:
            db_type = "unknown"

        base_prefix = f"{prefix.strip('/')}/" if prefix else ""
        key = f"{base_prefix}{server}/{db_type}/{date_folder}/{p.name}"
        try:
            print(f"[upload] Uploading {p} to s3://{bucket}/{key} ...")
            s3.upload_file(str(p), bucket, key)
        except (BotoCoreError, ClientError) as e:
            raise RuntimeError(f"Failed to upload {p} to s3://{bucket}/{key}: {e}")
