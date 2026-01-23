# backend_django/rag/models.py
import uuid
from django.db import models
from django.utils import timezone

class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=255, null=True, blank=True)
    scope = models.CharField(max_length=64, default="default")

    # Opcional pero útil para lo que ya quieres en UI (modelo y top_k por chat)
    model = models.CharField(max_length=128, default="default")
    top_k = models.PositiveSmallIntegerField(default=5)

    deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["deleted", "-updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title or 'Nueva conversación'} ({self.id})"


class Message(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [(ROLE_USER, "user"), (ROLE_ASSISTANT, "assistant")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()

    # Aquí persistimos adjuntos y contexto: image_path, table_path, context, etc.
    extra = models.JSONField(default=dict, blank=True)

    # Idempotencia (evita duplicados si el usuario reintenta / refresh / doble click)
    client_message_id = models.UUIDField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["client_message_id"]),
        ]
        constraints = [
            # En Postgres, UNIQUE con NULL permite múltiples NULL -> OK.
            models.UniqueConstraint(
                fields=["conversation", "client_message_id"],
                name="uq_msg_conversation_client_message_id",
            )
        ]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:40]}"


class RagRequestLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    conversation_id = models.UUIDField(null=True, blank=True)
    client_message_id = models.CharField(max_length=64, null=True, blank=True)

    model_requested = models.CharField(max_length=128, null=True, blank=True)
    model_used = models.CharField(max_length=128, null=True, blank=True)
    fallback_reason = models.CharField(max_length=256, null=True, blank=True)

    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    total_tokens = models.IntegerField(null=True, blank=True)

    ok = models.BooleanField(default=True)
    status_code = models.IntegerField(default=200)
    error_type = models.CharField(max_length=128, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # tiempos (ms) si ya los estás midiendo o los añades ahora
    embed_ms = models.IntegerField(default=0)
    qdrant_ms = models.IntegerField(default=0)
    minio_ms = models.IntegerField(default=0)
    llm_ms = models.IntegerField(default=0)
    total_ms = models.IntegerField(default=0)

    api_pre_rag_ms = models.IntegerField(default=0)
    api_post_rag_ms = models.IntegerField(default=0)
    api_total_ms = models.IntegerField(default=0)
    db_ms = models.IntegerField(default=0)

    attachments_total = models.IntegerField(default=0)
    attachments_images = models.IntegerField(default=0)
    attachments_tables = models.IntegerField(default=0)
    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["conversation_id", "created_at"]),
            models.Index(fields=["ok", "created_at"]),
            models.Index(fields=["model_used", "created_at"]),
        ]
