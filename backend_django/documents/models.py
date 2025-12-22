import uuid
from django.db import models


class Document(models.Model):
    STATUS_CHOICES = [
        ("pending", "pending"),
        ("processing", "processing"),
        ("ready", "ready"),
        ("failed", "failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_filename = models.CharField(max_length=512, blank=True, null=True)
    storage_key_original = models.CharField(max_length=1024)  # ej: "{doc_id}/original.pdf"
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending")
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Asset(models.Model):
    TYPE_CHOICES = [("table", "table"), ("image", "image")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="assets")
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    page = models.IntegerField(null=True, blank=True)
    storage_key = models.CharField(max_length=1024)  # ej: "{doc_id}/tables/..csv" o "{doc_id}/images/..png"
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
