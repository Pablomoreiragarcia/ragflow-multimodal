# backend_django/rag/intent.py
from __future__ import annotations

import re
from dataclasses import dataclass

KIND_IMAGE = "image"
KIND_TABLE = "table"

@dataclass
class Intent:
    allow_table: bool = False
    allow_image: bool = False
    want_all_tables: bool = False
    want_all_images: bool = False

_ALL_TABLES_RE = re.compile(r"\b(todas?|todas\s+las)\s+tablas\b", re.IGNORECASE)
_ALL_IMAGES_RE = re.compile(r"\b(todas?|todas\s+las)\s+(im[aá]genes|imagenes|fotos)\b", re.IGNORECASE)

def detect_intent(question: str) -> Intent:
    q = (question or "").strip().lower()

    want_all_tables = bool(_ALL_TABLES_RE.search(q))
    want_all_images = bool(_ALL_IMAGES_RE.search(q))

    img_kw = ["imagen", "imágenes", "foto", "fotos", "figura", "captura", "capturas", "pantallazo", "image", "picture", "screenshoot", "screenshot"]
    tbl_kw = ["tabla", "tablas", "csv", "excel", "hoja", "sheet", "spreadsheet", "dataframe"]

    wants_img = want_all_images or any(k in q for k in img_kw)
    wants_tbl = want_all_tables or any(k in q for k in tbl_kw)

    # “solo imágenes” => desactivar tablas
    if wants_img and not wants_tbl:
        return Intent(allow_table=False, allow_image=True, want_all_images=want_all_images, want_all_tables=want_all_tables)

    # “solo tablas” => desactivar imágenes
    if wants_tbl and not wants_img:
        return Intent(allow_table=True, allow_image=False, want_all_images=want_all_images, want_all_tables=want_all_tables)

    # ambas
    if wants_tbl and wants_img:
        return Intent(allow_table=True, allow_image=True, want_all_images=want_all_images, want_all_tables=want_all_tables)
    
    return Intent(allow_table=False, allow_image=False, want_all_images=False, want_all_tables=False)


def policy_engine(intent: Intent, candidates: list[dict]) -> list[dict]:
    # dedup por (kind, path)
    out = []
    seen = set()
    def add(c):
        key = (c.get("kind"), c.get("path"))
        if key in seen:
            return
        seen.add(key)
        out.append(c)

    if getattr(intent, "want_all_images", False):
        for c in candidates:
            if c.get("kind") == KIND_IMAGE:
                add(c)

    if getattr(intent, "want_all_tables", False):
        for c in candidates:
            if c.get("kind") == KIND_TABLE:
                add(c)

    # Si pidió "todas", ya devolvimos el set completo (por tipo)
    if getattr(intent, "want_all_images", False) or getattr(intent, "want_all_tables", False):
        return out

    return [c for c in candidates if c.get("kind") == KIND_TABLE]
