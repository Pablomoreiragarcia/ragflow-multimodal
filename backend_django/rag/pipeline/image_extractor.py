import fitz  # PyMuPDF
from typing import List, Dict, Any

from integrations.minio_client import upload_bytes


def extract_images_from_pdf(doc_id: str, pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Extrae imágenes reales del PDF y devuelve una lista de dicts:
      - bytes: PNG bytes válidos
      - image_path: key en MinIO
      - page: número de página
      - content: opcional (caption vacío por ahora)
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: List[Dict[str, Any]] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        images = page.get_images(full=True)  # lista de xrefs

        for img_idx, img_info in enumerate(images):
            xref = img_info[0]
            pix = fitz.Pixmap(doc, xref)

            # Convertir a RGB si viene en CMYK/alpha
            if pix.n > 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            png_bytes = pix.tobytes("png")
            if not png_bytes:
                continue

            image_path = f"{doc_id}/images/page_{page_idx+1}_img_{img_idx+1}.png"

            # Subir a MinIO (opcional, pero normalmente lo quieres)
            upload_bytes(image_path, png_bytes, content_type="image/png")

            out.append(
                {
                    "bytes": png_bytes,
                    "image_path": image_path,
                    "page": page_idx + 1,
                    "content": "",
                    "modality": "image",
                }
            )

    return out
