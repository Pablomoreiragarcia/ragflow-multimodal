# backend_django\rag\views.py

from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rag.serializers import (
    AskRequestSerializer,
    QueryRequestSerializer,
)

from integrations.qdrant_client import search_text_and_tables, search_images
from integrations.minio_client import download_bytes
from rag.llm.chat import call_llm  # ajusta el import si tu chat.py está en otro sitio

from conversations.models import Conversation, Message
from django.db.models import Q

from rag.embeddings.text_embeddings import embed_text
from rag.embeddings.image_embeddings import embed_image


def load_conversation_history(conversation_id, limit: int = 12):
    """
    Devuelve últimos N mensajes (user/assistant) en orden cronológico,
    listo para pasarlo a call_llm(history=...).
    """
    qs = (
        Message.objects
        .filter(conversation_id=conversation_id)
        .filter(role__in=["user", "assistant"])
        .order_by("-created_at")[:limit]
    )
    turns = [{"role": m.role, "content": m.content} for m in reversed(list(qs))]
    return turns

class QueryView(APIView):
    def post(self, request):
        ser = QueryRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        top_k = ser.validated_data.get("top_k", 5)

        q_vec = embed_text(ser.validated_data["query"])

        # 1) Primera consulta (sin doc_ids)
        #hits = search_text_and_tables(q_vec, top_k=ser.validated_data["top_k"], doc_ids=None)
        hits = search_text_and_tables(q_vec, top_k=ser.validated_data["top_k"], doc_ids=None)
        # 2) Si hay hits, acotamos al doc_id del mejor resultado y re-consultamos
        if not doc_ids and hits:
            top_payload = hits[0].payload or {}
            top_meta = top_payload.get("metadata", {}) or {}
            top_doc_id = top_meta.get("doc_id")

            if top_doc_id:
                doc_ids = [top_doc_id]
                hits = search_text_and_tables(q_vec, top_k=top_k, doc_ids=doc_ids)

        # 3) Dedup (una sola vez)
        seen = set()
        results = []
        for p in hits:
            payload = p.payload or {}
            meta = payload.get("metadata", {}) or {}
            modality = meta.get("modality") or payload.get("modality") or "text"
            content = payload.get("content") or ""

            key = f"{modality}|{content}"
            if key in seen:
                continue
            seen.add(key)

            results.append(
                {
                    "score": getattr(p, "score", None),
                    "content": content,
                    "metadata": meta if meta else {
                        "doc_id": payload.get("doc_id"),
                        "page": payload.get("page"),
                        "modality": payload.get("modality"),
                    },
                }
            )

        return Response({"results": results})



