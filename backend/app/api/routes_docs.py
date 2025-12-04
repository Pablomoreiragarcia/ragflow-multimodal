# backend/app/api/routes_docs.py

import json
from app.storage.minio_client import list_objects, download_file  # asumiendo helpers
from app.ingestion.pdf_ingest import process_pdf

from fastapi import APIRouter, HTTPException
from typing import List, Dict

from app.storage.minio_client import list_objects, delete_file
from app.vectorstores.qdrant_client import delete_by_doc_id

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_documents() -> Dict:
    """
    Lista los documentos existentes en MinIO.
    Consideramos que cada doc tiene un original en: <doc_id>/original.pdf
    """
    objs = list_objects("")
    docs = []

    for obj in objs:
        key = obj["key"]
        if key.endswith("/original.pdf"):
            doc_id = key.split("/")[0]
            docs.append({
                "doc_id": doc_id,
                "pdf_path": key,
                "size": obj["size"],
            })

    return {"documents": docs}


@router.delete("/{doc_id}")
def delete_document(doc_id: str):
    """
    Borra:
    - Todos los archivos en MinIO bajo <doc_id>/
    - Todos los puntos de Qdrant con ese doc_id
    """
    # 1) MinIO
    objs = list_objects(prefix=f"{doc_id}/")
    for o in objs:
        delete_file(o["key"])

    # 2) Qdrant
    try:
        deleted = delete_by_doc_id(doc_id)
    except Exception as e:
        raise HTTPException(500, f"Error borrando en Qdrant: {e}")

    return {
        "status": "ok",
        "doc_id": doc_id,
        "deleted_minio": len(objs),
        "deleted_qdrant": deleted,
    }
    
@router.post("/{doc_id}/reindex")
def reindex_document(doc_id: str):
    try:
        # 1) Descargar original
        pdf_bytes = download_file(f"{doc_id}/original.pdf")

        # 2) Borrar embeddings
        delete_by_doc_id(doc_id)

        # 3) Reprocesar usando mismo doc_id
        result = process_pdf(pdf_bytes, original_filename=None, doc_id=doc_id)
        return result
    except Exception as e:
        raise HTTPException(500, detail=str(e))
