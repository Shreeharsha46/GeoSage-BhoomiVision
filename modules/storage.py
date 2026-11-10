# ---------------------------------------------------------------------------
# GeoSage - Cloud storage utility (optional S3/R2 backend)
# ---------------------------------------------------------------------------
# This module provides cloud storage abstraction for production deployments.
# On Render free tier, local filesystem is ephemeral (lost on deploy).
# For persistent uploads/outputs, use S3-compatible storage (AWS S3, Cloudflare R2).
# ---------------------------------------------------------------------------
import os
import boto3
from botocore.config import Config as BotoConfig
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class StorageBackend:
    """Abstract storage backend."""

    def save(self, source_path: Path, destination_key: str) -> str:
        """Save file and return public URL or path."""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def get_url(self, key: str) -> str:
        raise NotImplementedError


class LocalStorage(StorageBackend):
    """Local filesystem storage (development only - not persistent on Render)."""

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, source_path: Path, destination_key: str) -> str:
        destination = self.base_path / destination_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_path.read_bytes())
        return destination.as_posix()

    def exists(self, key: str) -> bool:
        return (self.base_path / key).exists()

    def delete(self, key: str) -> bool:
        path = self.base_path / key
        if path.exists():
            path.unlink()
            return True
        return False

    def get_url(self, key: str) -> str:
        return f"/media/file/{key}"


class S3Storage(StorageBackend):
    """S3-compatible storage (AWS S3, Cloudflare R2, etc.)."""

    def __init__(self, bucket: str, region: str = "us-east-1",
                 endpoint_url: str = None,
                 access_key: str = None,
                 secret_key: str = None,
                 public_base_url: str = None):
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.public_base_url = public_base_url

        session = boto3.session.Session()
        self.client = session.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(signature_version="s3v4"),
        )

    def save(self, source_path: Path, destination_key: str) -> str:
        content_type = self._guess_content_type(source_path)
        self.client.upload_file(
            Filename=source_path.as_posix(),
            Bucket=self.bucket,
            Key=destination_key,
            ExtraArgs={"ContentType": content_type}
        )
        return self.get_url(destination_key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete {key}: {e}")
            return False

    def get_url(self, key: str) -> str:
        if self.public_base_url:
            return f"{self.public_base_url.rstrip('/')}/{key}"
        # Generate presigned URL (valid for 1 hour)
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=3600
        )

    def _guess_content_type(self, path: Path) -> str:
        ext = path.suffix.lower()
        mapping = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".tif": "image/tiff", ".tiff": "image/tiff",
            ".geojson": "application/geo+json", ".json": "application/json",
            ".kml": "application/vnd.google-earth.kml+xml",
            ".pdf": "application/pdf",
        }
        return mapping.get(ext, "application/octet-stream")


def get_storage_backend(config) -> StorageBackend:
    """Factory to get configured storage backend."""
    backend = getattr(config, "STORAGE_BACKEND", "local").lower()

    if backend == "s3" or backend == "r2":
        bucket = getattr(config, "AWS_S3_BUCKET", None) or os.environ.get("AWS_S3_BUCKET")
        if not bucket:
            logger.warning("S3/R2 configured but no bucket specified, falling back to local")
            return LocalStorage(config.UPLOAD_FOLDER)

        return S3Storage(
            bucket=bucket,
            region=getattr(config, "AWS_REGION", "us-east-1"),
            endpoint_url=getattr(config, "S3_ENDPOINT_URL", None) or os.environ.get("S3_ENDPOINT_URL"),
            access_key=getattr(config, "AWS_ACCESS_KEY_ID", None) or os.environ.get("AWS_ACCESS_KEY_ID"),
            secret_key=getattr(config, "AWS_SECRET_ACCESS_KEY", None) or os.environ.get("AWS_SECRET_ACCESS_KEY"),
            public_base_url=os.environ.get("S3_PUBLIC_BASE_URL"),
        )

    # Default to local storage
    return LocalStorage(config.UPLOAD_FOLDER)