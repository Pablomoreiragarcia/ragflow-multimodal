import fitz  # PyMuPDF


def extract_text_from_pdf(pdf_bytes: bytes):
    """
    Devuelve: lista de dicts por página:
    [
       {"page": 0, "text": "texto..."},
       ...
    ]
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        pages.append({"page": i, "text": text})

    return pages
