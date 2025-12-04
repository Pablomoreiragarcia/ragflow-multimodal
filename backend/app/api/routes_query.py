from fastapi import APIRouter
from pydantic import BaseModel
from app.vectorstores.qdrant_client import search_text_chunks

router = APIRouter()

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

@router.post("/query")
def query_documents(req: QueryRequest):
    results = search_text_chunks(req.query, req.top_k)
    return {"results": results}
