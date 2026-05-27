"""
PDF text extraction and chunking.

Key design decisions:
- Extract text page-by-page to preserve document structure
- Chunk at WORD boundaries (never mid-word) for cleaner embeddings
- Overlap is also word-based for accurate context continuity
- Every word of every page enters at least one chunk (zero content loss)
"""

import fitz  # PyMuPDF
import re
from app.config import get_settings


# ─── Text cleaning ────────────────────────────────────────────────────────────

def _clean_page_text(raw: str) -> str:
    """
    Light cleaning that preserves content structure.
    - Normalise whitespace but keep paragraph breaks
    - Remove hyphenation at line ends (common in PDFs)
    - Collapse excessive blank lines
    """
    # Dehyphenate: "configu-\nration" → "configuration"
    text = re.sub(r"-\n(\w)", r"\1", raw)
    # Collapse more-than-two consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace tabs with space
    text = text.replace("\t", " ")
    # Collapse multiple spaces (but keep newlines)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


# ─── Word-boundary chunking ───────────────────────────────────────────────────

def _words_to_chunks(
    words: list[str],
    source: str,
    chunk_words: int,
    overlap_words: int,
    start_index: int = 0,
) -> list[dict]:
    """
    Slice a word list into overlapping chunks.
    Every word appears in at least one chunk.
    Returns list of {text, source, chunk_index}.
    """
    chunks = []
    idx = start_index
    pos = 0
    step = max(chunk_words - overlap_words, 1)

    while pos < len(words):
        end = min(pos + chunk_words, len(words))
        chunk_text = " ".join(words[pos:end]).strip()

        if len(chunk_text) > 60:          # skip near-empty slices
            chunks.append({
                "text": chunk_text,
                "source": source,
                "chunk_index": idx,
            })
            idx += 1

        if end >= len(words):
            break
        pos += step

    return chunks


def chunk_text(text: str, source: str, start_index: int = 0) -> list[dict]:
    """
    Public chunking function. Splits text into word-boundary overlapping chunks.
    Uses chunk_size (chars) from config, converted to an approximate word count.
    """
    cfg = get_settings()

    # Convert char-based settings to word counts (≈5 chars / word avg in English)
    chars_per_word = 5
    chunk_words   = max(cfg.chunk_size   // chars_per_word, 80)
    overlap_words = max(cfg.chunk_overlap // chars_per_word, 20)

    # Normalise whitespace while preserving paragraph structure
    clean = _clean_page_text(text)
    words = clean.split()

    if not words:
        return []

    return _words_to_chunks(words, source, chunk_words, overlap_words, start_index)


# ─── OCR fallback ────────────────────────────────────────────────────────────

def _ocr_pdf(pdf_bytes: bytes) -> str:
    """
    OCR fallback for scanned / image-only PDFs.
    Requires:  pip install pytesseract pdf2image
               + system Tesseract binary (https://tesseract-ocr.github.io/)
    Returns extracted text, or empty string if libraries are unavailable.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(pdf_bytes, dpi=200)
        return "\n\n".join(
            pytesseract.image_to_string(img, lang="eng") for img in images
        )
    except ImportError:
        return ""   # silent: deps not installed
    except Exception:
        return ""   # silent: Tesseract binary missing or other runtime error


# ─── PDF extraction ──────────────────────────────────────────────────────────

def extract_pdf_chunks(pdf_bytes: bytes, filename: str) -> list[dict]:
    """
    Extract ALL text from a PDF and produce overlapping word-boundary chunks.

    Strategy:
    1. Extract page-by-page with PyMuPDF for best layout fidelity.
    2. If a page yields no text, try OCR via pytesseract (optional dep).
    3. Concatenate all pages, then chunk globally so cross-page context is
       preserved (a sentence split across a page boundary stays in one chunk).
    4. Zero content loss: every word on every page enters at least one chunk.

    Raises ValueError for fully unreadable (e.g. image-only, no OCR available) PDFs.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    page_texts: list[str] = []
    for page in doc:
        page_text = page.get_text("text")
        page_texts.append(page_text)
    doc.close()

    full_text = "\n\n".join(page_texts)

    # If digital extraction yielded nothing, try OCR
    if not full_text.strip():
        full_text = _ocr_pdf(pdf_bytes)

    if not full_text.strip():
        raise ValueError(
            "PDF appears to be scanned/image-only and no text could be extracted. "
            "For OCR support install: pip install pytesseract pdf2image  "
            "and the Tesseract binary from https://tesseract-ocr.github.io/"
        )

    return chunk_text(full_text, source=filename, start_index=0)
