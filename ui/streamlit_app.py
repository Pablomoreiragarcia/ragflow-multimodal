# streamlit_app.py
from __future__ import annotations

import io
import os
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st

# ----------------------------
# Config
# ----------------------------
DEFAULT_BACKEND = "http://backenddjango:8000/api"  # ajusta si tu service se llama distinto
BACKEND_URL = os.getenv("BACKEND_URL", DEFAULT_BACKEND).rstrip("/")

st.set_page_config(page_title="ragflow-multimodal", layout="wide")

# ----------------------------
# Helpers HTTP
# ----------------------------
class ApiError(RuntimeError):
    pass


def api(path: str) -> str:
    # path sin leading slash recomendado
    return urljoin(BACKEND_URL + "/", path.lstrip("/") + ("" if path.endswith("/") else "/"))


def _raise_for_status(resp: requests.Response, where: str) -> None:
    if 200 <= resp.status_code < 300:
        return
    try:
        payload = resp.json()
    except Exception:
        payload = resp.text
    raise ApiError(f"{where} -> HTTP {resp.status_code}: {payload}")


def get_json(path: str, params: dict | None = None, timeout: int = 20) -> Any:
    resp = requests.get(api(path), params=params, timeout=timeout)
    _raise_for_status(resp, f"GET {path}")
    return resp.json()


def post_json(path: str, payload: dict | None = None, params: dict | None = None, timeout: int = 60) -> Any:
    resp = requests.post(api(path), json=payload, params=params, timeout=timeout)
    _raise_for_status(resp, f"POST {path}")
    # algunos endpoints devuelven 202 con json
    return resp.json() if resp.content else None


def patch_json(path: str, payload: dict, timeout: int = 20) -> Any:
    resp = requests.patch(api(path), json=payload, timeout=timeout)
    _raise_for_status(resp, f"PATCH {path}")
    return resp.json()


def delete_call(path: str, timeout: int = 20) -> None:
    resp = requests.delete(api(path), timeout=timeout)
    _raise_for_status(resp, f"DELETE {path}")


# ----------------------------
# Backend functions
# ----------------------------
def backend_health() -> dict:
    return get_json("health")


def fetch_conversations() -> list[dict]:
    # OpenAPI: GET /api/conversations/ -> list[Conversation]
    data = get_json("conversations")
    if isinstance(data, list):
        return data
    # defensivo: si algún día devuelves {"results": [...]}
    return data.get("results", [])


def fetch_conversation_detail(cid: str) -> dict:
    # GET /api/conversations/{id}/ -> ConversationDetail (incluye messages)
    return get_json(f"conversations/{cid}")


def create_conversation(title: str = "Nueva conversación", scope: str = "all") -> dict:
    # POST /api/conversations/
    payload = {"title": title, "scope": scope}
    return post_json("conversations", payload)


def update_conversation_title(cid: str, title: str) -> dict:
    # PATCH /api/conversations/{id}/
    return patch_json(f"conversations/{cid}", {"title": title})


def delete_conversation(cid: str) -> None:
    delete_call(f"conversations/{cid}")


def add_message(cid: str, role: str, content: str, extra: dict | None = None) -> dict:
    # POST /api/conversations/{id}/add_message/
    payload = {"role": role, "content": content, "extra": extra or {}}
    return post_json(f"conversations/{cid}/add_message", payload)


def fetch_documents() -> list[dict]:
    data = get_json("documents")
    if isinstance(data, list):
        return data
    return data.get("results", [])


def ingest_document(file_bytes: bytes, filename: str) -> dict:
    # POST /api/documents/ingest/ multipart (serializer: file)
    files = {"file": (filename, file_bytes, "application/pdf")}
    resp = requests.post(api("documents/ingest"), files=files, timeout=120)
    _raise_for_status(resp, "POST documents/ingest")
    return resp.json()


def reindex_document(doc_id: str) -> dict:
    # POST /api/documents/{id}/reindex/
    return post_json(f"documents/{doc_id}/reindex", payload={})


def delete_document(doc_id: str) -> None:
    delete_call(f"documents/{doc_id}")


# ----------------------------
# Download tables/images (ya tienes endpoints)
# ----------------------------
def download_table_bytes(minio_key: str) -> bytes:
    # GET /api/tables/download/?path=<key>
    resp = requests.get(api("tables/download"), params={"path": minio_key}, timeout=60)
    _raise_for_status(resp, "GET tables/download")
    return resp.content


