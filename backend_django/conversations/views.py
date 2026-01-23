# backend_django\conversations\views.py

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Conversation
from .serializers import (
    ConversationSummarySerializer,
    ConversationDetailSerializer,
    ConversationCreateSerializer,
    ConversationDocsSerializer,
    ConversationDocsUpdateSerializer,
)
from documents.models import Document

class ConversationViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.filter(deleted=False).order_by("-updated_at")

    def get_queryset(self):
        qs = Conversation.objects.filter(deleted=False).order_by("-updated_at")

        # Solo en el detalle (GET /conversations/<id>) necesitamos mensajes + attachments
        if getattr(self, "action", None) == "retrieve":
            qs = qs.prefetch_related("messages__attachments")

        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return ConversationSummarySerializer
        if self.action == "create":
            return ConversationCreateSerializer
        return ConversationDetailSerializer

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.deleted = True
        obj.deleted_at = timezone.now()
        obj.save(update_fields=["deleted", "deleted_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=["get", "put"], url_path="docs")
    def docs(self, request, pk=None):
        conv = self.get_object()

        def sanitize(ids: list[str]) -> tuple[list[str], list[str]]:
            incoming = [str(x) for x in (ids or [])]
            if not incoming:
                return [], []

            ready_ids = set(
                str(x) for x in Document.objects.filter(id__in=incoming, status="ready")
                .values_list("id", flat=True)
            )
            valid = [d for d in incoming if d in ready_ids]      # mantiene orden
            invalid = [d for d in incoming if d not in ready_ids]
            return valid, invalid

        if request.method == "GET":
            current = [str(x) for x in (conv.doc_ids or [])]
            valid, invalid = sanitize(current)

            # Si había basura, limpia y persiste
            if invalid:
                conv.doc_ids = valid
                conv.updated_at = timezone.now()
                conv.save(update_fields=["doc_ids", "updated_at"])

            return Response(
                {"doc_ids": valid, "invalid_doc_ids": invalid},
                status=status.HTTP_200_OK,
            )

        # PUT
        ser = ConversationDocsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        incoming = [str(x) for x in ser.validated_data["doc_ids"]]
        valid, invalid = sanitize(incoming)

        conv.doc_ids = valid
        conv.updated_at = timezone.now()
        conv.save(update_fields=["doc_ids", "updated_at"])

        # Nunca 400: se sanea y se informa
        return Response(
            {"doc_ids": valid, "invalid_doc_ids": invalid},
            status=status.HTTP_200_OK,
        )
