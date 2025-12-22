# rag/embeddings/image_embeddings.py
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from PIL import Image
from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_clip_model() -> SentenceTransformer:
    m = SentenceTransformer("clip-ViT-B-16")
    # CLIP hard limit para texto; para imágenes no molesta
    m.max_seq_length = 77
    return m

def embed_image(image_bytes: bytes) -> list[float] | None:
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None

    model = get_clip_model()
    vec = model.encode(img)
    return vec.tolist()