def download_image_bytes(minio_key: str) -> tuple[bytes, str]:
    # GET /api/images/download/?path=<key>
    resp = requests.get(api("images/download"), params={"path": minio_key}, timeout=60)
    _raise_for_status(resp, "GET images/download")
    content_type = resp.headers.get("Content-Type", "application/octet-stream")
    return resp.content, content_type


# ----------------------------
# RAG
# ----------------------------
def rag_ask(question: str, history: list[dict], doc_ids: list[str] | None, top_k: int) -> dict:
    payload = {
        "question": question,
        "history": history,
        "doc_ids": doc_ids or [],
        "top_k": int(top_k),
    }
    return post_json("rag/ask", payload, timeout=120)


# ----------------------------
# Utilities
# ----------------------------
def safe_get_extra(msg: dict) -> dict:
    ex = msg.get("extra")
    return ex if isinstance(ex, dict) else {}


def dedup_messages(messages: list[dict]) -> list[dict]:
    """
    Deduplicación defensiva por si ya tienes duplicados en DB.
    Prioriza 'id'; si no, usa (role, content, created_at).
    """
    seen = set()
    out = []
    for m in messages or []:
        mid = m.get("id")
        if mid:
            k = ("id", mid)
        else:
            k = ("sig", m.get("role"), m.get("content"), m.get("created_at"))
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
    return out


def build_history_for_rag(messages: list[dict], max_turns: int = 12) -> list[dict]:
    """
    Envía al backend un history mínimo (role/content).
    max_turns = número de mensajes, no de pares.
    """
    trimmed = (messages or [])[-max_turns:]
    out = []
    for m in trimmed:
        role = m.get("role")
        content = m.get("content")
        if role and content:
            out.append({"role": role, "content": content})
    return out


def extract_artifacts_from_rag(data: dict) -> tuple[list[str], list[str]]:
    """
    Intenta extraer rutas de tablas/imágenes desde:
      - data["tables"], data["images"] (si algún día existen)
      - data["context"][i]["metadata"] con keys variables
    Devuelve: (table_paths, image_paths) como lista de minio keys.
    """
    table_paths: list[str] = []
    image_paths: list[str] = []

    # 1) direct (si existiera)
    t = data.get("tables")
    if isinstance(t, list):
        for x in t:
            if isinstance(x, str) and x not in table_paths:
                table_paths.append(x)

    im = data.get("images")
    if isinstance(im, list):
        for x in im:
            if isinstance(x, str) and x not in image_paths:
                image_paths.append(x)

    # 2) context metadata
    ctx = data.get("context", [])
    if isinstance(ctx, list):
        for c in ctx:
            if not isinstance(c, dict):
                continue
            meta = c.get("metadata") or {}
            if not isinstance(meta, dict):
                continue

            modality = meta.get("modality")

            if modality == "table":
                # intenta varias keys típicas
                for k in ("csv_path", "storage_key", "path", "key"):
                    p = meta.get(k)
                    if isinstance(p, str) and p and p not in table_paths:
                        table_paths.append(p)

            if modality == "image":
                for k in ("image_path", "storage_key", "path", "key"):
                    p = meta.get(k)
                    if isinstance(p, str) and p and p not in image_paths:
                        image_paths.append(p)

    return table_paths, image_paths


def wants_tables_or_images(user_text: str) -> tuple[bool, bool]:
    q = (user_text or "").lower()
    wants_table = any(w in q for w in ["tabla", "tablas", "table", "cuadro", "csv"])
    wants_image = any(w in q for w in ["imagen", "imágenes", "imagenes", "figura", "foto", "gráfico", "grafico", "png", "jpg"])
    return wants_table, wants_image


def conversation_to_markdown(conv_detail: dict) -> str:
    lines = []
    lines.append(f"# {conv_detail.get('title','Conversación')}")
    lines.append("")
    for m in dedup_messages(conv_detail.get("messages", [])):
        role = m.get("role", "unknown")
        content = m.get("content", "")
        lines.append(f"## {role}")
        lines.append(content)
        lines.append("")
        ex = safe_get_extra(m)
        tables = ex.get("tables") or []
        images = ex.get("images") or []
        if tables or images:
            lines.append("### Adjuntos")
            if tables:
                lines.append("- Tablas:")
                for p in tables:
                    lines.append(f"  - {p}")
            if images:
                lines.append("- Imágenes:")
                for p in images:
                    lines.append(f"  - {p}")
            lines.append("")
    return "\n".join(lines)


