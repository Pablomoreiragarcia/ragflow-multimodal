from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
from io import BytesIO
from fastapi.responses import StreamingResponse
from urllib.parse import unquote
from app.storage.minio_client import download_file
import io
from fastapi.responses import Response
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class TableRequest(BaseModel):
    csv_path: str  # ej: "doc123/tables/table_0.csv"


@router.post("/table")
def get_table(req: TableRequest):
    try:
        # 1) Descargar CSV desde MinIO
        csv_bytes = download_file(req.csv_path)

        if not csv_bytes:
            raise HTTPException(status_code=404, detail="CSV no encontrado en MinIO")

        # 2) Convertir a DataFrame
        df = pd.read_csv(BytesIO(csv_bytes))

        # 3) Respuesta serializable en JSON
        return {
            "csv_path": req.csv_path,
            "headers": list(df.columns),
            "rows": df.values.tolist()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables/download")
def download_table(path: str):
    """
    Descarga una tabla CSV desde MinIO.
    `path` es la clave dentro del bucket, por ejemplo:
    60e5931c-3612-4cfd-aa24-f962e361a503/tables/table_1.csv
    """
    logger.info(f"[TABLE_DOWNLOAD] Recibida petición para path={path}")
    try:
        data = download_file(path)  # -> bytes
        logger.info(f"[TABLE_DOWNLOAD] Bytes descargados: {len(data)}")
        logger.info(f"[TABLE_DOWNLOAD] Primera línea:\n{data[:200]}")
    except Exception as e:
        # si quieres ver el detalle real en logs, aquí podrías hacer logging.exception(e)
        raise HTTPException(status_code=400, detail=str(e))

    filename = Path(path).name

    return Response(
        content=data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )

