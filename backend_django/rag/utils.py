def clip_truncate(model, text: str, max_len: int = 77) -> str:
    """
    Trunca texto a <=77 tokens para CLIP.
    Maneja el caso en el que model.tokenizer sea un CLIPProcessor (imagen+texto),
    extrayendo el tokenizer real de texto en .tokenizer.
    """
    s = str(text).replace("\n", " ").strip()

    tok = getattr(model, "tokenizer", None)
    if tok is not None and hasattr(tok, "tokenizer"):
        tok = tok.tokenizer  # tokenizer de texto real

    if tok is None:
        # fallback conservador
        return " ".join(s.split()[:60])

    enc = tok(s, truncation=True, max_length=max_len, return_tensors="pt")
    return tok.decode(enc["input_ids"][0], skip_special_tokens=True)
