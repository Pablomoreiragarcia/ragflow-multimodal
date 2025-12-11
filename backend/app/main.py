# backend/app/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.embeddings.text_embeddings import get_embedding_model
from app.embeddings.image_embeddings import get_clip_model

from app.api.routes_healthcheck import router as health_router
from app.api.routes_rag import router as rag_router
from app.api.routes_query import router as query_router
from app.api.routes_ask import router as ask_router
from app.api.routes_table import router as tables_router
from app.api.routes_images import router as images_router
from app.api.routes_docs import router as docs_router
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# 👉 Este es el objeto ASGI que uvicorn necesita
app = FastAPI(title="ragflow-multimodal backend")

@app.on_event("startup")
async def load_models_on_startup():
    # Fuerza a que se carguen al arrancar
    _ = get_embedding_model()
    _ = get_clip_model()

# CORS para que Streamlit pueda llamar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(rag_router)
app.include_router(query_router)
app.include_router(ask_router)
app.include_router(tables_router)
app.include_router(images_router)
app.include_router(docs_router)


# Opcional: para ejecutar con `python -m app.main`
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)