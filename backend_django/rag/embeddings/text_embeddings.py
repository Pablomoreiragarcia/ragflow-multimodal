# backend_django\rag\embeddings\text_embeddings.py

from functools import lru_cache
from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_text_embedding_model():
    # Ligero, rápido, 384 dims
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def _clean(t: str) -> str:
    t = str(t).replace("\n", " ").strip()
    # evita inputs absurdos
    return t[:4000]

def embed_text(text: str) -> list[float]:
    model = get_text_embedding_model()
    vec = model.encode(_clean(text))
    return vec.tolist()

def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_text_embedding_model()
    clean = [_clean(t) for t in texts]
    vecs = model.encode(clean)
    return vecs.tolist()
