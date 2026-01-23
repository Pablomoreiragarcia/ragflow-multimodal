# backend_django/rag/views.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from integrations.qdrant_client import search_text_and_tables, search_images
from integrations.minio_client import download_bytes
from rag.embeddings.text_embeddings import embed_text
from rag.embeddings.image_embeddings import embed_image
from rag.llm.chat import call_llm

import uuid
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from conversations.models import Conversation, Message, Attachment
from .serializers import AskRequestSerializer, AskResponseSerializer

from .intent import detect_intent, policy_engine
import inspect
from documents.models import Document
import math
import os

import csv
import io
import hashlib

IMAGES_LIMIT = int(os.getenv("IMAGES_LIMIT"))
TABLES_LIMIT = int(os.getenv("TABLES_LIMIT"))
TABLE_PREVIEW_ROWS = int(os.getenv("TABLE_PREVIEW_ROWS"))
TABLE_PREVIEW_CHARS = int(os.getenv("TABLE_PREVIEW_CHARS"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
OPENAI_MODELS = os.getenv("OPENAI_MODELS", OPENAI_MODEL).strip()

def get_available_models() -> list[dict]:
    # ids reales separados por coma
    ids = [m.strip() for m in OPENAI_MODELS.split(",") if m.strip()]
    if not ids:
        ids = ["gpt-4.1-mini"]

    default_id = OPENAI_MODEL if OPENAI_MODEL else ids[0]
    if default_id not in ids:
        ids.insert(0, default_id)

    # payload amigable para UI
    out = []
    for mid in ids:
        label = mid
        if mid == default_id:
            label = f"{mid} (default)"
        out.append({"id": mid, "label": label})
    return out

def dominant_doc_id_from_context(context: list[dict]) -> Optional[str]:
    scores = {}
    for c in context or []:
        meta = (c.get("metadata") or {})
        did = meta.get("doc_id")
        if did:
            scores[did] = scores.get(did, 0) + 1
    if not scores:
        return None
    return max(scores.items(), key=lambda kv: kv[1])[0]

def list_assets_for_docs(doc_ids: list[str], kind: str, limit: int = 30) -> list[dict]:
    if not doc_ids:
        return []

    docs = Document.objects.filter(id__in=doc_ids, status="ready")

    order = {did: i for i, did in enumerate(doc_ids)}
    docs = sorted(docs, key=lambda d: order.get(str(d.id), 10**9))

    def get_assets_qs(d: Document):
        # Ajusta/añade nombres si tu related_name es otro
        for rel in ("assets", "asset_set"):
            mgr = getattr(d, rel, None)
            if mgr is not None:
                return mgr.all()
        return None

    out: list[dict] = []
    for d in docs:
        qs = get_assets_qs(d)
        if qs is None:
            continue

        for a in qs:
            if getattr(a, "type", None) != kind:
                continue

            storage_key = getattr(a, "storage_key", None)
            if not storage_key:
                continue

            page = getattr(a, "page", None)
            title = f"{d.original_filename or d.id} · {kind}" + (f" · pág {page}" if page else "")
            out.append({"path": storage_key, "title": title})

            if len(out) >= limit:
                return out

    return out



def search_balanced_text_tables(q_vec, doc_ids, top_k_int):
    # cuota por doc (sube el mínimo para asegurar recall)
    per_doc = max(3, math.ceil(top_k_int / max(1, len(doc_ids))))
    all_hits = []
    for did in doc_ids:
        all_hits.extend(
            search_text_and_tables(query_vector=q_vec, top_k=per_doc, doc_ids=[did]) or []
        )
    # opcional: añade un global extra para mejorar ranking cross-doc
    all_hits.extend(
        search_text_and_tables(query_vector=q_vec, top_k=top_k_int, doc_ids=doc_ids) or []
    )

    # dedup por point.id si existe, si no por (modality|content)
    uniq = {}
    for h in all_hits:
        hid = getattr(h, "id", None) or getattr(h, "point_id", None) or None
        key = hid or (str(getattr(h, "payload", "") ) + "|" + str(getattr(h, "score", "")))
        # quédate con el de mejor score
        if key not in uniq or (getattr(h, "score", 0) > getattr(uniq[key], "score", 0)):
            uniq[key] = h

    hits = list(uniq.values())
    hits.sort(key=lambda x: float(getattr(x, "score", 0.0) or 0.0), reverse=True)
    return hits

def _sniff_dialect(sample: str):
    try:
        return csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
    except Exception:
        return csv.excel  # coma por defecto

def _table_signature(csv_bytes: bytes) -> str:
    """
    Firma estable:
    - normaliza whitespace
    - detecta delimitador
    - hace la firma independiente del orden de filas (body sorted)
    """
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    dialect = _sniff_dialect(sample)

    reader = csv.reader(io.StringIO(text), dialect=dialect)
    rows = []
    for row in reader:
        row = [" ".join(c.strip().split()).lower() for c in row]
        if any(row):
            rows.append(tuple(row))

    if not rows:
        return hashlib.sha256(csv_bytes).hexdigest()

    header = rows[0]
    body = sorted(rows[1:])  # <-- clave: ignora orden
    canon = "\n".join(
        [",".join(header)] + [",".join(r) for r in body]
    ).encode("utf-8")

    return hashlib.sha256(canon).hexdigest()

def dedup_table_assets_by_content(table_assets: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Input: [{"path":..., "title":...}, ...]
    Output:
      - unique_assets: lista (representantes)
      - dup_groups: [{ "representative": {...}, "duplicates": [ {...}, ... ] }, ...]
    """
    groups: dict[str, list[dict]] = {}
    for t in table_assets:
        try:
            b = download_bytes(t["path"])
            sig = _table_signature(b)
        except Exception:
            # si falla descarga, lo tratamos como único por path
            sig = f"err:{t['path']}"
        groups.setdefault(sig, []).append(t)

    unique = []
    dup_groups = []
    for sig, items in groups.items():
        unique.append(items[0])
        if len(items) > 1 and not sig.startswith("err:"):
            dup_groups.append({"representative": items[0], "duplicates": items[1:]})

    return unique, dup_groups

def _table_preview(csv_bytes: bytes, max_rows: int = TABLE_PREVIEW_ROWS, max_chars: int = TABLE_PREVIEW_CHARS) -> str:
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    dialect = _sniff_dialect(text[:4096])

    reader = csv.reader(io.StringIO(text), dialect=dialect)
    rows = []
    for row in reader:
        row = [c.strip() for c in row]
        if any(row):
            rows.append(row)
        if len(rows) >= max_rows:
            break

    if not rows:
        return "(tabla vacía o no parseable)"

    # Render simple tipo markdown
    header = rows[0]
    body = rows[1:]
    lines = []
    lines.append(" | ".join(header))
    lines.append(" | ".join(["---"] * len(header)))
    for r in body:
        lines.append(" | ".join(r))

    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars] + "\n...(recortado)"
    return out

def run_your_current_rag(
    question: str,
    top_k: int,
    model: str = OPENAI_MODEL,
    doc_ids: Optional[List[str]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    allow_table: bool = False,
    allow_image: bool = False,
    want_all_images: bool = False,
    want_all_tables: bool = False,
    max_images_for_llm: int = IMAGES_LIMIT,
    max_tables_for_llm: int = TABLES_LIMIT,
) -> Tuple[str, List[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    Ejecuta tu RAG actual y devuelve:
      - answer: str
      - context: list[dict] (puntos de contexto “UI-friendly”)
      - table_paths: list[str]
      - image_paths: list[str]
      - image_path: str|None

    NOTA:
    - No persiste nada en BBDD. Eso lo hace el AskView (o quien llame).
    - `history` debe venir ya en formato [{"role":"user|assistant","content":"..."}].
    """
    image_titles: List[str] = []
    q = (question or "").strip()
    if not q:
        return "Pregunta vacía.", [], None, None

    top_k_int = max(1, min(50, int(top_k) if str(top_k).isdigit() else 5))
    
    if doc_ids and len(doc_ids) > 1:
        top_k_search = min(50, top_k_int * 2)
    else:
        top_k_search = top_k_int

    q_vec_text = embed_text(q)

    if doc_ids and len(doc_ids) > 1:
        hits = search_balanced_text_tables(q_vec_text, doc_ids, top_k_int)
        top_k_search = min(50, top_k_int * 2)  # si quieres recortar después
        hits = hits[:top_k_search]
    else:
        hits = search_text_and_tables(query_vector=q_vec_text, top_k=top_k_search, doc_ids=doc_ids)

    def dominant_doc_id_from_hits(hits) -> Optional[str]:
        scores = {}
        for p in hits or []:
            payload = getattr(p, "payload", None) or {}
            meta = (payload.get("metadata") or {}) if isinstance(payload, dict) else {}
            doc_id = meta.get("doc_id")
            if not doc_id:
                continue
            s = getattr(p, "score", None)
            w = float(s) if s is not None else 1.0
            scores[doc_id] = scores.get(doc_id, 0.0) + w
        if not scores:
            return None
        return max(scores.items(), key=lambda kv: kv[1])[0]
    
    dominant_doc_id = dominant_doc_id_from_hits(hits)
    # 2b) Si NO hay doc_ids, acotar al doc_id del mejor hit y re-consultar (evita mezclar docs)
    # (Mismo patrón que ya estabas aplicando)
    if not doc_ids and hits:
        top_payload = getattr(hits[0], "payload", None) or {}
        top_meta = (top_payload.get("metadata") or {}) if isinstance(top_payload, dict) else {}
        top_doc_id = top_meta.get("doc_id")
        if top_doc_id:
            doc_ids = [top_doc_id]
            hits = search_text_and_tables(query_vector=q_vec_text, top_k=top_k_int, doc_ids=doc_ids)

    # 3) Dedup hits por (modality|content) para no repetir
    seen = set()
    dedup_hits = []
    for p in hits or []:
        payload = getattr(p, "payload", None) or {}
        meta = (payload.get("metadata") or {}) if isinstance(payload, dict) else {}
        modality = meta.get("modality") or payload.get("modality") or "text"
        content = payload.get("content") or ""

        key = f"{modality}|{content}"
        if key in seen:
            continue
        seen.add(key)
        dedup_hits.append(p)

    hits = dedup_hits

    # 4) Construir contexto (texto + tabla)
    first_table_path: Optional[str] = None
    first_table_block: Optional[str] = None

    context_points: List[Dict[str, Any]] = []
    context_parts: List[str] = []

    for p in hits or []:
        payload = getattr(p, "payload", None) or {}
        meta = (payload.get("metadata") or {}) if isinstance(payload, dict) else {}
        modality = meta.get("modality") or payload.get("modality") or "text"
        content = payload.get("content") or ""

        if modality == "table":
            csv_path = meta.get("csv_path") or meta.get("table_path")
            if csv_path and not first_table_path:
                first_table_path = csv_path

            table_obj = meta.get("table")
            if table_obj and not first_table_block:
                headers = table_obj.get("headers", []) or []
                rows = table_obj.get("rows", []) or []
                lines = [" | ".join(map(str, headers))] if headers else []
                for r in rows:
                    lines.append(" | ".join(map(str, r)))
                if lines:
                    first_table_block = "\n".join(lines)

        context_points.append(
            {"content": content, "metadata": {"modality": modality, **meta}}
        )
        if content:
            context_parts.append(content)

    # Imagen SOLO si allow_image
    first_image_path: Optional[str] = None
    image_bytes: Optional[bytes] = None
    image_bytes_list: Optional[List[bytes]] = None
    attachments_catalog_parts = []

    if doc_ids and allow_image:
        if want_all_images:
            # “todas”: listar assets del/los doc_ids y descargar bytes
            img_assets = list_assets_for_docs(doc_ids, kind="image", limit=max_images_for_llm)
            image_bytes_list = []

            for i, it in enumerate(img_assets, start=1):
                try:
                    image_bytes_list.append(download_bytes(it["path"]))
                    image_titles.append(f"IMAGEN {i}: {it['title']}")
                except Exception:
                    continue
            attachments_catalog_parts.append("IMÁGENES ADJUNTAS:\n" + "\n".join([t for t in image_titles]) if image_titles else "IMÁGENES ADJUNTAS:\n- (ninguna)")

            # opcional: para compat (guardar 1 image_path en Message.image_path)
            if img_assets:
                first_image_path = img_assets[0]["path"]

        else:
            # normal: 1 imagen por búsqueda semántica
            q_vec_img = embed_image(q)
            image_hits = search_images(query_vector=q_vec_img, top_k=1, doc_ids=doc_ids) or []
            if image_hits:
                img_payload = getattr(image_hits[0], "payload", None) or {}
                img_meta = (img_payload.get("metadata") or {}) if isinstance(img_payload, dict) else {}
                first_image_path = img_meta.get("image_path") or img_payload.get("image_path")
                if first_image_path:
                    try:
                        image_bytes = download_bytes(first_image_path)
                    except Exception:
                        image_bytes = None

    # TABLAS
    dup_groups = []
    if doc_ids and allow_table and want_all_tables:
        tabs_all = list_assets_for_docs(doc_ids, kind="table", limit=30)
        tabs_unique, dup_groups = dedup_table_assets_by_content(tabs_all)

        # limita tablas al LLM (por tokens)
        tabs_unique = tabs_unique[:max_tables_for_llm]

        tab_lines = ["TABLAS (preview):"]
        for idx, t in enumerate(tabs_unique, start=1):
            try:
                b = download_bytes(t["path"])
                prev = _table_preview(b, max_rows=TABLE_PREVIEW_ROWS, max_chars=TABLE_PREVIEW_CHARS)
            except Exception:
                prev = "(no se pudo leer el CSV)"
            tab_lines.append(f"\nTABLA {idx}: {t['title']}\n{prev}")

        attachments_catalog_parts.append("\n".join(tab_lines))

        if dup_groups:
            details = []
            for g in dup_groups:
                rep = g["representative"]["title"]
                dups = [x["title"] for x in g["duplicates"]]
                details.append(f"- Repetida: {rep} (también en: {', '.join(dups)})")
            attachments_catalog_parts.append("TABLAS REPETIDAS (mismo contenido):\n" + "\n".join(details))

    attachments_catalog = "\n\n".join([p for p in attachments_catalog_parts if p])

    if not context_parts and not context_points:
        return "No he encontrado información relevante en los documentos.", [], None, None

    # Contexto para LLM
    context_text = "\n".join([p for p in context_parts if p])

    # >>> CLAVE: solo añadimos TABLA completa si allow_table
    if allow_table and first_table_block:
        block = first_table_block
        if len(block) > TABLE_PREVIEW_CHARS:
            block = block[:TABLE_PREVIEW_CHARS] + "\n...(recortado)"
        context_text += "\n\nTABLA (completa):\n" + block

    # >>> CLAVE: solo pasamos table_path si allow_table
    llm_kwargs = dict(
        question=q,
        context=context_text,
        table_path=(first_table_path if allow_table else None),
        image_bytes=(image_bytes if allow_image else None),
        image_bytes_list=image_bytes_list,
        image_titles=image_titles,           # <--- NUEVO
        attachments_catalog=attachments_catalog,  # <--- NUEVO
        history=history,
        model=model,
    )

    sig = inspect.signature(call_llm)
    params = sig.parameters
    accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

    if "model" in params or accepts_kwargs:
        llm_kwargs["model"] = model

    answer = call_llm(**llm_kwargs)

    out_table_path = first_table_path if (allow_table and first_table_path) else None
    out_image_path = first_image_path if (allow_image and first_image_path) else None

    return answer, context_points, out_table_path, out_image_path


class ModelsView(APIView):
    def get(self, request):
        return Response({"models": get_available_models()}, status=status.HTTP_200_OK)


class AskView(APIView):
    def post(self, request):
        def sanitize_doc_ids(ids: list[str]) -> tuple[list[str], list[str]]:
            incoming = [str(x) for x in (ids or [])]
            if not incoming:
                return [], []
            ready_ids = set(
                str(x) for x in Document.objects.filter(id__in=incoming, status="ready")
                .values_list("id", flat=True)
            )
            valid = [d for d in incoming if d in ready_ids]
            invalid = [d for d in incoming if d not in ready_ids]
            return valid, invalid
        
        ser = AskRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        question: str = data["question"]
        top_k: int = data.get("top_k", 5)
        model: str = data.get("model", OPENAI_MODEL)
        if model == "default":
            model = OPENAI_MODEL
        conv_id = data.get("conversation_id")

        client_message_id = data.get("client_message_id") or uuid.uuid4().hex

        # 1) Obtener o crear conversación
        if conv_id:
            conv = Conversation.objects.get(id=conv_id, deleted=False)
        else:
            conv = Conversation.objects.create(
                title="Nueva conversación",
                scope="default",
                top_k=top_k,
                model=model or OPENAI_MODEL,
            )

        # 2) Persistir ajustes de conversación si cambian
        changed = False
        if conv.top_k != top_k:
            conv.top_k = top_k
            changed = True
        if model and conv.model != model:
            conv.model = model
            changed = True
        if changed:
            conv.save(update_fields=["top_k", "model", "updated_at"])

        # 3) Idempotencia: si ya existe el assistant de este turno, devolverlo
        existing_asst = (
            Message.objects.filter(
                conversation=conv,
                role=Message.ROLE_ASSISTANT,
                client_message_id=client_message_id,
            )
            .prefetch_related("attachments")
            .first()
        )
        if existing_asst:
            payload = {
                "answer": existing_asst.content,
                "context": existing_asst.extra.get("context", []),
                "conversation_id": conv.id,
                "assistant_message_id": existing_asst.id,
                "attachments": [
                    {"kind": a.kind, "path": a.path, "title": a.title}
                    for a in existing_asst.attachments.all()
                ],
            }
            return Response(AskResponseSerializer(payload).data, status=status.HTTP_200_OK)

        # 4) Crear user + generar + crear assistant (atómico)
        with transaction.atomic():
            # user message (si ya existe por constraint, no duplicamos)
            try:
                Message.objects.create(
                    conversation=conv,
                    role=Message.ROLE_USER,
                    content=question,
                    client_message_id=client_message_id,
                )
            except IntegrityError:
                pass
            
            # intent primero (ok)
            intent = detect_intent(question)

            # 1) Resolver effective_doc_ids
            incoming = data.get("doc_ids", None)
            if incoming is None:
                persisted = conv.doc_ids or []
                valid, invalid = sanitize_doc_ids(persisted)
                effective_doc_ids = valid if valid else None

                if invalid:
                    conv.doc_ids = valid
                    conv.updated_at = timezone.now()
                    conv.save(update_fields=["doc_ids", "updated_at"])
            else:
                incoming = [str(x) for x in (incoming or [])]
                valid, invalid = sanitize_doc_ids(incoming)
                effective_doc_ids = valid if valid else None
                # (opcional) también persistir selección explícita saneada:
                conv.doc_ids = valid
                conv.updated_at = timezone.now()
                conv.save(update_fields=["doc_ids", "updated_at"])

            # 2) Validar doc_ids (solo si hay)
            if effective_doc_ids:
                ready_qs = Document.objects.filter(id__in=effective_doc_ids, status="ready")
                ready_ids = set(str(d.id) for d in ready_qs)
                invalid = [d for d in effective_doc_ids if d not in ready_ids]
                if invalid:
                    return Response(
                        {"detail": "Some active documents are missing/not ready", "invalid_doc_ids": invalid},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # 3) Ejecutar RAG: si effective_doc_ids=None -> tu RAG hace autoselección por top hit
            answer, context, table_path, image_path = run_your_current_rag(
                question=question,
                top_k=top_k,
                model=model,
                doc_ids=effective_doc_ids,
                history=data.get("history"),
                allow_table=intent.allow_table,
                allow_image=intent.allow_image,
                want_all_images=getattr(intent, "want_all_images", False),
                want_all_tables=getattr(intent, "want_all_tables", False),
                max_images_for_llm=IMAGES_LIMIT,
            )

            asset_doc_ids = effective_doc_ids
            if not asset_doc_ids:
                # Auto: usa doc dominante del contexto (coherente con tu heurística de no mezclar)
                dom = dominant_doc_id_from_context(context)
                asset_doc_ids = [dom] if dom else []

            candidates: list[dict] = []
            # Imágenes
            if getattr(intent, "want_all_images", False):
                imgs = list_assets_for_docs(asset_doc_ids, kind="image", limit=30)
                for it in imgs:
                    candidates.append({"kind": Attachment.KIND_IMAGE, "path": it["path"], "title": it["title"]})
            else:
                if image_path:
                    candidates.append({"kind": Attachment.KIND_IMAGE, "path": image_path, "title": "Imagen"})

            # Tablas
            if getattr(intent, "want_all_tables", False):
                tabs_all = list_assets_for_docs(asset_doc_ids, kind="table", limit=30)
                tabs_unique, dup_groups = dedup_table_assets_by_content(tabs_all)
                for it in tabs_unique:
                    candidates.append({"kind": Attachment.KIND_TABLE, "path": it["path"], "title": it["title"]})
            else:
                if table_path:
                    candidates.append({"kind": Attachment.KIND_TABLE, "path": table_path, "title": "Tabla"})

            selected = policy_engine(intent, candidates)

            if getattr(intent, "want_all_images", False) or getattr(intent, "want_all_tables", False):
                n_img = sum(1 for a in selected if a["kind"] == Attachment.KIND_IMAGE)
                n_tab = sum(1 for a in selected if a["kind"] == Attachment.KIND_TABLE)

                dup_msg = ""
                if getattr(intent, "want_all_tables", False):
                    # dup_groups está en el scope si lo defines arriba; si no, guárdalo antes.
                    dup_count = sum(len(g["duplicates"]) for g in dup_groups) if "dup_groups" in locals() else 0
                    if dup_count:
                        # opcional: detalle
                        details = []
                        for g in dup_groups:
                            rep = g["representative"]["title"]
                            dups = [x["title"] for x in g["duplicates"]]
                            details.append(f"- Repetida: {rep} (también en: {', '.join(dups)})")
                        dup_msg = "\n\nHe detectado tablas repetidas (mismo contenido):\n" + "\n".join(details)

                # Si el retrieval textual fue pobre, evita un “no hay info” engañoso.
                if not answer or answer.strip().lower().startswith("no he encontrado información"):
                    answer = f"En los documentos activos he encontrado {n_img} imagen(es) y {n_tab} tabla(s). Te las adjunto." + dup_msg
                else:
                    # opcional: prefijo informativo siempre
                    answer = f"He encontrado {n_img} imagen(es) y {n_tab} tabla(s). Te las adjunto.\n\n" + answer + dup_msg

            # Crear assistant message
            try:
                asst = Message.objects.create(
                    conversation=conv,
                    role=Message.ROLE_ASSISTANT,
                    content=answer,
                    client_message_id=client_message_id,
                    extra={"context": context, "intent": intent.__dict__},
                    # compat: solo el primero de cada tipo seleccionado
                    image_path=next((a["path"] for a in selected if a["kind"] == Attachment.KIND_IMAGE), None),
                    table_path=next((a["path"] for a in selected if a["kind"] == Attachment.KIND_TABLE), None),
                )
            except IntegrityError:
                # por si entra doble request simultáneo
                asst = Message.objects.get(
                    conversation=conv,
                    role=Message.ROLE_ASSISTANT,
                    client_message_id=client_message_id,
                )

            # Crear attachments para ESTE mensaje (solo los seleccionados)
            att_objs = [
                Attachment(
                    message=asst,
                    kind=a["kind"],
                    path=a["path"],
                    title=a.get("title"),
                )
                for a in selected
            ]
            if att_objs:
                Attachment.objects.bulk_create(att_objs, ignore_conflicts=True)

        payload = {
            "answer": asst.content,
            "context": context,
            "conversation_id": conv.id,
            "assistant_message_id": asst.id,
            "attachments": selected,
        }
        return Response(AskResponseSerializer(payload).data, status=status.HTTP_200_OK)