def render_table_attachment(csv_key: str, key_prefix: str) -> None:
    try:
        b = download_table_bytes(csv_key)
    except Exception as e:
        st.warning(f"No se pudo descargar la tabla: {e}")
        return

    filename = os.path.basename(csv_key) or "table.csv"
    try:
        df = pd.read_csv(io.BytesIO(b))
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception:
        st.info("No se pudo parsear como CSV (mostrando descarga directa).")

    st.download_button(
        "Descargar CSV",
        data=b,
        file_name=filename,
        mime="text/csv",
        key=f"{key_prefix}_dl_{filename}_{uuid.uuid4().hex[:6]}",
    )


def render_image_attachment(img_key: str, key_prefix: str) -> None:
    try:
        b, content_type = download_image_bytes(img_key)
    except Exception as e:
        st.warning(f"No se pudo descargar la imagen: {e}")
        return

    filename = os.path.basename(img_key) or "image"
    # st.image detecta formatos por bytes; content_type se usa para download
    st.image(b, caption=filename, use_container_width=True)

    st.download_button(
        "Descargar imagen",
        data=b,
        file_name=filename,
        mime=content_type or "application/octet-stream",
        key=f"{key_prefix}_dl_{filename}_{uuid.uuid4().hex[:6]}",
    )


# ----------------------------
# Session state init
# ----------------------------
if "page" not in st.session_state:
    st.session_state.page = "Chat"

if "selected_conv_id" not in st.session_state:
    st.session_state.selected_conv_id = None

if "conv_detail" not in st.session_state:
    st.session_state.conv_detail = None

if "auto_show_attachments" not in st.session_state:
    st.session_state.auto_show_attachments = False

if "top_k" not in st.session_state:
    st.session_state.top_k = 5

if "doc_scope" not in st.session_state:
    st.session_state.doc_scope = "all"  # all | selected

if "selected_doc_ids" not in st.session_state:
    st.session_state.selected_doc_ids = []


# ----------------------------
# Sidebar
# ----------------------------
with st.sidebar:
    st.title("ragflow-\nmultimodal")
    st.caption("Asistente RAG multimodal sobre PDFs (texto, tablas, imágenes).")

    page = st.radio("Vista", ["Chat", "Documentos"], index=0 if st.session_state.page == "Chat" else 1)
    st.session_state.page = page

    st.divider()
    st.subheader("Backend health")
    if st.button("Probar conexión"):
        try:
            st.success("Backend OK")
            st.json(backend_health())
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.caption("BACKEND_URL")
    st.code(BACKEND_URL)


