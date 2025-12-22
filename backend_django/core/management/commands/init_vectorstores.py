from django.core.management.base import BaseCommand
from integrations.qdrant_client import (
    ensure_text_collection,
    ensure_image_collection,
)

class Command(BaseCommand):
    help = "Initialize Qdrant collections used by the RAG pipeline"

    def handle(self, *args, **options):
        ensure_text_collection()
        ensure_image_collection()
        self.stdout.write(self.style.SUCCESS("Qdrant collections ensured."))
