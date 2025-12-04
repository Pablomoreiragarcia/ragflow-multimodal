# ragflow-multimodal 🧠

> Graph-based **multimodal RAG** assistant (texto, tablas, imágenes y futuro audio/vídeo) construido con **LangChain**, **LangGraph**, **FastAPI**, **Qdrant**, **MinIO** y **Streamlit**.

`ragflow-multimodal` permite ingestar PDFs, extraer texto, tablas e imágenes, indexarlos en Qdrant usando un modelo CLIP compartido y consultar todo ello a través de un asistente tipo chat que:
- Responde en **castellano**
- Devuelve **referencias a las fuentes** (documento, página, tabla, imagen…)
- Permite **descargar tablas e imágenes** relevantes
- Está pensado para ser **configurable y extensible** (colecciones por tipo de dato, selección de modelos, etc.)

---

## ✨ Características

- 📄 **Ingesta multimodal de PDFs**
  - Extracción de **texto** (PyMuPDF)
  - Extracción de **tablas** (Camelot → CSV en MinIO)
  - Extracción de **imágenes** (PyMuPDF → MinIO)

- 🧩 **Indexación unificada en Qdrant**
  - Texto, filas de tablas e imágenes se vectorizan con el mismo modelo CLIP
  - Colección única `text_chunks` con `modality = text | table | image`
  - Filtros por `doc_id` y modalidad

- 💬 **Asistente tipo chat**
  - Endpoint `/ask` que consulta texto + tablas + imágenes
  - Llama a un modelo OpenAI multimodal (texto + imagen)
  - Devuelve:
    - `answer`
    - `context` (chunks + metadatos: doc_id, página, csv_path, image_path…)
    - `table_path` e `image_path` principales

- 📥 **Gestión de documentos**
  - Endpoint `/documents` para listar documentos
  - `/documents/{doc_id}` para borrar embeddings + ficheros en MinIO
  - `/documents/{doc_id}/reindex` para reprocesar un PDF y reindexarlo

- 🧪 **Evaluación con RAGAS** (work in progress)
  - Módulo `app/eval` con generación de datasets y ejecución de RAGAS

- 🐳 **Infraestructura con Docker Compose**
  - `backend` (FastAPI)
  - `ui` (Streamlit)
  - `qdrant`
  - `minio` + consola de administración

---

## 🏗 Arquitectura (alto nivel)

```text
                ┌─────────────────────────┐
                │       Streamlit UI      │
                │   (ragflow-multimodal)  │
                └─────────────┬───────────┘
                              │ HTTP (REST)
                              ▼
                    ┌───────────────────┐
                    │   FastAPI Backend │
                    │   app/main.py     │
                    └───┬───────────────┘
     ┌──────────────────┼─────────────────────────┐
     │                  │                         │
     ▼                  ▼                         ▼
┌─────────┐      ┌─────────────┐          ┌────────────────┐
│ MinIO   │      │   Qdrant    │          │ OpenAI LLMs    │
│ Storage │      │ Vectorstore │          │ (texto+imagen) │
└─────────┘      └─────────────┘          └────────────────┘
   │ PDFs, CSVs     ▲ embeddings               ▲
   │ imágenes       │ (texto, tablas,          │
   │ metadatos      │  imágenes)               │

