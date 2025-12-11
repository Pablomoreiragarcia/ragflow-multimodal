# app/api/routes_healthcheck.py
from fastapi import APIRouter
from pydantic import BaseModel
import os

from app.storage.minio_client import get_minio_client
from app.vectorstores.qdrant_client import client as qdrant_client

router = APIRouter()

class DependencyStatus(BaseModel):
    ok: bool
    detail: str | None = None

class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "error"
    minio: DependencyStatus
    qdrant: DependencyStatus
    openai_api_key: DependencyStatus


@router.get("/health", response_model=HealthResponse)
def healthcheck():
    # --- MinIO ---
    minio_ok = True
    minio_detail = "ok"
    try:
        s3 = get_minio_client()
        # list_buckets solo para ver si responde
        list(s3.list_buckets())
    except Exception as e:
        minio_ok = False
        minio_detail = f"MinIO error: {e}"

    # --- Qdrant ---
    qdrant_ok = True
    qdrant_detail = "ok"
    try:
        qdrant_client.get_collections()
    except Exception as e:
        qdrant_ok = False
        qdrant_detail = f"Qdrant error: {e}"

    # --- OpenAI API key ---
    api_key = os.getenv("OPENAI_API_KEY")
    openai_ok = bool(api_key)
    openai_detail = "OK" if api_key else "OPENAI_API_KEY not set"

    # --- Estado global ---
    if minio_ok and qdrant_ok and openai_ok:
        status = "ok"
    elif minio_ok or qdrant_ok:
        status = "degraded"
    else:
        status = "error"

    return HealthResponse(
        status=status,
        minio=DependencyStatus(ok=minio_ok, detail=minio_detail),
        qdrant=DependencyStatus(ok=qdrant_ok, detail=qdrant_detail),
        openai_api_key=DependencyStatus(ok=openai_ok, detail=openai_detail),
    )




# from fastapi import APIRouter

# router = APIRouter()

# @router.get("/health")
# def healthcheck():
#     # Healthcheck minimalista para desarrollo:
#     # si la app ha arrancado, devuelve 200 y ya.
#     return {"status": "ok"}
