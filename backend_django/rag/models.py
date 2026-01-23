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
