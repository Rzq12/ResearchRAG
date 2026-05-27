import fitz  # PyMuPDF
from app.config import get_settings


def chunk_text(text: str, source: str) -> list[dict]:
    """
    Split text into overlapping chunks.
    Returns list of dicts: {text, source, chunk_index}
    """
    cfg = get_settings()
    size = cfg.chunk_size
    overlap = cfg.chunk_overlap

    # Clean whitespace
    text = " ".join(text.split())
    if not text.strip():
        return []

    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end]
        if len(chunk.strip()) > 50:  # skip tiny chunks
            chunks.append({
                "text": chunk.strip(),
                "source": source,
                "chunk_index": idx,
            })
        start += size - overlap
        idx += 1

    return chunks


def extract_pdf_chunks(pdf_bytes: bytes, filename: str) -> list[dict]:
    """
    Extract text from PDF bytes and chunk it.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"
    doc.close()

    if not full_text.strip():
        raise ValueError("PDF appears to be scanned/image-only. No text extracted.")

    return chunk_text(full_text, source=filename)
