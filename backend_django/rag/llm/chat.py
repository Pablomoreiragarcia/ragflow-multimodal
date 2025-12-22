# app/llm/chat.py
import base64
from typing import Optional, List, Dict
from openai import OpenAI
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
Eres un asistente RAG multimodal que responde SIEMPRE en castellano.
Usas SOLO la información del contexto, el historial de conversación y, si se te pasa, también el contenido de la imagen.

Instrucciones:
- Mantén coherencia con la conversación previa del usuario.
- Si el usuario pregunta por tablas, resume los datos clave de forma clara.
- Si el usuario pregunta por la imagen, describe con detalle qué se ve.
- Si algo NO aparece ni en el contexto ni en la imagen, dilo explícitamente.
"""


def call_llm(
    question: str,
    context: str,
    table_path: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
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

    if table_path:
        user_text += (
            "\n\nInformación adicional sobre tablas:\n"
            f"- Hay una tabla relevante almacenada en el CSV: {table_path}.\n"
            "En el contexto tienes varias filas de esa tabla; utilízalas para responder.\n"
        )

    # Contenido multimodal del mensaje actual
    user_content = [
        {
            "type": "text",
            "text": user_text,
        }
    ]

    if image_bytes is not None:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            }
        )

    # Construimos el listado de mensajes con historial
    messages: List[Dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    # Historial previo (solo texto, ya ha pasado por RAG antes)
    if history:
        for turn in history:
            role = turn.get("role")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    # Turno actual (texto + imagen opcional)
    messages.append(
        {
            "role": "user",
            "content": user_content,
        }
    )

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.2,
    )

    return completion.choices[0].message.content or ""
