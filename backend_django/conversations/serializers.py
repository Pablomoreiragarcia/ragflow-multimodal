# backend_django/conversations/serializers.py

from rest_framework import serializers
from .models import Conversation, Message, Attachment
from documents.models import Document

class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = ("id", "kind", "path", "title", "created_at")

class MessageSerializer(serializers.ModelSerializer):
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at", "image_path", "table_path", "attachments"]


class ConversationSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["id", "title", "updated_at"]


class ConversationDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id", "title", "scope", "model", "top_k",
            "deleted", "doc_ids", "created_at", "updated_at",
            "messages",
        ]

class ConversationDocsSerializer(serializers.Serializer):
    doc_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )

class ConversationCreateSerializer(serializers.ModelSerializer):
    # IMPORTANT: si no devuelves id aquí, el front navega a /conversations/undefined
    id = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    deleted = serializers.BooleanField(read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "scope", "model", "top_k", "deleted", "created_at", "updated_at"]

    def validate_top_k(self, v):
        if v < 1 or v > 50:
            raise serializers.ValidationError("top_k must be between 1 and 50")
        return v
    

class ConversationDocsUpdateSerializer(serializers.Serializer):
    doc_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        required=True,
    )

    def validate_doc_ids(self, value):
        # Validar existencia + ready
        qs = Document.objects.filter(id__in=value, status="ready")
        if qs.count() != len(set(value)):
            raise serializers.ValidationError("Todos los doc_ids deben existir y estar en status=ready.")
        return value
