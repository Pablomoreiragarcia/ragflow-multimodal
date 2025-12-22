from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Conversation, Message
from .serializers import (
    ConversationSerializer,
    ConversationDetailSerializer,
    MessageSerializer,
)


class ConversationViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.all().order_by("-updated_at")
    serializer_class = ConversationSerializer

    def get_serializer_class(self):
        if self.action in ["retrieve"]:
            return ConversationDetailSerializer
        return ConversationSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        # filtros opcionales estilo tu FastAPI: ?include_deleted=1&scope=...
        include_deleted = self.request.query_params.get("include_deleted")
        scope = self.request.query_params.get("scope")

        if not include_deleted or include_deleted in ("0", "false", "False"):
            qs = qs.filter(deleted=False)

        if scope:
            qs = qs.filter(scope=scope)

        return qs

    @action(detail=True, methods=["post"])
    def add_message(self, request, pk=None):
        """
        POST /api/conversations/{id}/add_message/
        body: {"role":"user|assistant|system", "content":"...", "extra": {...}}
        """
        conv = self.get_object()
        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        msg = Message.objects.create(
            conversation=conv,
            role=serializer.validated_data["role"],
            content=serializer.validated_data["content"],
            extra=serializer.validated_data.get("extra", {}),
        )

        # refresca updated_at
        conv.save(update_fields=["updated_at"])

        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)
