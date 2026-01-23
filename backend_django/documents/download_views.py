# backend_django/documents/download_views.py
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote

from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.minio_client import download_bytes


def _bad(msg: str) -> Response:
    return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)


def _validate_no_traversal(p: str) -> bool:
    # S3 keys no son FS paths, pero esto evita cosas raras
    return ".." not in p and p.strip() != ""


class TableDownloadView(APIView):
    """
    GET /api/tables/download/?path=<minio_key>
    Reglas:
      - debe contener "/tables/"
      - debe terminar en ".csv"
    """

    def get(self, request):
        path = request.query_params.get("path")
        if not path:
            return _bad("Query param 'path' is required")

        path = unquote(str(path))
        if not _validate_no_traversal(path):
            return _bad("Invalid path")

        if "/tables/" not in path or not path.lower().endswith(".csv"):
            return _bad("Invalid table path")

        try:
            data = download_bytes(path)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        filename = os.path.basename(path)
        resp = HttpResponse(data, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp


class ImageDownloadView(APIView):
    """
    GET /api/images/download/?path=<minio_key>
    Reglas:
      - debe contener "/images/"
      - debe terminar en .png/.jpg/.jpeg
    """

    ALLOWED = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }

    def get(self, request):
        path = request.query_params.get("path")
        if not path:
            return _bad("Query param 'path' is required")

        path = unquote(str(path))
        if not _validate_no_traversal(path):
            return _bad("Invalid path")

        ext = Path(path).suffix.lower()
        if "/images/" not in path or ext not in self.ALLOWED:
            return _bad("Invalid image path")

        try:
            data = download_bytes(path)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        filename = os.path.basename(path)
        resp = HttpResponse(data, content_type=self.ALLOWED[ext])
        resp["Content-Disposition"] = f'inline; filename="{filename}"'
        return resp
