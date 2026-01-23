# app/llm/chat.py
import base64
from typing import Optional, List, Dict, Tuple, Any
from openai import OpenAI
import os
import imghdr

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
IMAGES_LIMIT = int(os.getenv("IMAGES_LIMIT"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
Eres un asistente RAG multimodal que responde SIEMPRE en castellano.
Usas SOLO la información del contexto, el historial de conversación y, si se te pasa, también el contenido de la imagen.

Instrucciones:
- Mantén coherencia con la conversación previa del usuario.
- Si el usuario pregunta por tablas, resume los datos clave de forma clara.
- Si el usuario pregunta por la imagen, describe con detalle qué se ve.
- Si algo NO aparece ni en el contexto ni en la imagen, dilo explícitamente.
- No inventes nombres, fotos, fechas ni identidades.
- La sección "CATÁLOGO DE ADJUNTOS" es la fuente de verdad para listar imágenes/tablas. No uses el "Contexto RAG" para inventar adjuntos.
- Solo existen las imágenes adjuntas etiquetadas como IMAGEN N. No inventes imágenes a partir del texto.
- Las tablas (TABLA N) no son imágenes. No listes filas de tabla como si fueran imágenes.
- Si una tabla está incompleta (preview), indícalo.
"""

def _guess_mime(image_bytes: bytes) -> str:
    # imghdr devuelve 'jpeg', 'png', 'gif', etc. Si no detecta, asumimos png.
    kind = imghdr.what(None, h=image_bytes)
    if kind == "jpeg":
        return "image/jpeg"
    if kind == "png":
        return "image/png"
    if kind == "gif":
        return "image/gif"
    if kind == "webp":
        return "image/webp"
    return "image/png"

def call_llm(
    *,
    question: str,
    context: str,
    history: Optional[List[Dict[str, str]]] = None,
    model: str = OPENAI_MODEL,
    table_path: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    image_bytes_list: Optional[List[bytes]] = None,
    image_titles: Optional[List[str]] = None,
    attachments_catalog: Optional[str] = None,
    max_images: int = IMAGES_LIMIT,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Llama a un modelo multimodal (texto + imagen) para responder
    usando:
      - contexto RAG
      - historial de conversación (user/assistant)
      - imagen opcional
    """
    
    # Texto base para este turno
    user_text = (
        "Pregunta del usuario:\n"
        f"{question}\n\n"
        "Contexto de los documentos:\n"
        f"{context}"
    )
    if attachments_catalog:
        user_text += (
            "\n\nCATÁLOGO DE ADJUNTOS (NO inventes adjuntos fuera de este catálogo):\n"
            f"{attachments_catalog}\n"
        )

    if table_path:
        user_text += (
            "\n\nNota: existe un CSV relevante en: "
            f"{table_path} (el modelo NO puede abrirlo por path; usa el preview si se incluye).\n"
        )

    # Contenido multimodal del mensaje actual
    user_content: List[Dict] = [{"type": "text", "text": user_text}]

    imgs: List[bytes] = []
    titles: List[str] = []

    if image_bytes is not None:
        imgs.append(image_bytes)
        titles.append("IMAGEN 1 (single)")
    if image_bytes_list:
        imgs.extend([b for b in image_bytes_list if b])
        if image_titles:
            titles = image_titles[:]
        else:
            titles = [f"IMAGEN {i+1}" for i in range(len(imgs))]

    # aplica límite
    imgs = imgs[: max_images if max_images and max_images > 0 else len(imgs)]
    titles = titles[: len(imgs)]

    for i, b in enumerate(imgs):
        user_content.append({"type": "text", "text": f"{titles[i]}: Describe brevemente lo que ves (1-2 frases)."})
        mime = _guess_mime(b)
        b64 = base64.b64encode(b).decode("utf-8")
        user_content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        )

    messages: List[Dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Historial previo (solo texto, ya ha pasado por RAG antes)
    if history:
        for turn in history:
            role = turn.get("role")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    # Turno actual (texto + imagen opcional)
    messages.append({"role": "user", "content": user_content,})

    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
    )

    text = completion.choices[0].message.content or ""
    usage = getattr(completion, "usage", None)

    return text, (usage.model_dump() if usage else None)
