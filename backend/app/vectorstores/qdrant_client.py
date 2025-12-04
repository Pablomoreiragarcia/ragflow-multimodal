# app/vectorstores/qdrant_client.py

from typing import List, Optional, Any, Dict

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
    Filter,
    FieldCondition,
    MatchAny,
    FilterSelector,
)
from uuid import uuid4

from app.config import TEXT_COLLECTION

# En Docker, el servicio de Qdrant se llama "rag_qdrant" y expone 6333
client = QdrantClient(host="qdrant", port=6333)


# ---------- helpers internos ----------

def _get_embedding_dim() -> int:
    """
    Saca la dimensión del modelo de texto que estás usando
    (el mismo que usas en text_embeddings.py).
    """
    from app.embeddings.text_embeddings import get_embedding_model

    model = get_embedding_model()
    vec = model.encode("dimension probe")
    return len(vec)


def _build_filter(
    doc_ids: Optional[List[str]] = None,
    modalities: Optional[List[str]] = None,
) -> Optional[Filter]:
    must_conditions = []

    if doc_ids:
        must_conditions.append(
            FieldCondition(
                key="doc_id",
                match=MatchAny(any=doc_ids),
            )
        )

    if modalities:
        must_conditions.append(
            FieldCondition(
                key="modality",
                match=MatchAny(any=modalities),
            )
        )

    if not must_conditions:
        return None

    return Filter(must=must_conditions)


# ---------- gestión de la colección ----------

def ensure_text_collection() -> None:
    """
    Crea la colección TEXT_COLLECTION si no existe.
    Si existe con distinta dimensión, la recrea.
    """
    dim = _get_embedding_dim()

    try:
        info = client.get_collection(TEXT_COLLECTION)
        params = info.config.params

        vectors = getattr(params, "vectors", None)
        current_dim = None

        if vectors is not None:
            # Puede ser un único VectorParams o un dict de ellos
            if isinstance(vectors, dict):
                current_dim = list(vectors.values())[0].size
            else:
                current_dim = vectors.size

        if current_dim == dim:
            # Ya está bien configurada, no tocamos nada
            return

        # Si la dimensión no coincide, la recreamos
        client.recreate_collection(
            collection_name=TEXT_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    except Exception:
        # Si no existe u otro error, la recreamos
        client.recreate_collection(
            collection_name=TEXT_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


# ---------- upsert de chunks de texto ----------

def add_text_chunks(chunks: List[Dict[str, Any]]) -> None:
    """
    chunks: lista de dicts con:
      - "id"
      - "content"
      - "metadata" (incluyendo doc_id, page, modality, etc.)
      - "embedding" (lista de floats)
    """
    points: List[PointStruct] = []

    for ch in chunks:
        emb = ch["embedding"]
        meta = ch.get("metadata", {}) or {}

        payload: Dict[str, Any] = {
            "content": ch["content"],
            "metadata": meta,
        }

        if "doc_id" in meta:
            payload["doc_id"] = meta["doc_id"]
        if "page" in meta:
            payload["page"] = meta["page"]
        if "modality" in meta:
            payload["modality"] = meta["modality"]

        points.append(
            PointStruct(
                id=str(uuid4()),
                vector=emb,
                payload=payload,
            )
        )

    if points:
        client.upsert(collection_name=TEXT_COLLECTION, points=points)


# ---------- upsert de filas de tablas ----------

def add_table_rows(rows: List[Dict[str, Any]]) -> None:
    """
    rows: lista de dicts con:
      - "id"
      - "content"
      - "metadata" (doc_id, page, csv_path, table{headers,rows}, modality="table")
      - "embedding"
    """
    points: List[PointStruct] = []

    for r in rows:
        emb = r["embedding"]
        meta = r.get("metadata", {}) or {}

        payload: Dict[str, Any] = {
            "content": r["content"],
            "metadata": meta,
        }

        if "doc_id" in meta:
            payload["doc_id"] = meta["doc_id"]
        if "page" in meta:
            payload["page"] = meta["page"]
        if "modality" in meta:
            payload["modality"] = meta["modality"]

        points.append(
            PointStruct(
                id=str(uuid4()),
                vector=emb,
                payload=payload,
            )
        )

    if points:
        client.upsert(collection_name=TEXT_COLLECTION, points=points)


# ---------- búsqueda genérica de texto ----------

def search_text_chunks(
    query: str,
    top_k: int = 5,
    doc_ids: Optional[List[str]] = None,
):
    """
    Busca en la colección usando el modelo de texto.
    Si doc_ids está definido, filtra para buscar sólo en esos documentos.
    """
    from app.embeddings.text_embeddings import get_embedding_model

    model = get_embedding_model()
    q_vec = model.encode(query).tolist()

    q_filter = _build_filter(doc_ids=doc_ids)

    res = client.query_points(
        collection_name=TEXT_COLLECTION,
        query=q_vec,
        limit=top_k,
        with_payload=True,
        query_filter=q_filter,
    )
    return res


# ---------- búsqueda texto + tablas (CLIP) ----------

def search_text_and_tables(
    query_vector: List[float],
    top_k: int = 5,
    doc_ids: Optional[List[str]] = None,
):
    """
    Usa un vector ya calculado (CLIP) y busca sólo en chunks de texto y filas de tabla.
    """
    q_filter = _build_filter(
        doc_ids=doc_ids,
        modalities=["text", "table"],
    )

    return client.query_points(
        collection_name=TEXT_COLLECTION,
        query=query_vector,
        limit=top_k,
        with_payload=True,
        query_filter=q_filter,
    )


def search_images(
    query_vector: List[float],
    top_k: int = 5,
    doc_ids: Optional[List[str]] = None,
):
    """
    Busca sólo puntos con modality="image".
    """
    q_filter = _build_filter(
        doc_ids=doc_ids,
        modalities=["image"],
    )

    return client.query_points(
        collection_name=TEXT_COLLECTION,
        query=query_vector,
        limit=top_k,
        with_payload=True,
        query_filter=q_filter,
    )


# ---------- borrado por doc_id ----------

def delete_by_doc_id(doc_id: str) -> None:
    """
    Borra todos los puntos de un documento concreto.
    """
    flt = _build_filter(doc_ids=[doc_id])

    client.delete(
        collection_name=TEXT_COLLECTION,
        points_selector=FilterSelector(filter=flt),
    )

