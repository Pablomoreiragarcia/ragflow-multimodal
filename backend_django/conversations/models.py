# backend_django/conversations/models.py
from __future__ import annotations

import uuid
from django.db import models
from django.db.models import Q
from documents.models import Document

class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, null=True, blank=True)
    scope = models.CharField(max_length=64, null=True, blank=True, default="default")

    # ajustes de conversación (persisten)
    model = models.CharField(max_length=128, default="default")
    top_k = models.PositiveIntegerField(default=5)

    deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    doc_ids = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    documents = models.ManyToManyField(
        Document,
        through="ConversationDocument",
        related_name="conversations",
        blank=True,
    )

    class Meta:
        ordering = ["-updated_at"]

class ConversationDocument(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "document"],
                name="uniq_conversation_document",
            )
        ]

class Message(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [(ROLE_USER, "user"), (ROLE_ASSISTANT, "assistant")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")

    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField(blank=True, default="")

    # idempotencia por turno (lo manda el front)
    client_message_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    # compatibilidad (opcional): primeros adjuntos “principales”
    table_path = models.TextField(null=True, blank=True)
    image_path = models.TextField(null=True, blank=True)

    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            # Evita duplicados del mismo turno y rol.
            # IMPORTANTE: requiere Q importado (tu error venía de no importarlo)
            models.UniqueConstraint(
                fields=["conversation", "role", "client_message_id"],
                condition=Q(client_message_id__isnull=False),
                name="uniq_conv_role_client_mid",
            )
        ]


class Attachment(models.Model):
    KIND_IMAGE = "image"
    KIND_TABLE = "table"
    KIND_CHOICES = [
        (KIND_IMAGE, "image"),
        (KIND_TABLE, "table"),
        # futuro: audio, video, ppt, docx, chart, etc.
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")

    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    path = models.TextField()  # el “path” que ya usas en /api/images/download/ o /api/tables/download/
    title = models.CharField(max_length=255, null=True, blank=True)
    mime_type = models.CharField(max_length=127, null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["message", "kind", "path"], name="uniq_msg_kind_path")
        ]
