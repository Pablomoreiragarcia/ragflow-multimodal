# backend_django/documents/views.py
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
import uuid
from django.utils import timezone

from documents.models import Document, Asset
from documents.serializers import (
    DocumentSerializer,
    DocumentDetailSerializer,
    DocumentIngestRequestSerializer,
)
from integrations.minio_client import upload_bytes

class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Document.objects.all().order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DocumentDetailSerializer
        return DocumentSerializer

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        doc = self.get_object()
        return Response(
            {
                "id": str(doc.id),
                "status": doc.status,
                "meta": doc.meta or {},
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
            }
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="ingest",
        parser_classes=[MultiPartParser, FormParser],
    )
    def ingest(self, request):
        ser = DocumentIngestRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        f = ser.validated_data["file"]
        doc_id = uuid.uuid4()
        storage_key = f"{doc_id}/original.pdf"

        pdf_bytes = f.read()
        upload_bytes(storage_key, pdf_bytes, "application/pdf")

        doc = Document.objects.create(
            id=doc_id,
            original_filename=f.name,
            storage_key_original=storage_key,
            status="pending",
        )

        from documents.tasks import process_document
        process_document.delay(str(doc.id))

        return Response(DocumentSerializer(doc).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="reindex")
    def reindex(self, request, pk=None):
        doc = self.get_object()
        doc.status = "pending"
        meta = doc.meta or {}
        meta.pop("error", None)
        meta.pop("ingest_result", None)
        doc.meta = meta
        doc.updated_at = timezone.now()
        doc.save(update_fields=["status", "meta", "updated_at"])

        from documents.tasks import process_document
        process_document.delay(str(doc.id))

        return Response(
            {"id": str(doc.id), "status": doc.status, "detail": "reindex queued"},
            status=status.HTTP_202_ACCEPTED,
        )
