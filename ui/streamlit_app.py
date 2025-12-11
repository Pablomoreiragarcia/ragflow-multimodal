import os
import io
import requests
import pandas as pd
import streamlit as st
import uuid
from datetime import datetime

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# ----------------------------
# 🎨 Configuración básica UI
# ----------------------------
st.set_page_config(
    page_title="ragflow-multimodal",
    page_icon="🧠",
    layout="wide",
)

# CSS sencillo para darle un poco de estilo
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        font-size: 0.9rem;
        color: #888;
    }
    .stChatMessage {
        border-radius: 0.6rem;
        padding: 0.4rem 0.6rem;
    }
    .context-block {
        border: 1px solid #33333355;
        border-radius: 0.5rem;
        padding: 0.6rem 0.8rem;
        margin-bottom: 0.6rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------
# 🔁 Estado de sesión
# ----------------------------
if "conversations" not in st.session_state:
    # Estructura: dict id -> conv
    first_id = str(uuid.uuid4())
    st.session_state.conversations = {
        first_id: {
            "id": first_id,
            "title": "Conversación 1",
            "messages": [],        # lista de dicts {role, content, tables, images}
            "doc_ids": None,       # None => todos los documentos
            "scope": "Todos",      # "Todos" | "Seleccionar"
            "created_at": datetime.utcnow().isoformat(),
        }
    }
    st.session_state.active_conversation_id = first_id

# ----------------------------
# 🧭 Sidebar
# ----------------------------
with st.sidebar:
    st.markdown('<div class="main-title">ragflow-multimodal</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle">Asistente RAG multimodal sobre PDFs (texto, tablas, imágenes).</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Selección de vista
    page = st.radio(
        "Vista",
        ["💬 Chat asistente", "📂 Documentos"],
        index=0,
    )

    st.markdown("---")
    st.subheader("Backend health")

    if st.button("Probar conexión"):
        try:
            r = requests.get(f"{BACKEND_URL}/health", timeout=10)
            if r.status_code == 200:
                data = r.json()
                st.success("Backend OK ✅")
                st.json(data)
            else:
                st.error(f"❌ Backend respondió {r.status_code}")
        except Exception as e:
            st.error(f"❌ No se pudo conectar con backend: {e}")


# ----------------------------
# 📚 Utilidades comunes
# ----------------------------
def fetch_documents():
    """Devuelve lista de documentos desde /documents o [] si falla."""
    try:
        resp = requests.get(f"{BACKEND_URL}/documents", timeout=10)
        if resp.status_code != 200:
            st.warning(f"⚠️ No se pudieron obtener documentos: {resp.status_code}")
            return []
        data = resp.json()
        return data.get("documents", [])
    except Exception as e:
        st.warning(f"⚠️ Error llamando a /documents: {e}")
        return []


def render_table_from_csv_path(csv_path: str, key_suffix: str):
    try:
        resp = requests.get(
            f"{BACKEND_URL}/tables/download",
            params={"path": csv_path},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        st.error(f"⚠️ Error descargando tabla: {e}")
        return

    import io
    import pandas as pd

    df = pd.read_csv(io.BytesIO(resp.content))
    render_df_with_download(df, key_suffix)


def render_image_from_path(image_path: str, key_suffix: str = ""):
    """Descarga y muestra una imagen desde /images/download."""
    dl = requests.get(
        f"{BACKEND_URL}/images/download",
        params={"path": image_path},
        timeout=20,
    )

    if not key_suffix:
            key_suffix = str(uuid.uuid4())

    if dl.status_code == 200:
        st.image(dl.content, width='stretch')
        st.download_button(
            label="⬇️ Descargar imagen",
            data=dl.content,
            file_name=image_path.split("/")[-1],
            mime="image/jpeg",
            key=f"img_{image_path}_{key_suffix}",
        )
    else:
        st.error(f"❌ No se pudo obtener la imagen ({dl.status_code})")


def get_active_conversation():
    convs = st.session_state.conversations
    active_id = st.session_state.active_conversation_id
    return convs[active_id]


def create_new_conversation():
    conv_id = str(uuid.uuid4())
    st.session_state.conversations[conv_id] = {
        "id": conv_id,
        "title": "Nueva conversación",
        "messages": [],
        "doc_ids": None,
        "scope": "Todos",
        "created_at": datetime.utcnow().isoformat(),
    }
    st.session_state.active_conversation_id = conv_id


def set_active_conversation(conv_id: str):
    if conv_id in st.session_state.conversations:
        st.session_state.active_conversation_id = conv_id


def normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Asegura que no haya nombres de columna vacíos ni duplicados."""
    new_cols = []
    seen = {}

    for i, col in enumerate(df.columns):
        name = str(col).strip() if col is not None else ""

        if not name:
            name = f"col_{i+1}"

        count = seen.get(name, 0)
        if count > 0:
            name = f"{name}_{count}"

        seen[name] = count + 1
        new_cols.append(name)

    df = df.copy()
    df.columns = new_cols
    return df


def render_df_with_download(df: pd.DataFrame, key_suffix: str):
    df = normalize_headers(df)

    st.dataframe(df, width="stretch")  # sustituye use_container_width
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Descargar tabla en CSV",
        data=csv_bytes,
        file_name=f"tabla_{key_suffix}.csv",
        mime="text/csv",
        key=f"csv_btn_{key_suffix}",
    )


# ----------------------------
# 💬 Página: Chat asistente
# ----------------------------
if page == "💬 Chat asistente":
    st.markdown("## 💬 Chat asistente")

    docs = fetch_documents()
    doc_options = {f"{d.get('original_filename') or d.get('pdf_path', d['doc_id'])}": d["doc_id"] for d in docs}

    # Layout: columna izquierda -> conversaciones, derecha -> chat
    conv_col, chat_col = st.columns([1, 3])

    # ==================================
    # 🧵 Columna IZQUIERDA: conversaciones
    # ==================================
    with conv_col:
        st.markdown("### Conversaciones")

        if st.button("➕ Nueva conversación", width='stretch'):
            create_new_conversation()
            st.rerun()

        st.markdown("---")

        convs = st.session_state.conversations
        active_id = st.session_state.active_conversation_id

        # Orden simple por fecha
        sorted_convs = sorted(
            convs.values(),
            key=lambda c: c["created_at"],
            reverse=True,
        )

        for conv in sorted_convs:
            cid = conv["id"]
            is_active = (cid == active_id)
            title = conv["title"] or "Sin título"
            doc_ids = conv.get("doc_ids")
            doc_label = "Todos los documentos" if not doc_ids else f"{len(doc_ids)} doc(s)"

            if st.button(
                f"{'🟢 ' if is_active else ''}{title}\n{doc_label}",
                key=f"btn_conv_{cid}",
                width='stretch',
            ):
                set_active_conversation(cid)
                st.rerun()

    # ==================================
    # 💬 Columna DERECHA: chat actual
    # ==================================
    with chat_col:
        conv = get_active_conversation()

        # -------- Configuración de RAG por conversación --------
        with st.expander("⚙️ Configuración de la consulta (solo esta conversación)", expanded=True):
            col1, col2 = st.columns([2, 1])

            with col1:
                scope = st.radio(
                    "Ámbito de búsqueda",
                    ["Todos los documentos", "Seleccionar documentos"],
                    horizontal=True,
                    index=0 if conv["scope"] == "Todos" else 1,
                    key=f"scope_{conv['id']}",
                )
                conv["scope"] = "Todos" if scope == "Todos los documentos" else "Seleccionar"

            with col2:
                top_k = st.slider(
                    "top_k (nº de chunks)",
                    min_value=3,
                    max_value=30,
                    value=10,
                    key=f"topk_{conv['id']}",
                )

            selected_doc_ids = None
            if scope == "Seleccionar documentos" and doc_options:
                labels = list(doc_options.keys())
                # Valores por defecto recuperados de la conversación
                current_doc_ids = conv.get("doc_ids") or []
                default_labels = [
                    label for label, did in doc_options.items() if did in current_doc_ids
                ]

                selected_labels = st.multiselect(
                    "Elige documentos para esta conversación",
                    labels,
                    default=default_labels,
                    placeholder="Selecciona uno o varios PDFs",
                    key=f"docs_{conv['id']}",
                )
                selected_doc_ids = [doc_options[l] for l in selected_labels]
                conv["doc_ids"] = selected_doc_ids or None
            else:
                selected_doc_ids = None
                conv["doc_ids"] = None

        st.markdown("---")

        # -------- Historial de mensajes --------
        messages = conv["messages"]
        
        # Índice de la última respuesta del asistente
        last_assistant_idx = None
        for i, m in enumerate(messages):
            if m["role"] == "assistant":
                last_assistant_idx = i

        for idx, msg in enumerate(messages):
            role = msg["role"]
            content = msg["content"]
            tables = msg.get("tables", [])
            images = msg.get("images", [])

            with st.chat_message("user" if role == "user" else "assistant"):
                st.markdown(content)

                # Solo mostrar tablas / imágenes de LA ÚLTIMA respuesta del asistente
                if role == "assistant" and last_assistant_idx is not None and idx == last_assistant_idx:
                    for t_i, csv_path in enumerate(tables):
                        st.markdown("**📊 Tabla relacionada:**")
                        render_table_from_csv_path(
                            csv_path,
                            key_suffix=f"hist_msg{idx}_tbl{t_i}",
                        )

                    for im_i, image_path in enumerate(images):
                        st.markdown("**🖼 Imagen relacionada:**")
                        render_image_from_path(
                            image_path,
                            key_suffix=f"hist_msg{idx}_img{im_i}",
                        )

        # -------- Entrada del usuario --------
        user_input = st.chat_input("Escribe tu pregunta al asistente...")

        if user_input:
            # 1) Añadir mensaje de usuario
            user_msg = {
                "role": "user",
                "content": user_input,
                "tables": [],
                "images": [],
            }
            messages.append(user_msg)

            # 2) Preparar historial simple para el backend
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in messages
                if m["role"] in ("user", "assistant")
            ]
            q_lower = user_input.lower()

            only_flag = any(
                w in q_lower
                for w in ["solo", "sólo", "unicamente", "únicamente", "only", "just"]
            )
            wants_table = any(w in q_lower for w in ["tabla", "table"])
            wants_image = any(
                w in q_lower for w in ["imagen", "image", "figura", "gráfico", "grafico"]
            )

            if only_flag and wants_table and not wants_image:
                allowed_modalities = {"table"}
            elif only_flag and wants_image and not wants_table:
                allowed_modalities = {"image"}
            else:
                # Caso general: mostramos todo lo relevante
                allowed_modalities = {"text", "table", "image"}
            # 3) Llamar a /ask
            with st.chat_message("assistant"):
                with st.spinner("Consultando al backend RAG…"):
                    payload = {
                        "question": user_input,
                        "top_k": top_k,
                        "doc_ids": selected_doc_ids or conv["doc_ids"],
                        "history": history,
                    }

                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/ask",
                            json=payload,
                            timeout=120,
                        )
                    except Exception as e:
                        st.error(f"❌ Error conectando a /ask: {e}")
                        st.stop()

                    if resp.status_code != 200:
                        st.error(f"❌ Error {resp.status_code}")
                        try:
                            st.json(resp.json())
                        except Exception:
                            st.text(resp.text)
                        st.stop()

                    data = resp.json()
                    answer = data.get("answer", "(sin respuesta)")
                    raw_context = data.get("context", [])

                    q_lower = user_input.lower()

                    wants_table = any(w in q_lower for w in ["tabla", "tablas", "table", "cuadro"])
                    wants_image = any(w in q_lower for w in ["imagen", "imágenes", "imagen", "figura", "foto", "gráfico", "grafico"])
                    
                    context = raw_context
                    if wants_table and not wants_image:
                        # Solo mostramos tablas
                        context = [
                            c for c in raw_context
                            if (c.get("metadata", {}) or {}).get("modality") == "table"
                        ]
                    elif wants_image and not wants_table:
                        # Solo mostramos imágenes
                        context = [
                            c for c in raw_context
                            if (c.get("metadata", {}) or {}).get("modality") == "image"
                        ]
                    # 4) Determinar tablas e imágenes usadas
                    tables_to_show: list[str] = []
                    images_to_show: list[str] = []

                    for c in context:
                        meta = c.get("metadata", {}) or {}
                        modality = meta.get("modality", "text")

                        if modality not in allowed_modalities:
                            continue
                        if modality == "table":
                            table_meta = meta.get("table")  # headers + rows
                            csv_path = meta.get("csv_path")
                            tables_to_show.append(
                                {
                                    "csv_path": csv_path,
                                    "table": table_meta,
                                }
                            )

                        if modality == "image":
                            image_path = meta.get("image_path")
                            if image_path and image_path not in images_to_show:
                                images_to_show.append(image_path)
                    
                    def dedup_paths(items, meta_key: str | None = None):
                        """
                        items: lista de strings o dicts.
                        meta_key:
                        - "csv_path" para tablas
                        - "image_path" para imágenes
                        Devuelve siempre una lista de strings (los paths únicos).
                        """
                        seen = set()
                        out: list[str] = []

                        for x in items:
                            if isinstance(x, dict) and meta_key:
                                path = x.get(meta_key)
                            else:
                                path = x

                            if not path:
                                continue

                            if path not in seen:
                                seen.add(path)
                                out.append(path)

                        return out

                    tables_to_show = dedup_paths(tables_to_show, meta_key="csv_path")
                    images_to_show = dedup_paths(images_to_show, meta_key="image_path")


                    # 5) Pintar respuesta + adjuntos (SOLO de esta respuesta)
                    st.markdown(answer)

                    for t_i, csv_path in enumerate(tables_to_show):
                        st.markdown("**📊 Tabla relacionada:**")
                        render_table_from_csv_path(
                            csv_path,
                            key_suffix=f"current_tbl{t_i}",
                        )

                    for im_i, image_path in enumerate(images_to_show):
                        st.markdown("**🖼 Imagen relacionada:**")
                        render_image_from_path(
                            image_path,
                            key_suffix=f"current_img{im_i}",
                        )

            # 6) Guardar mensaje de asistente en la conversación
            assistant_msg = {
                "role": "assistant",
                "content": answer,
                "tables": tables_to_show,
                "images": images_to_show,
            }
            messages.append(assistant_msg)

                    # # 6) Mostrar respuesta principal
                    # st.markdown(answer)

                    # # 7) Mostrar tablas / imágenes de esta respuesta con keys únicos
                    # msg_index = len(messages) - 1
                    # for t_idx, csv_path in enumerate(tables_to_show):
                    #     st.markdown("**📊 Tabla relacionada:**")
                    #     render_table_from_csv_path(
                    #         csv_path,
                    #         key_suffix=f"ans_{msg_index}_{t_idx}",
                    #     )

                    # for i_idx, image_path in enumerate(images_to_show):
                    #     st.markdown("**🖼 Imagen relacionada:**")
                    #     render_image_from_path(
                    #         image_path,
                    #         key_suffix=f"ans_{msg_index}_{i_idx}",
                    #     )
            

            # 8) Actualizar título de la conversación con el primer mensaje
            if conv["title"] == "Nueva conversación" or conv["title"].startswith("Conversación"):
                conv["title"] = user_input[:40] + ("…" if len(user_input) > 40 else "")

            st.rerun()





# ----------------------------
# 📂 Página: Documentos
# ----------------------------
elif page == "📂 Documentos":
    st.markdown("## 📂 Documentos")

    docs = fetch_documents()

    col_list, col_ingest = st.columns([2, 1])

    with col_list:
        st.markdown("### Lista de documentos")

        if not docs:
            st.info("No hay documentos ingestado(s) todavía.")
        else:
            df_docs = pd.DataFrame(docs)
            st.dataframe(df_docs, width='stretch')

            st.markdown("#### Acciones por documento")

            for d in docs:
                doc_id = d["doc_id"]
                pdf_path = d.get("pdf_path", "")
                size = d.get("size", 0)

                cols = st.columns([4, 1, 1])
                name = d.get("original_filename") or doc_id
                with cols[0]:
                    st.markdown(
                        f"**📄 {name}**  \n"
                        f"- doc_id: `{doc_id}`  \n"
                        f"- pdf_path: `{pdf_path}`  \n"
                        f"- Tamaño: **{size} bytes**"
                    )
                with cols[1]:
                    if st.button("🗑 Borrar", key=f"del_{doc_id}"):
                        try:
                            r = requests.delete(
                                f"{BACKEND_URL}/documents/{doc_id}", timeout=120
                            )
                            if r.status_code == 200:
                                st.success(f"Documento {doc_id} borrado.")
                                st.rerun()
                            else:
                                st.error(f"Error borrando {doc_id}: {r.status_code}")
                        except Exception as e:
                            st.error(f"Error llamando a delete: {e}")
                with cols[2]:
                    if st.button("🔄 Reindexar", key=f"re_{doc_id}"):
                        try:
                            r = requests.post(
                                f"{BACKEND_URL}/documents/{doc_id}/reindex",
                                timeout=300,
                            )
                            if r.status_code == 200:
                                st.success(f"Documento {doc_id} reindexado.")
                                st.json(r.json())
                            else:
                                st.error(f"Error reindexando {doc_id}: {r.status_code}")
                        except Exception as e:
                            st.error(f"Error llamando a reindex: {e}")

    with col_ingest:
        st.markdown("### ➕ Ingestar nuevo PDF")

        upl = st.file_uploader("Sube un PDF", type=["pdf"], key="upl_docs")

        if upl and st.button("Ingestar PDF", type="primary"):
            with st.spinner("Procesando PDF... ⏳"):
                files = {"file": (upl.name, upl.getvalue(), "application/pdf")}
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/ingest", files=files, timeout=120
                    )
                    if resp.status_code != 200:
                        st.error(f"❌ Error {resp.status_code}")
                        st.text(resp.text)
                    else:
                        st.success("✅ PDF procesado correctamente")
                        st.json(resp.json())
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Error enviando PDF: {e}")
