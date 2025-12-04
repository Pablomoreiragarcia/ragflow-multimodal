from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.embeddings.text_embeddings import get_embedding_model
from app.vectorstores.qdrant_client import (
    search_text_and_tables,
    search_images,
)
from app.storage.minio_client import download_file
from app.llm.chat import call_llm

from minio.error import S3Error
from qdrant_client.http.exceptions import UnexpectedResponse

router = APIRouter()
_model = get_embedding_model()


class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    doc_ids: Optional[List[str]] = None  # filtrar por documentos concretos


class AskResponse(BaseModel):
    answer: str
    context: List[Dict[str, Any]]
    table_path: Optional[str] = None
    image_path: Optional[str] = None


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    # Vector CLIP de la pregunta (mismo modelo que usaste para indexar)
    q_vec = _model.encode(req.question).tolist()

    # 1) Buscar en Qdrant con manejo de errores
    try:
        hits = search_text_and_tables(
            query_vector=q_vec,
            top_k=req.top_k,
            doc_ids=req.doc_ids,
        )

        image_hits = search_images(
            query_vector=q_vec,
            top_k=1,
            doc_ids=req.doc_ids,
        )
    except UnexpectedResponse as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "QDRANT_QUERY_ERROR",
                "message": "No he podido consultar el almacén de conocimiento.",
                "details": str(e),
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "QDRANT_UNKNOWN_ERROR",
                "message": "Se ha producido un error inesperado consultando Qdrant.",
                "details": str(e),
            },
        )

    # --- Construir contexto de texto ---
    context_points: List[Dict[str, Any]] = []
    context_parts: List[str] = []

    first_table_path: Optional[str] = None

    for point in hits.points:
        payload = point.payload or {}
        meta = payload.get("metadata", {}) or {}

        modality = meta.get("modality") or payload.get("modality", "text")
        content = payload.get("content", "")

        if modality == "table":
            csv_path = meta.get("csv_path")
            if csv_path and not first_table_path:
                first_table_path = csv_path

        
        ctx_item = {
            "content": content,
            "metadata": {
                "doc_id": meta.get("doc_id") or payload.get("doc_id"),
                "page": meta.get("page") or payload.get("page"),
                "modality": modality,
                "csv_path": meta.get("csv_path"),
                "table": meta.get("table"),
                "image_path": meta.get("image_path") or payload.get("image_path"),
            },
        }
        context_points.append(ctx_item)
        context_parts.append(content)

        

    # --- Procesar imagen ---
    first_image_path: Optional[str] = None
    image_bytes: Optional[bytes] = None

    if image_hits.points:
        img_payload = image_hits.points[0].payload or {}
        meta = img_payload.get("metadata", {}) or {}
        first_image_path = meta.get("image_path") or img_payload.get("image_path")

        # chunk para que la UI pueda mostrar la imagen 👇
        img_ctx = {
            "content": img_payload.get("content", ""),
            "metadata": {
                "doc_id": meta.get("doc_id") or img_payload.get("doc_id"),
                "page": meta.get("page") or img_payload.get("page"),
                "modality": "image",
                "image_path": first_image_path,
            },
        }
        context_points.append(img_ctx)
        context_parts.append(img_ctx["content"])

        if first_image_path:
            try:
                image_bytes = download_file(first_image_path)
            except S3Error:
                image_bytes = None  # no reventamos si falla la descarga

    if not context_points and not first_image_path:
        return AskResponse(
            answer=(
                "No he encontrado información relevante en los documentos "
                "para responder a tu pregunta."
            ),
            context=[],
            table_path=None,
            image_path=None,
        )
    # ---------- Contexto plano para el LLM ----------
    context_text = "\n".join(c["content"] for c in context_points)

    # 3) Llamada real al LLM (texto + imagen)
    try:
        answer = call_llm(
            question=req.question,
            context=context_text,
            table_path=first_table_path,
            image_bytes=image_bytes,
        )
    except Exception as e:
        # No rompemos la API; devolvemos el contexto y un mensaje claro
        answer = (
            "He recuperado contexto de los documentos, pero se ha producido un error "
            "al llamar al modelo de lenguaje. Un administrador puede revisar los logs. "
            f"(Detalle técnico: {type(e).__name__}: {e})"
        )

    return AskResponse(
        answer=answer,
        context=context_points,
        table_path=first_table_path,
        image_path=first_image_path,
    )