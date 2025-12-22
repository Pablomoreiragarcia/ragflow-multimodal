def chunk_text(text: str, max_len=500):
    """
    Crea chunks simples de longitud ~500 caracteres.
    """
    chunks = []
    current = []

    words = text.split()

    for word in words:
        current.append(word)
        if len(" ".join(current)) > max_len:
            chunks.append(" ".join(current))
            current = []

    if current:
        chunks.append(" ".join(current))

    return chunks
