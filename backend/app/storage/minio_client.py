import os
import io
import logging

from typing import BinaryIO
from minio import Minio, S3Error

from app.config import (
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_BUCKET,
)

logger = logging.getLogger(__name__)

client = Minio(
    endpoint=MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

def get_minio_client() -> Minio:
    return client

# Crear bucket si no existe
def _ensure_bucket():
    if not client.bucket_exists(bucket_name=MINIO_BUCKET):
        client.make_bucket(bucket_name=MINIO_BUCKET)

def upload_bytes(path: str, data: bytes, content_type: str | None = None):
    _ensure_bucket()
    client.put_object(
        MINIO_BUCKET,
        path,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def download_file(path: str) -> bytes:
    """
    Devuelve el contenido del objeto como bytes.
    path = object_name (por ejemplo: 'doc_id/tables/table_1.csv')
    """
    try:
        resp = client.get_object(MINIO_BUCKET, path)
        try:
            data = resp.read()  # -> bytes
            return data
        finally:
            resp.close()
            resp.release_conn()
    except S3Error as e:
        # Esto es lo que dispara tu 400 en el router
        logger.info(f"[MinIO] Error al descargar {path}: {e}")
        raise

def list_objects(prefix: str = "", recursive: bool = True):
    """
    Devuelve una lista de nombres de objetos en el bucket.
    """
    _ensure_bucket()
    objs = client.list_objects(
        MINIO_BUCKET,
        prefix=prefix,
        recursive=recursive,
    )
    return [{"key": o.object_name, "size": o.size} for o in objs]

def delete_file(path: str):
    _ensure_bucket()
    client.remove_object(MINIO_BUCKET, path)