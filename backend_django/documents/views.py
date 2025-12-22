from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
import uuid

from documents.models import Document
from documents.serializers import DocumentSerializer, DocumentIngestRequestSerializer
from integrations.minio_client import upload_bytes, get_minio_client, get_bucket


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all().order_by("-created_at")
    serializer_class = DocumentSerializer

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
        if not f:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

        doc_id = uuid.uuid4()
        storage_key = f"{doc_id}/original.pdf"

        pdf_bytes = f.read()
        upload_bytes(object_name=storage_key, data=pdf_bytes, content_type="application/pdf")

        doc = Document.objects.create(
            id=doc_id,
            original_filename=f.name,
            storage_key_original=storage_key,
            status="pending",
        )

        from documents.tasks import process_document
        process_document.delay(str(doc.id))

        return Response(DocumentSerializer(doc).data, status=status.HTTP_202_ACCEPTED)
