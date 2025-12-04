# app/embeddings/text_embeddings.py
from typing import List
from sentence_transformers import SentenceTransformer
from app.config import EMBEDDING_MODEL

_model = None


def get_embedding_model() -> SentenceTransformer:
    """
    Devuelve una única instancia global del modelo de embeddings de texto.
    Ahora mismo usamos clip-ViT-B-16 para que tenga la misma dimensión que las imágenes.
    """
    global _model
    if _model is None:
        # IMPORTANTE: mismo modelo que uses para calcular la dimensión en Qdrant
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_text(text: str) -> List[float]:
    """
    Embedding de un solo texto.
    """
    model = get_embedding_model()
    vec = model.encode(text)
    return vec.tolist()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embedding de una lista de textos.
    """
    model = get_embedding_model()
    vecs = model.encode(texts)
    return vecs.tolist()


def get_embedding_dim() -> int:
    """
    Devuelve la dimensión de los embeddings de texto.
    Útil para crear la colección en Qdrant.
    """
    model = get_embedding_model()
    return model.get_sentence_embedding_dimension()
