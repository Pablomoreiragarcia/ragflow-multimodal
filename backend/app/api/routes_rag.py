from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from minio.error import S3Error
from qdrant_client.http.exceptions import UnexpectedResponse

from app.ingestion.pdf_ingest import process_pdf

router = APIRouter()

class IngestError(BaseModel):
    error_code: str
    message: str
    details: str | None = None

# ----- Routes -----

@router.post("/ingest")
async def ingest_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_FILE_TYPE",
                "message": "El archivo debe ser un PDF",
            },
        )

    pdf_bytes = await file.read()

    try:
        result = process_pdf(pdf_bytes, original_filename=file.filename)
        return result

    except S3Error as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "MINIO_ERROR",
                "message": "Error al guardar o leer archivos en MinIO.",
                "details": str(e),
            },
        )

    except UnexpectedResponse as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "QDRANT_ERROR",
                "message": "Error al escribir en Qdrant.",
                "details": str(e),
            },
        )

    except Exception as e:
        # aquí puedes afinar si quieres distinguir PDF_PARSE_ERROR, etc.
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "PDF_PARSE_ERROR",
                "message": "Se produjo un error procesando el PDF.",
                "details": str(e),
            },
        )