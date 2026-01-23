# backend_django/rag/serializers.py
from __future__ import annotations

from rest_framework import serializers


class ChatTurnSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()


class AskRequestSerializer(serializers.Serializer):
    question = serializers.CharField()
    top_k = serializers.IntegerField(required=False, default=5)
    model = serializers.CharField(required=False, default="default")
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    client_message_id = serializers.CharField(required=False, allow_null=True)
    doc_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )

    history = serializers.ListField(required=False)

class AttachmentOutSerializer(serializers.Serializer):
    kind = serializers.CharField()
    path = serializers.CharField()
    title = serializers.CharField(required=False, allow_null=True)


class AskResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    context = serializers.ListField(child=serializers.DictField(), required=False)

    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    assistant_message_id = serializers.UUIDField(required=False, allow_null=True)

    attachments = AttachmentOutSerializer(many=True, required=False)
