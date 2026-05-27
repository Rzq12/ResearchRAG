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


def _ocr_pdf(pdf_bytes: bytes) -> str:
    """
    Fallback OCR for scanned/image-only PDFs.
    Requires: pytesseract + pdf2image + system Tesseract binary.
    Returns extracted text, or empty string if OCR is unavailable.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(pdf_bytes, dpi=200)
        texts = []
        for img in images:
            text = pytesseract.image_to_string(img, lang="eng")
            texts.append(text)
        return "\n".join(texts)

    except ImportError:
        # pytesseract or pdf2image not installed — silent fallback
        return ""
    except Exception:
        # Tesseract binary not found or other runtime error
        return ""


def extract_pdf_chunks(pdf_bytes: bytes, filename: str) -> list[dict]:
    """
    Extract text from PDF bytes and chunk it.
    For scanned/image-only PDFs, automatically falls back to OCR
    (requires pytesseract + pdf2image + Tesseract to be installed).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"
    doc.close()

    if not full_text.strip():
        # Try OCR fallback
        full_text = _ocr_pdf(pdf_bytes)

    if not full_text.strip():
        raise ValueError(
            "PDF appears to be scanned/image-only and no text could be extracted. "
            "Install Tesseract + pytesseract + pdf2image for OCR support: "
            "`pip install pytesseract pdf2image` and install Tesseract from https://tesseract-ocr.github.io/"
        )

    return chunk_text(full_text, source=filename)
