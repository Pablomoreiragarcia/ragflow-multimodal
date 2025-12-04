# app/llm/chat.py
import os
import base64
from typing import Optional
from app.config import OPENAI_API_KEY
from openai import OpenAI

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
Eres un asistente RAG multimodal que responde SIEMPRE en castellano.
Usas SOLO la información del contexto y, si se te pasa, también el contenido de la imagen.

Instrucciones:
- Si el usuario pregunta por tablas, resume los datos clave de forma clara
  (por ejemplo proyectos, duración y estado).
- Si el usuario pregunta por la imagen, describe con detalle qué se ve
  (colores, texto, distribución, etc.).
- Si algo NO aparece ni en el contexto ni en la imagen, dilo explícitamente.
"""


def call_llm(
    question: str,
    context: str,
    table_path: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
) -> str:
    """
    Llama a un modelo multimodal (texto + imagen) para responder
    usando el contexto recuperado y, opcionalmente, una imagen.
    """

    # Texto que verá el modelo
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

    user_content = [
        {
            "type": "text",
            "text": user_text,
        }
    ]

    # Adjuntamos la imagen si la hay
    if image_bytes is not None:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64}",
                },
            }
        )

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",     # o gpt-4.1 / gpt-4o-mini, según lo que uses
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
    )

    return completion.choices[0].message.content or ""
