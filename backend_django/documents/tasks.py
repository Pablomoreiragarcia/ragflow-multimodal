import logging
from celery import shared_task
from django.utils import timezone
from integrations.minio_client import download_bytes, upload_bytes
from datetime import timedelta

logger = logging.getLogger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, retry_kwargs={"max_retries": 3})
def process_document(self, document_id: str) -> dict:
    from documents.models import Document
    from rag.ingestion import process_pdf

    doc = Document.objects.get(id=document_id)

    if doc.status == "ready":
        return {"status": "skipped", "reason": "already ready", "doc_id": str(doc.id)}

    if doc.status == "processing":
        # Si está "processing" pero lleva demasiado tiempo, lo reintentas (rescate)
        if doc.updated_at and timezone.now() - doc.updated_at < timedelta(minutes=5):
            return {"status": "skipped", "reason": "already processing", "doc_id": str(doc.id)}

    doc.status = "processing"
    doc.updated_at = timezone.now()
    doc.save(update_fields=["status", "updated_at"])

    try:
        pdf_bytes = download_bytes(doc.storage_key_original, bucket=None)

        result = process_pdf(
            pdf_bytes=pdf_bytes,
            original_filename=doc.original_filename,
            doc_id=str(doc.id),
            upload_original=False,   # ya subido por el endpoint
        )

        meta = doc.meta or {}
        meta["ingest_result"] = result
        doc.meta = meta
        doc.status = "ready"
        doc.updated_at = timezone.now()
        doc.save(update_fields=["meta", "status", "updated_at"])

        return result

    except Exception as e:
        logger.exception("Ingest failed for document_id=%s", document_id)
        meta = doc.meta or {}
        meta["error"] = str(e)
        doc.meta = meta
        doc.status = "failed"
        doc.updated_at = timezone.now()
        doc.save(update_fields=["meta", "status", "updated_at"])
        raise