# ----------------------------
# Main: Chat
# ----------------------------
if st.session_state.page == "Chat":
    col_left, col_right = st.columns([0.36, 0.64], gap="large")

    with col_left:
        st.header("Chat asistente")
        st.subheader("Conversaciones")

        # load conversations
        try:
            convs = fetch_conversations()
        except Exception as e:
            st.error(f"No se pudieron cargar conversaciones: {e}")
            st.stop()

        # button new conversation
        if st.button("Nueva conversación", use_container_width=True):
            try:
                newc = create_conversation()
                st.session_state.selected_conv_id = newc["id"]
                st.session_state.conv_detail = fetch_conversation_detail(newc["id"])
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo crear: {e}")

        # select conversation
        conv_options = [(c["id"], c.get("title") or str(c["id"])) for c in convs]
        if not conv_options:
            st.info("No hay conversaciones todavía.")
        else:
            id_to_label = {cid: label for cid, label in conv_options}
            default_idx = 0
            if st.session_state.selected_conv_id in id_to_label:
                default_idx = [cid for cid, _ in conv_options].index(st.session_state.selected_conv_id)

            selected_label = st.selectbox(
                "Selecciona conversación",
                options=[id_to_label[cid] for cid, _ in conv_options],
                index=default_idx,
            )
            selected_cid = [cid for cid, label in conv_options if label == selected_label][0]

            if selected_cid != st.session_state.selected_conv_id or st.session_state.conv_detail is None:
                st.session_state.selected_conv_id = selected_cid
                try:
                    st.session_state.conv_detail = fetch_conversation_detail(selected_cid)
                except Exception as e:
                    st.error(f"No se pudo cargar conversación: {e}")
                    st.session_state.conv_detail = None

        conv_detail = st.session_state.conv_detail

        st.subheader("Título")
        if conv_detail:
            new_title = st.text_input("Título", value=conv_detail.get("title", ""))
            if st.button("Guardar título", use_container_width=True):
                try:
                    update_conversation_title(conv_detail["id"], new_title)
                    st.session_state.conv_detail = fetch_conversation_detail(conv_detail["id"])
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo guardar título: {e}")

        st.subheader("Exportar (UI)")
        if conv_detail:
            md = conversation_to_markdown(conv_detail)
            st.download_button(
                "Descargar Markdown",
                data=md.encode("utf-8"),
                file_name=f"conversation_{conv_detail['id']}.md",
                mime="text/markdown",
                use_container_width=True,
            )
            st.download_button(
                "Descargar JSON",
                data=str(conv_detail).encode("utf-8"),
                file_name=f"conversation_{conv_detail['id']}.json",
                mime="application/json",
                use_container_width=True,
            )

        st.subheader("Borrar conversación")
        if conv_detail:
            if st.button("Borrar conversación", type="primary", use_container_width=True):
                try:
                    delete_conversation(conv_detail["id"])
                    st.session_state.selected_conv_id = None
                    st.session_state.conv_detail = None
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo borrar: {e}")

        st.divider()
        st.subheader("Contexto (documentos)")
        st.session_state.auto_show_attachments = st.checkbox(
            "Mostrar tablas/imágenes automáticamente (si el RAG las devuelve)",
            value=st.session_state.auto_show_attachments,
        )
        st.session_state.top_k = st.slider("top_k", 1, 20, int(st.session_state.top_k))

        docs = []
        try:
            docs = fetch_documents()
        except Exception:
            pass

        scope = st.radio("Ámbito", ["Todos", "Seleccionar"], index=0 if st.session_state.doc_scope == "all" else 1)
        st.session_state.doc_scope = "all" if scope == "Todos" else "selected"

        if st.session_state.doc_scope == "selected":
            options = [(d["id"], d.get("original_filename") or d.get("storage_key_original") or str(d["id"])) for d in docs]
            labels = [f"{name} ({did})" for did, name in options]
            selected = st.multiselect("Documentos", options=labels, default=[])
            selected_ids = []
            for lab in selected:
                # extrae id entre paréntesis final
                try:
                    did = lab.split("(")[-1].rstrip(")")
                    selected_ids.append(did)
                except Exception:
                    continue
            st.session_state.selected_doc_ids = selected_ids
        else:
            st.session_state.selected_doc_ids = []

    # ----------------------------
    # Right: chat rendering + input
    # ----------------------------
    with col_right:
        st.subheader("Conversación")

        if not conv_detail:
            st.info("Crea o selecciona una conversación.")
        else:
            msgs = dedup_messages(conv_detail.get("messages", []))

            # Render history
            for i, msg in enumerate(msgs):
                role = msg.get("role", "assistant")
                content = msg.get("content", "")
                with st.chat_message(role):
                    st.markdown(content)

                    ex = safe_get_extra(msg)
                    tables = ex.get("tables") or []
                    images = ex.get("images") or []

                    if tables or images:
                        with st.expander("Adjuntos", expanded=False):
                            if tables:
                                st.markdown("**Tablas**")
                                for t_idx, csv_key in enumerate(tables):
                                    st.markdown(f"- `{csv_key}`")
                                    render_table_attachment(csv_key, key_prefix=f"msg{i}_tbl{t_idx}")
                                    st.divider()
                            if images:
                                st.markdown("**Imágenes**")
                                for im_idx, img_key in enumerate(images):
                                    st.markdown(f"- `{img_key}`")
                                    render_image_attachment(img_key, key_prefix=f"msg{i}_img{im_idx}")
                                    st.divider()

            # Chat input
            user_text = st.chat_input("Escribe tu mensaje…")

            if user_text:
                cid = conv_detail["id"]

                # Render user message optimista (solo visual)
                with st.chat_message("user"):
                    st.markdown(user_text)

                # 1) Persist user message en backend (una sola vez)
                try:
                    add_message(cid, "user", user_text, extra={})
                except Exception as e:
                    st.error(f"No se pudo guardar el mensaje del usuario: {e}")
                    st.stop()

                # 2) Llamar RAG
                # refresca una vez para history consistente (opcional)
                try:
                    fresh = fetch_conversation_detail(cid)
                    base_msgs = dedup_messages(fresh.get("messages", []))
                except Exception:
                    base_msgs = msgs

                history = build_history_for_rag(base_msgs, max_turns=12)

                doc_ids = st.session_state.selected_doc_ids if st.session_state.doc_scope == "selected" else []
                top_k = int(st.session_state.top_k)

                with st.chat_message("assistant"):
                    with st.spinner("Generando respuesta…"):
                        try:
                            rag = rag_ask(user_text, history=history, doc_ids=doc_ids, top_k=top_k)
                        except Exception as e:
                            st.error(f"Error llamando a /rag/ask/: {e}")
                            st.stop()

                        answer = rag.get("answer", "(sin respuesta)")
                        st.markdown(answer)

                        # 3) Extraer artefactos
                        table_paths, image_paths = extract_artifacts_from_rag(rag)

                        # Control de auto-mostrar
                        wants_table, wants_image = wants_tables_or_images(user_text)
                        should_show = st.session_state.auto_show_attachments or wants_table or wants_image

                        if should_show and (table_paths or image_paths):
                            with st.expander("Adjuntos", expanded=True):
                                if table_paths:
                                    st.markdown("**Tablas**")
                                    for t_idx, csv_key in enumerate(table_paths):
                                        st.markdown(f"- `{csv_key}`")
                                        render_table_attachment(csv_key, key_prefix=f"cur_tbl{t_idx}")
                                        st.divider()
                                if image_paths:
                                    st.markdown("**Imágenes**")
                                    for im_idx, img_key in enumerate(image_paths):
                                        st.markdown(f"- `{img_key}`")
                                        render_image_attachment(img_key, key_prefix=f"cur_img{im_idx}")
                                        st.divider()

                # 4) Persist assistant message con extra (IMPORTANTÍSIMO)
                try:
                    add_message(
                        cid,
                        "assistant",
                        answer,
                        extra={"tables": table_paths, "images": image_paths},
                    )
                except Exception as e:
                    st.warning(f"No se pudo guardar el mensaje del asistente: {e}")

                # 5) Rerun: recarga conversación desde backend (evita duplicados)
                try:
                    st.session_state.conv_detail = fetch_conversation_detail(cid)
                except Exception:
                    st.session_state.conv_detail = None
                st.rerun()


