# Placeholder para el grafo real con LangGraph

def run_rag_pipeline(question: str, doc_id: str = None) -> dict:
    """
    Ejecutor del grafo (versión mock hasta que lo implementemos).
    """

    return {
        "final_answer": f"[Mock] Respuesta a: {question}",
        "filtered_chunks": [],
        "reasoning_trace": ["router: mock", "retriever: mock", "answer: mock"]
    }
