import streamlit as st
import requests
import pandas as pd
import io
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

st.title("📚 Multimodal RAG UI")

# ----------------------------
# ✅ HEALTHCHECK
# ----------------------------
st.subheader("✅ Probar conexión con Backend")

if st.button("Probar backend"):
    try:
        r = requests.get(f"{BACKEND_URL}/health")
        if r.status_code == 200:
            st.success("Backend OK ✅")
            st.json(r.json())
        else:
            st.error(f"❌ Backend respondió {r.status_code}")
    except Exception as e:
        st.error(f"❌ No se pudo conectar con backend: {e}")

# ----------------------------
# ✅ INGEST PDF
# ----------------------------
st.subheader("📄 Probar ingestión de PDF")

upl = st.file_uploader("Sube un PDF", type=["pdf"])

if upl and st.button("Enviar PDF"):
    with st.spinner("Procesando PDF... ⏳"):
        files = {
            "file": (upl.name, upl.getvalue(), "application/pdf")
        }
        try:
            resp = requests.post(f"{BACKEND_URL}/ingest", files=files)

            if resp.status_code != 200:
                st.error(f"❌ Error {resp.status_code}")
                st.text(resp.text)
            else:
                st.success("✅ PDF procesado correctamente")
                try:
                    st.json(resp.json())
                except:
                    st.warning("⚠️ Respuesta no es JSON válido")
                    st.text(resp.text)

        except Exception as e:
            st.error(f"❌ Error enviando PDF: {e}")

# ----------------------------
# ✅ ASK / QUERY
# ----------------------------
st.subheader("🔍 Probar /ask")

try:
    docs_resp = requests.get(f"{BACKEND_URL}/documents")
    if docs_resp.status_code != 200:
        st.error(f"❌ Error obteniendo documentos: {docs_resp.status_code}")
        st.text(docs_resp.text)
        docs = []
    else:
        data = docs_resp.json()
        docs = data.get("documents", [])
except Exception as e:
    st.error(f"❌ Error llamando a /documents: {e}")
    docs = []

doc_options = {f"{d.get('original_filename', d['doc_id'])}": d["doc_id"] for d in docs}

scope = st.sidebar.radio(
    "Ámbito de búsqueda",
    ["Todos los documentos", "Seleccionar documentos"],
)

selected_doc_ids = None
if scope == "Seleccionar documentos" and doc_options:
    labels = list(doc_options.keys())
    selected_labels = st.sidebar.multiselect("Elige documentos", labels)
    selected_doc_ids = [doc_options[l] for l in selected_labels]

    # Botones de gestión
    for l in selected_labels:
        did = doc_options[l]
        if st.sidebar.button(f"🗑 Borrar {l}"):
            requests.delete(f"{BACKEND_URL}/documents/{did}")
        if st.sidebar.button(f"🔄 Reindexar {l}"):
            requests.post(f"{BACKEND_URL}/documents/{did}/reindex")

question = st.text_input("Escribe tu pregunta")

if st.button("Preguntar"):
    if not question.strip():
        st.warning("⚠️ Escribe una pregunta.")
    else:
        try:
            resp = requests.post(
                f"{BACKEND_URL}/ask",
                json={"question": question, "top_k": 10, "doc_ids": selected_doc_ids}
            )

            if resp.status_code != 200:
                st.error(f"❌ Error {resp.status_code}")
                st.text(resp.text)
            else:
                data = resp.json()

                st.write("💬 Respuesta:")
                st.success(data.get("answer", "(sin respuesta)"))

                st.write("📚 Contexto usado:")
                context = data.get("context", [])

                if not context:
                    st.info("⚠️ No se devolvió contexto.")
                else:

                    shown_tables = set()

                    for c in context:
                        st.write("-", c.get("content", "(vacío)"))

                        # ✅ Si es tabla, mostrarla
                        metadata = c.get("metadata", {})
                        csv_path = metadata.get("csv_path")

                        if csv_path and csv_path not in shown_tables:
                            shown_tables.add(csv_path)

                            st.write("📊 Tabla encontrada:")

                            # 1) Recuperar tabla del backend
                            dl = requests.get(
                                f"{BACKEND_URL}/tables/download",
                                params={"path": csv_path}
                            )

                            if dl.status_code == 200:
                                df = pd.read_csv(io.BytesIO(dl.content))
                                st.dataframe(df)

                                # ✅ 3) Botón para descargar CSV
                                st.download_button(
                                    label="⬇️ Descargar tabla en CSV",
                                    data=dl.content,
                                    file_name=csv_path.split("/")[-1],
                                    mime="text/csv",
                                    key=csv_path
                                )
                            else:
                                st.error("❌ No se pudo obtener la tabla.")

                        if metadata.get("modality") == "image":
                            st.write("🖼 Imagen encontrada:")

                            # Descargar imagen
                            dl = requests.get(f"{BACKEND_URL}/images/download", params={"path": metadata["image_path"]})

                            if dl.status_code == 200:
                                st.image(dl.content)

                                st.download_button(
                                    label="⬇️ Descargar imagen",
                                    data=dl.content,
                                    file_name=metadata["image_path"].split("/")[-1],
                                    mime="image/jpeg",
                                    key=f"img_{metadata['image_path']}"
                                )
                            else:
                                st.error("❌ No pude cargar la imagen")
        except Exception as e:
            st.error(f"❌ Error conectando a /ask: {e}")
