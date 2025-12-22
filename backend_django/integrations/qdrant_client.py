# backend_django\integrations\qdrant_client.py

from typing import List, Optional, Any, Dict
import os
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
from qdrant_client.http import models as qm

TEXT_COLLECTION = os.getenv("TEXT_COLLECTION", "text_chunks")
TEXT_DIM = 384

IMAGE_COLLECTION = os.getenv("IMAGE_COLLECTION", "image_chunks")
IMAGE_DIM = 512

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

if QDRANT_URL:
    client = QdrantClient(url=QDRANT_URL)
else:
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


# ---------- helpers internos ----------

def _build_filter(
    doc_ids: Optional[List[str]] = None,
    modalities: Optional[List[str]] = None,
) -> Optional[Filter]:
    must_conditions = []

    if doc_ids:
        must_conditions.append(
            FieldCondition(
                key="metadata.doc_id",
                match=MatchAny(any=doc_ids),
            )
        )

    if modalities:
        must_conditions.append(
            FieldCondition(
                key="metadata.modality",
                match=MatchAny(any=modalities),
            )
        )

    if not must_conditions:
        return None

    return Filter(must=must_conditions)


def _ensure_collection(name: str, dim: int) -> None:
    try:
        info = client.get_collection(name)
        params = info.config.params
        vectors = getattr(params, "vectors", None)

        current_dim = None
        if vectors is not None:
            if isinstance(vectors, dict):
                current_dim = list(vectors.values())[0].size
            else:
                current_dim = vectors.size

        if current_dim == dim:
            return

        client.recreate_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    except Exception:
        client.recreate_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

# ---------- gestión de la colección ----------

def ensure_text_collection() -> None:
    _ensure_collection(TEXT_COLLECTION, TEXT_DIM)

def ensure_image_collection() -> None:
    _ensure_collection(IMAGE_COLLECTION, IMAGE_DIM)

# ---------- upsert de chunks de texto ----------

def add_text_chunks(chunks: list[dict], collection_name: str = TEXT_COLLECTION, embedding_key: str = "embedding"):
    points = []
    for c in chunks:
        vec = c.get(embedding_key)
        if vec is None:
            continue
        points.append(
            PointStruct(
                id=str(uuid4()),
                vector=vec,
                payload={
                    "content": c["content"],
                    "metadata": c.get("metadata", {}),
                },
            )
        )
    if points:
        client.upsert(collection_name=collection_name, points=points)


# ---------- upsert de filas de tablas ----------

def add_table_rows(rows: list[dict], collection_name: str = TEXT_COLLECTION, embedding_key: str = "embedding"):
    points = []
    for r in rows:
        vec = r.get(embedding_key)
        if vec is None:
            continue
        points.append(
            PointStruct(
                id=str(uuid4()),
                vector=vec,
                payload={
                    "content": r["content"],
                    "metadata": r.get("metadata", {}),
                },
            )
        )
    if points:
        client.upsert(collection_name=collection_name, points=points)


# ---------- búsqueda texto + tablas (CLIP) ----------

def _query_points(collection_name: str, query_vector, top_k: int, qfilter):
    res = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=top_k,
        with_payload=True,
        query_filter=qfilter,
    )
    return res.points

def search_text(query_vector, top_k=5, doc_ids=None):
    qfilter = _build_filter(doc_ids=doc_ids, modalities=["text", "table"])
    return _query_points(TEXT_COLLECTION, query_vector, top_k, qfilter)

def search_text_and_tables(query_vector, top_k=5, doc_ids=None):
    return search_text(query_vector, top_k=top_k, doc_ids=doc_ids)

def search_images(query_vector, top_k=5, doc_ids=None):
    qfilter = _build_filter(doc_ids=doc_ids, modalities=["image"])
    return _query_points(IMAGE_COLLECTION, query_vector, top_k, qfilter)



# ---------- borrado por doc_id ----------

def delete_by_doc_id(doc_id: str) -> None:
    flt = _build_filter(doc_ids=[doc_id])

    for col in (TEXT_COLLECTION, IMAGE_COLLECTION):
        client.delete(
            collection_name=col,
            points_selector=FilterSelector(filter=flt),
        )

