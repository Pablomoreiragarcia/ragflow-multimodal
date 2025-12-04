from sentence_transformers import SentenceTransformer
from PIL import Image
import io
from app.config import EMBEDDING_MODEL

# Modelo CLIP compartido para texto e imágenes
_clip_model = None

def get_clip_model():
    global _clip_model
    if _clip_model is None:
        # Usa siempre el mismo modelo CLIP
        _clip_model = SentenceTransformer(EMBEDDING_MODEL)
    return _clip_model


def embed_image(image_bytes: bytes):
    """
    Devuelve el embedding CLIP (dim=512) de una imagen.
    """
    model = get_clip_model()
    img = Image.open(io.BytesIO(image_bytes))
    vec = model.encode(img)
    return vec.tolist()


def embed_text_with_clip(text: str):
    """
    Devuelve el embedding CLIP (dim=512) de un texto.
    Usado para chunks de texto, filas de tablas y queries.
    """
    model = get_clip_model()
    vec = model.encode(text)
    return vec.tolist()
