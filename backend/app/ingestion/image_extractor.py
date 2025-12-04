import fitz  # PyMuPDF
import uuid

from app.storage.minio_client import upload_bytes


def extract_images_from_pdf(doc_id: str, pdf_bytes: bytes):
    """
    Extrae imágenes del PDF, las guarda en MinIO y devuelve metadatos listos para Qdrant.
    """
    results = []
    pdf = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_num, page in enumerate(pdf):
        images = page.get_images(full=True)

        for _idx, img in enumerate(images):
            xref = img[0]
            base_image = pdf.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image["ext"]

            unique_id = str(uuid.uuid4())
            path = f"{doc_id}/images/{unique_id}.{ext}"

            # Guardar en MinIO
            upload_bytes(path, image_bytes)

            results.append(
                {
                    "content": f"[Imagen {unique_id}]",
                    "page": page_num + 1,
                    "image_path": path,
                    "modality": "image",
                    "bytes": image_bytes,
                }
            )

    return results