# ----------------------------
# Main: Documentos
# ----------------------------
else:
    st.header("Documentos")

    col_a, col_b = st.columns([0.55, 0.45], gap="large")

    with col_a:
        st.subheader("Listado de documentos")
        try:
            docs = fetch_documents()
        except Exception as e:
            st.error(f"No se pudieron cargar documentos: {e}")
            docs = []

        if not docs:
            st.info("No hay documentos.")
        else:
            for d in docs:
                doc_id = d.get("id")
                name = d.get("original_filename") or d.get("storage_key_original") or str(doc_id)
                status_ = d.get("status")

                st.markdown(f"### {name}")
                st.caption(f"id: {doc_id} · status: {status_}")

                c1, c2, c3 = st.columns([0.18, 0.18, 0.18])
                with c1:
                    if st.button("Ver status", key=f"st_{doc_id}"):
                        st.json(d)

                with c2:
                    if st.button("Reindex", key=f"rx_{doc_id}"):
                        try:
                            out = reindex_document(str(doc_id))
                            st.success(out)
                        except Exception as e:
                            st.error(f"Error reindex: {e}")

                with c3:
                    if st.button("Eliminar", key=f"del_{doc_id}"):
                        try:
                            delete_document(str(doc_id))
                            st.success("Eliminado")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error delete: {e}")

                st.divider()

    with col_b:
        st.subheader("Ingestar PDF")
        up = st.file_uploader("Sube un PDF", type=["pdf"])
        if up is not None:
            if st.button("Ingestar PDF", type="primary", use_container_width=True):
                try:
                    out = ingest_document(up.read(), up.name)
                    st.success(out)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error ingest: {e}")