class AskView(APIView):
    def post(self, request):
        ser = AskRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        question = data["question"]
        top_k = data.get("top_k", 5)
        doc_ids = data.get("doc_ids")
        history = data.get("history") or None

        conv_id = data.get("conversation_id")
        history_for_llm = None

        if not history and conv_id:
            history_for_llm = load_conversation_history(conv_id, limit=12)
        elif history:
            history_for_llm = [{"role": t["role"], "content": t["content"]} for t in history]

        # 1) Embedding pregunta (CLIP para alinear con tu colección 512)
        q_vec_text = embed_text(question)

        # 2) Buscar en Qdrant (texto/tablas)
        hits = search_text_and_tables(query_vector=q_vec_text, top_k=top_k, doc_ids=doc_ids)

        # Si el usuario NO restringe doc_ids, acotamos al doc_id del mejor hit y re-consultamos
        if not doc_ids and hits:
            top_payload = hits[0].payload or {}
            top_meta = top_payload.get("metadata", {}) or {}
            top_doc_id = top_meta.get("doc_id")

            if top_doc_id:
                doc_ids = [top_doc_id]
                hits = search_text_and_tables(q_vec_text, top_k=top_k, doc_ids=doc_ids)

        # Imagen (opcional) ya acotada al/los doc_ids
        image_hits = []
        if doc_ids:  # o si detectas intención de imagen
            q_vec_img = embed_image(question)
            image_hits = search_images(query_vector=q_vec_img, top_k=1, doc_ids=doc_ids)

        # Dedup (una sola vez)
        seen = set()
        dedup_hits = []
        for p in hits:
            payload = p.payload or {}
            meta = payload.get("metadata", {}) or {}
            modality = meta.get("modality") or payload.get("modality") or "text"
            content = payload.get("content") or ""

            key = f"{modality}|{content}"
            if key in seen:
                continue
            seen.add(key)
            dedup_hits.append(p)

        hits = dedup_hits


        # 3) Construir contexto (igual patrón que tu FastAPI)
        context_points = []
        context_parts = []
        first_table_path = None
        first_table_block = None
        table_sent = False
        for p in hits:
            payload = p.payload or {}
            meta = payload.get("metadata", {}) or {}

            modality = meta.get("modality") or payload.get("modality", "text")
            content = payload.get("content", "")

            if modality == "table":
                if table_sent:
                    # Evita repetir la tabla completa en cada fila
                    if "table" in meta:
                        meta = dict(meta)
                        meta.pop("table", None)
                else:
                    table_sent = True
                csv_path = meta.get("csv_path") or meta.get("table_path")
                if csv_path and not first_table_path:
                    first_table_path = csv_path
                table_obj = meta.get("table")
                if table_obj and not first_table_block:
                    headers = table_obj.get("headers", [])
                    rows = table_obj.get("rows", [])
                    # Formato texto robusto para el LLM
                    lines = [" | ".join(headers)]
                    for r in rows:
                        lines.append(" | ".join(map(str, r)))
                    first_table_block = "\n".join(lines)

            ctx_item = {
                "content": content,
                "metadata": {
                    "doc_id": meta.get("doc_id") or payload.get("doc_id"),
                    "page": meta.get("page") or payload.get("page"),
                    "modality": modality,
                    "csv_path": meta.get("csv_path"),
                    "table": meta.get("table"),
                    "image_path": meta.get("image_path") or payload.get("image_path"),
                    "score": getattr(p, "score", None),
                },
            }
            context_points.append(ctx_item)
            context_parts.append(content)

        table_item = next((x for x in context_points if x["metadata"].get("modality") == "table"), None)
        text_item  = next((x for x in context_points if x["metadata"].get("modality") == "text"), None)

        context_points = [x for x in [table_item, text_item] if x is not None]

        # 4) Imagen (opcional)
        first_image_path = None
        image_bytes = None

        if image_hits:
            img_payload = image_hits[0].payload or {}
            meta = img_payload.get("metadata", {}) or {}
            first_image_path = meta.get("image_path") or img_payload.get("image_path")

            img_ctx = {
                "content": img_payload.get("content", ""),
                "metadata": {
                    "doc_id": meta.get("doc_id") or img_payload.get("doc_id"),
                    "page": meta.get("page") or img_payload.get("page"),
                    "modality": "image",
                    "image_path": first_image_path,
                },
            }
            context_points.append(img_ctx)
            context_parts.append(img_ctx["content"])

            if first_image_path:
                try:
                    image_bytes = download_bytes(first_image_path)
                except Exception:
                    image_bytes = None

        if not context_points:
            return Response(
                {
                    "answer": (
                        "No he encontrado información relevante en los documentos "
                        "para responder a tu pregunta."
                    ),
                    "context": [],
                    "table_path": None,
                    "image_path": None,
                    "conversation_id": data.get("conversation_id"),
                },
                status=status.HTTP_200_OK,
            )

        context_text = "\n".join(context_parts)
        if first_table_block:
            context_text += "\n\nTABLA (completa):\n" + first_table_block

        history_for_llm = [{"role": t["role"], "content": t["content"]} for t in history] if history else None

        # 5) LLM
        answer = call_llm(
            question=question,
            context=context_text,
            table_path=first_table_path,
            image_bytes=image_bytes,
            history=history_for_llm,
        )

        # 6) Persistencia en Postgres (Conversation/Message)
        with transaction.atomic():
            conv_id = data.get("conversation_id")
            if conv_id:
                conv = Conversation.objects.get(id=conv_id)
            else:
                conv = Conversation.objects.create(
                    title=(question[:80] if question else "Nueva conversación"),
                    scope="default",
                    deleted=False,
                )

            Message.objects.create(conversation=conv, role="user", content=question, extra={})
            Message.objects.create(conversation=conv, role="assistant", content=answer, extra={"context": context_points})

        # --- UI-friendly context: 1 tabla + 1 texto (si existen) ---
        table_item = next(
            (x for x in context_points if (x.get("metadata") or {}).get("modality") == "table"),
            None,
        )
        text_item = next(
            (x for x in context_points if (x.get("metadata") or {}).get("modality") == "text"),
            None,
        )

        context_points = [x for x in (table_item, text_item) if x is not None]

        return Response(
            {
                "answer": answer,
                "context": context_points,
                "table_path": first_table_path,
                "image_path": first_image_path,
                "conversation_id": str(conv.id),
            },
            status=status.HTTP_200_OK,
        )
