# app/api/routes_images.py
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.storage.minio_client import download_file

router = APIRouter()


def _guess_mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".gif":
        return "image/gif"
    return "application/octet-stream"


@router.get("/images/download")
def download_image(path: str):
    """
    Descarga una imagen desde MinIO.
    `path` es la clave dentro del bucket, por ejemplo:
    60e5931c-3612-4cfd-aa24-f962e361a503/images/xxx.png
    """
    try:
        data = download_file(path)  # -> bytes
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    mime = _guess_mime(path)
    filename = Path(path).name

    return Response(
        content=data,
        media_type=mime,
        headers={
            # inline para que el navegador/Streamlit la pueda mostrar
            "Content-Disposition": f'inline; filename="{filename}"'
        },
    )
