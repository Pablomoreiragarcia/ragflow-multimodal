# backend_django\rag\ingestion.py

import uuid
import os
import json
from datetime import datetime
import logging
from io import BytesIO
from PIL import Image

from integrations.minio_client import upload_bytes

from rag.pipeline.text_extractor import extract_text_from_pdf
from rag.pipeline.table_extractor import extract_tables_from_pdf
from rag.pipeline.image_extractor import extract_images_from_pdf

from rag.pipeline.chunking import chunk_text

from rag.embeddings.text_embeddings import embed_text, embed_texts
from rag.embeddings.image_embeddings import embed_image

from integrations.qdrant_client import (
    add_text_chunks,
    add_table_rows,
    client,
    TEXT_COLLECTION,
    IMAGE_COLLECTION
)

from qdrant_client.models import PointStruct




logger = logging.getLogger(__name__)
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "ragflow")


def process_pdf(pdf_bytes: bytes, original_filename: str | None = None, doc_id: str | None = None, upload_original: bool = True) -> dict:
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
    if upload_original:
        upload_bytes(pdf_path, pdf_bytes, "application/pdf")

    # 4 — Extraer contenido del PDF
    pages = extract_text_from_pdf(pdf_bytes)
    images = extract_images_from_pdf(doc_id, pdf_bytes)
    tables = extract_tables_from_pdf(pdf_bytes)


    # ------------------------------
    # 🔹 Imágenes
    # ------------------------------
    image_points = []
    for img in images:
        raw = img.get("bytes")

        # 1) Si no son bytes, NO es una imagen. Saltamos.
        if not isinstance(raw, (bytes, bytearray)):
            logger.warning("[PDF_INGEST] Skip image: bytes is %s", type(raw).__name__)
            continue

        # 2) Intentar decodificar como imagen real (PNG/JPG/etc.)
        #try:
        #    pil = Image.open(BytesIO(raw)).convert("RGB")
        #except Exception as e:
        #    logger.warning("[PDF_INGEST] Skip image: cannot decode image bytes (%s)", e)
        #    continue

        # 3) Embedding CLIP con PIL (NO con bytes)
        try:
            vec = embed_image(img["bytes"])  # 512 dims
            if vec is None:
                continue
        except Exception as e:
            logger.warning("[PDF_INGEST] Skip image: CLIP encode failed (%s)", e)
            continue

        image_points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "content": img.get("content", ""),
                    "metadata": {
                        "doc_id": doc_id,
                        "page": (img.get("page", 0) + 1) if isinstance(img.get("page"), int) else img.get("page"),
                        "modality": "image",
                        "image_path": img.get("image_path"),
                    },
                },
            )
        )

    if image_points:
        client.upsert(collection_name=IMAGE_COLLECTION, points=image_points)

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
                    "content": chunk_text_content,
                    "metadata": {
                        "doc_id": doc_id,
                        "page": (page_number + 1),
                        "modality": "text",
                    },
                }
            )
            chunk_id += 1

    if all_chunks:
        vectors = embed_texts([c["content"] for c in all_chunks])

        for c, v in zip(all_chunks, vectors):
            c["embedding"] = v

        add_text_chunks(all_chunks)

    # ------------------------------
    # 🔹 Tablas
    # ------------------------------
    table_rows = []
    row_id = 0

    for table in tables:
        df = table["df"]
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
                        "page": (page_num + 1),
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
        vectors = embed_texts([r["content"] for r in table_rows])

        for r, v in zip(table_rows, vectors):
            r["embedding"] = v

        add_table_rows(table_rows, collection_name=TEXT_COLLECTION, embedding_key="embedding")
    
    result = {
        "status": "ok",
        "doc_id": doc_id,
        "original_filename": original_filename,
        "pdf_path": pdf_path,
        "pages": len(pages),
        "num_text_chunks": len(all_chunks),
        "num_tables": len(tables),
        "num_images": len(image_points),
        "created_at": datetime.utcnow().isoformat()
    }

    meta_key = f"docs_meta/{doc_id}.json"
    upload_bytes(meta_key, json.dumps(result, ensure_ascii=False).encode("utf-8"))

    return result