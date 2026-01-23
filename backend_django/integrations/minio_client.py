# backend_django/integrations/minio_client.py
from __future__ import annotations

import io
import os
from functools import lru_cache
from typing import Optional
from minio import Minio


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v not in (None, "") else default


@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

    return Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


def get_bucket() -> str:
    return os.getenv("MINIO_BUCKET", "ragflow")  # pon aquí tu bucket “default”


def ensure_bucket(bucket: Optional[str] = None) -> None:
    client = get_minio_client()
    b = bucket or get_bucket()
    if not client.bucket_exists(b):
        client.make_bucket(b)


def upload_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream", bucket: Optional[str] = None) -> None:
    client = get_minio_client()
    b = bucket or get_bucket()
    ensure_bucket(b)

    bio = io.BytesIO(data)
    client.put_object(
        bucket_name=b,
        object_name=object_name,
        data=bio,
        length=len(data),
        content_type=content_type,
    )


def download_bytes(object_name: str, bucket: Optional[str] = None) -> bytes:
    client = get_minio_client()
    b = bucket or get_bucket()
    resp = client.get_object(b, object_name)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def download_file(object_name: str, dest_path: str, bucket: Optional[str] = None) -> None:
    client = get_minio_client()
    b = bucket or get_bucket()
    client.get_object(b, object_name, dest_path)

def list_objects(prefix: str = "", bucket: Optional[str] = None, recursive: bool = True) -> list[str]:
    client = get_minio_client()
    b = bucket or get_bucket()
    ensure_bucket(b)
    objs = client.list_objects(b, prefix=prefix, recursive=recursive)
    return [o.object_name for o in objs]
