import uuid

from app.storage.minio_client import upload_bytes
from app.ingestion.text_extractor import extract_text_from_pdf
from app.ingestion.chunking import chunk_text
from app.ingestion.table_extractor import extract_tables_from_pdf
from app.ingestion.image_extractor import extract_images_from_pdf

from app.embeddings.image_embeddings import (
    get_clip_model,
    embed_image,
    embed_text_with_clip,
)

from app.vectorstores.qdrant_client import (
    ensure_text_collection,
    add_text_chunks,
    add_table_rows,
    client,
    TEXT_COLLECTION,
)

from qdrant_client.models import PointStruct

import json
from datetime import datetime
import io
import csv
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def process_pdf(pdf_bytes: bytes, original_filename: str | None = None, doc_id: str | None = None) -> dict:
    """
    Ingesta multimodal:
      - Subir PDF original a MinIO
      - Extraer texto + chunking + embeddings CLIP
      - Extraer tablas + filas → embeddings CLIP
      - Extraer imágenes → embeddings CLIP
      - Guardar todo en una única colección Qdrant: text_chunks
    """
    # 1 — doc_id único
    if doc_id is None:
        doc_id = str(uuid.uuid4())
        
    pdf_path = f"{doc_id}/original.pdf"
    # 2 — Subir PDF original
    upload_bytes(pdf_path, pdf_bytes)

    # 3 — Asegurar colección Qdrant (512 dims)
    ensure_text_collection()

    # 4 — Extraer contenido del PDF
    pages = extract_text_from_pdf(pdf_bytes)
    images = extract_images_from_pdf(doc_id, pdf_bytes)
    tables = extract_tables_from_pdf(pdf_bytes)

    # Modelo CLIP compartido (para acelerar)
    model = get_clip_model()

    # ------------------------------
    # 🔹 Imágenes
    # ------------------------------
    image_points = []
    for img in images:
        vec = embed_image(img["bytes"])  # 512 dims

        image_points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "content": img["content"],
                    "doc_id": doc_id,
                    "page": img["page"],
                    "modality": "image",
                    "image_path": img["image_path"],
                },
            )
        )

    if image_points:
        client.upsert(
            collection_name=TEXT_COLLECTION,
            points=image_points,
        )

    # ------------------------------
    # 🔹 Texto
    # ------------------------------
    all_chunks = []
    chunk_id = 0

    for page in pages:
        page_number = page["page"]
        text = page["text"]

        for chunk_text_content in chunk_text(text, max_len=500):
            all_chunks.append(
                {
                    #"id": chunk_id,
                    "content": chunk_text_content,
                    "metadata": {
                        "doc_id": doc_id,
                        "page": page_number,
                        "modality": "text",
                    },
                }
            )
            chunk_id += 1

    if all_chunks:
        # Embeddings CLIP para texto (512 dims)
        texts = [c["content"] for c in all_chunks]
        text_vectors = model.encode(texts).tolist()

        for i, emb in enumerate(text_vectors):
            all_chunks[i]["embedding"] = emb

        add_text_chunks(all_chunks)

    # ------------------------------
    # 🔹 Tablas
    # ------------------------------
    table_rows = []
    row_id = 0

    for table in tables:
        df = table["df"]              # ya viene limpio del extractor
        page_num = table["page"]
        table_idx = table.get("idx", 0)

        if df.empty:
            logger.warning(
                "[PDF_INGEST] Tabla %d en página %d está vacía, no se guarda CSV.",
                table_idx, page_num
            )
            continue

        # Guardar CSV completo en MinIO (con headers correctos)
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        csv_path = f"{doc_id}/tables/table_{page_num}_table_{table_idx}.csv"
        logger.info(
            "[PDF_INGEST] CSV para %s tiene %d bytes",
            csv_path,
            len(csv_bytes)
        )
        upload_bytes(csv_path, csv_bytes)
        logger.info(f"[PDF_INGEST] Guardando tabla {table_idx} de página {page_num} en {csv_path}")
        logger.info("[PDF_INGEST] Tabla %d head():\n%s" % (table_idx, df.head()))

        headers = list(df.columns)
        rows = df.values.tolist()

        for r in rows:
            # Texto “bonito” para el LLM: col1: val1 | col2: val2 | ...
            row_text_parts = []
            for col_name, value in zip(headers, r):
                row_text_parts.append(f"{col_name}: {value}")
            row_text = " | ".join(row_text_parts)

            table_rows.append(
                {
                    "id": row_id,
                    "content": row_text,
                    "metadata": {
                        "doc_id": doc_id,
                        "page": page_num,
                        "modality": "table",
                        "csv_path": csv_path,
                        "table": {
                            "headers": headers,
                            "rows": rows,
                        },
                    },
                }
            )
            row_id += 1

    if table_rows:
        row_texts = [r["content"] for r in table_rows]
        row_vectors = model.encode(row_texts).tolist()

        for i, emb in enumerate(row_vectors):
            table_rows[i]["embedding"] = emb

        add_table_rows(table_rows)
    
    result = {
        "status": "ok",
        "doc_id": doc_id,
        "original_filename": original_filename,
        "pdf_path": pdf_path,
        "pages": len(pages),
        "num_text_chunks": len(all_chunks),
        "num_tables": len(tables),
        "num_images": len(images),
        "created_at": datetime.utcnow().isoformat()
    }

    meta_key = f"docs_meta/{doc_id}.json"
    upload_bytes(meta_key, json.dumps(result, ensure_ascii=False).encode("utf-8"))

    return result
