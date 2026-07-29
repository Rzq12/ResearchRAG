"""
Advanced PDF chunking pipeline for ResearchRAG.

Strategy: Hierarchical + Layout-Aware + Parent-Child retrieval.

Flow:
  PDF bytes
    → per-page layout analysis (PyMuPDF blocks)
    → table extraction (pdfplumber)
    → block classification (title/heading/text/table/formula/image/list/footnote)
    → hierarchy tracking (section_path)
    → child chunks  (~180 words, for embedding)
    → parent chunks (~700 words, for LLM context)
    → coverage verification + fallback for missing pages
    → CoverageReport

Zero content loss: every page has at least one chunk (child + parent).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple

import fitz  # PyMuPDF

from app.config import get_settings


# ─── Enums & Dataclasses ─────────────────────────────────────────────────────

class ContentType(str, Enum):
    TITLE        = "title"
    HEADING      = "heading"
    SUBHEADING   = "subheading"
    TEXT         = "text"
    TABLE        = "table"
    FORMULA      = "formula"
    IMAGE_CAPTION = "image_caption"
    LIST         = "list"
    FOOTNOTE     = "footnote"
    FALLBACK_PAGE = "fallback_page"


@dataclass
class RawBlock:
    """One layout block extracted from a single PDF page."""
    page_num:     int            # 1-indexed
    content_type: ContentType
    text:         str
    bbox:         tuple[float, float, float, float]  # (x0, y0, x1, y1) normalised 0-1
    font_size:    float
    is_bold:      bool
    section_path: str = ""       # filled by build_hierarchy()
    section_title: str = ""      # immediate heading label


@dataclass
class DocumentChunk:
    """Output chunk ready for ChromaDB ingestion."""
    chunk_id:      str
    chunk_role:    str           # "child" | "parent"
    text:          str
    source:        str           # filename
    page_num:      int
    content_type:  str
    chunk_index:   int
    parent_id:     str | None    # child → parent_id; parent → None
    section_path:  str
    section_title: str
    word_count:    int
    # Fingerprint of the source document's bytes. Chunk ids are derived from it,
    # so editing a PDF and re-uploading it under the same filename produces
    # different ids instead of colliding with (and being discarded as) the old
    # revision. Stored in metadata so ingestion can detect a superseded version.
    doc_fp:        str = ""

    def to_metadata(self) -> dict:
        return {
            "chunk_role":    self.chunk_role,
            "source":        "upload",
            "filename":      self.source,
            "title":         self.source.replace(".pdf", ""),
            "doc_fp":        self.doc_fp,
            "authors":       "Uploaded by user",
            "published":     "N/A",
            "url":           "",
            "chunk_index":   self.chunk_index,
            "page_num":      self.page_num,
            "content_type":  self.content_type,
            "section_path":  self.section_path,
            "section_title": self.section_title,
            "section_label": section_label(self.section_title, self.section_path),
            "word_count":    self.word_count,
            "parent_id":     self.parent_id or "",
        }


class CoverageReport(NamedTuple):
    total_pages:   int
    covered_pages: int
    missing_pages: list[int]
    coverage_pct:  float
    child_chunks:  int
    parent_chunks: int
    fallback_used: int


# ─── Helpers ─────────────────────────────────────────────────────────────────

# Canonical academic-section labels (the domain analogue of the legal
# notebook's pasal/BAB metadata). Multilingual: English + Indonesian headings.
# Order matters — first match wins, checked against title then path.
_SECTION_LABEL_PATTERNS: list[tuple[str, "re.Pattern"]] = [
    ("abstract",     re.compile(r"abstract|abstrak|ringkasan", re.IGNORECASE)),
    ("introduction", re.compile(r"introduction|pendahuluan|latar belakang|\bbackground\b", re.IGNORECASE)),
    ("related_work", re.compile(r"related work|literature review|tinjauan pustaka|kajian pustaka", re.IGNORECASE)),
    ("methods",      re.compile(r"method|metode|metodologi|approach|pendekatan|materials|experimental setup", re.IGNORECASE)),
    ("results",      re.compile(r"result|hasil|finding|temuan|experiment|eksperimen|evaluation|evaluasi", re.IGNORECASE)),
    ("discussion",   re.compile(r"discussion|pembahasan|diskusi|analysis|analisis", re.IGNORECASE)),
    ("conclusion",   re.compile(r"conclusion|kesimpulan|penutup|\bsummary\b|future work", re.IGNORECASE)),
    ("references",   re.compile(r"references|bibliography|daftar pustaka", re.IGNORECASE)),
]


def section_label(section_title: str, section_path: str = "") -> str:
    """Map a free-form heading to a canonical section label ('other' if unknown)."""
    for text in (section_title, section_path):
        if not text:
            continue
        for label, pattern in _SECTION_LABEL_PATTERNS:
            if pattern.search(text):
                return label
    return "other"


_FORMULA_PATTERN = re.compile(
    r"[∑∫∏∂∇∆√±×÷≤≥≠≈∞αβγδεζηθιλμνξπρστφχψω]"
    r"|\\frac|\\sum|\\int|\\prod|\\alpha|\\beta"
    r"|\b[A-Za-z]\s*=\s*[A-Za-z0-9\+\-\*/\(\)]",
    re.UNICODE,
)

_LIST_PATTERN = re.compile(r"^\s*(?:[\•\-\*]|\d+[\.\)]|[a-zA-Z][\.\)])\s+")

_FOOTNOTE_PATTERN = re.compile(r"^\s*(?:\d+|[\*†‡§¶])\s+[A-Z]")


def _stable_id(*parts: str) -> str:
    raw = "::".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()


def document_fingerprint(pdf_bytes: bytes) -> str:
    """
    Short content hash identifying one revision of a document.

    Chunk ids are derived from this rather than from the filename alone. Without
    it, re-uploading a corrected paper under its original name produced
    identical ids, every chunk was treated as an existing duplicate and skipped,
    and the knowledge base kept answering from the superseded text — silently.
    """
    return hashlib.sha256(pdf_bytes).hexdigest()[:16]


def _clean_text(raw: str) -> str:
    """Light cleaning preserving paragraph structure."""
    text = re.sub(r"-\n(\w)", r"\1", raw)           # dehyphenate
    text = re.sub(r"\n{3,}", "\n\n", text)           # collapse blank lines
    text = text.replace("\t", " ")
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


def _word_count(text: str) -> int:
    return len(text.split())


# ─── Step 1: Layout Analysis ──────────────────────────────────────────────────

def _analyze_page_layout(page: fitz.Page, page_num: int) -> list[RawBlock]:
    """Extract typed RawBlocks from a single PDF page."""
    pw, ph = page.rect.width, page.rect.height
    if pw == 0 or ph == 0:
        return []

    raw_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    blocks_raw = raw_dict.get("blocks", [])

    # Collect all font sizes to compute page average (for heading detection)
    font_sizes: list[float] = []
    for b in blocks_raw:
        if b.get("type") == 0:  # text block
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("size", 0) > 4:
                        font_sizes.append(span["size"])

    avg_font = sum(font_sizes) / len(font_sizes) if font_sizes else 11.0
    page_bottom_threshold = ph * 0.88  # footnote zone

    out: list[RawBlock] = []

    for b in blocks_raw:
        btype = b.get("type", 0)

        # Image block
        if btype == 1:
            # Try to find caption: text near this image
            # We'll handle captions in a post-processing pass
            continue

        if btype != 0:
            continue

        lines = b.get("lines", [])
        if not lines:
            continue

        # Dominant span properties for the block
        dominant_size = 11.0
        dominant_bold = False
        block_texts: list[str] = []

        for line in lines:
            spans = line.get("spans", [])
            for span in spans:
                sz = span.get("size", 11.0)
                if sz > dominant_size:
                    dominant_size = sz
                flags = span.get("flags", 0)
                if flags & 2**4:  # bold bit
                    dominant_bold = True
                block_texts.append(span.get("text", ""))

        raw_text = " ".join(block_texts)
        text = _clean_text(raw_text)
        if not text or len(text) < 3:
            continue

        # Normalised bbox
        x0, y0, x1, y1 = b["bbox"]
        bbox = (x0 / pw, y0 / ph, x1 / pw, y1 / ph)

        # Classify content type
        ctype = _classify_block(
            text, dominant_size, avg_font, dominant_bold,
            y0, page_bottom_threshold
        )

        out.append(RawBlock(
            page_num=page_num,
            content_type=ctype,
            text=text,
            bbox=bbox,
            font_size=dominant_size,
            is_bold=dominant_bold,
        ))

    return out


def _classify_block(
    text: str,
    font_size: float,
    avg_font: float,
    is_bold: bool,
    y0: float,
    bottom_threshold: float,
) -> ContentType:
    """Rule-based block type classification."""
    wc = _word_count(text)

    # Very large font → document title (usually first page)
    if font_size >= avg_font * 1.6 and wc <= 20:
        return ContentType.TITLE

    # Heading: large font OR bold+short
    if font_size >= avg_font * 1.15 and wc <= 30:
        return ContentType.HEADING

    if is_bold and wc <= 20 and font_size >= avg_font * 1.05:
        return ContentType.SUBHEADING

    # Footnote: small font near bottom
    if font_size < avg_font * 0.85 and y0 >= bottom_threshold:
        if _FOOTNOTE_PATTERN.match(text):
            return ContentType.FOOTNOTE

    # Formula
    if _FORMULA_PATTERN.search(text) and wc < 60:
        return ContentType.FORMULA

    # List items
    if _LIST_PATTERN.match(text):
        return ContentType.LIST

    return ContentType.TEXT


# ─── Step 2: Table Extraction ────────────────────────────────────────────────

def _extract_tables(pdf_bytes: bytes) -> dict[int, list[str]]:
    """
    Use pdfplumber to extract tables as Markdown strings.
    Returns {page_num (1-indexed): [markdown_table, ...]}.
    """
    try:
        import pdfplumber
    except ImportError:
        return {}

    tables_by_page: dict[int, list[str]] = {}
    try:
        with pdfplumber.open_pdf_from_bytes(pdf_bytes) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                page_tables = page.extract_tables()
                if not page_tables:
                    continue
                md_tables = []
                for table in page_tables:
                    if not table:
                        continue
                    md = _table_to_markdown(table)
                    if md:
                        md_tables.append(md)
                if md_tables:
                    tables_by_page[i] = md_tables
    except Exception:
        pass
    return tables_by_page


def _extract_tables_pdfplumber(pdf_bytes: bytes) -> dict[int, list[str]]:
    """Wrapper that tries pdfplumber.open() API variants."""
    import io
    try:
        import pdfplumber
    except ImportError:
        return {}

    tables_by_page: dict[int, list[str]] = {}
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                raw_tables = page.extract_tables()
                if not raw_tables:
                    continue
                md_tables = [_table_to_markdown(t) for t in raw_tables if t]
                md_tables = [m for m in md_tables if m]
                if md_tables:
                    tables_by_page[i] = md_tables
    except Exception:
        pass
    return tables_by_page


def _table_to_markdown(table: list[list]) -> str:
    """Convert a pdfplumber table (list of rows) to Markdown."""
    if not table:
        return ""
    rows = []
    for row in table:
        cells = [str(c).replace("\n", " ").strip() if c is not None else "" for c in row]
        rows.append("| " + " | ".join(cells) + " |")

    if len(rows) >= 2:
        # Insert separator after header
        col_count = len(table[0])
        separator = "| " + " | ".join(["---"] * col_count) + " |"
        rows.insert(1, separator)

    return "\n".join(rows)


# ─── Step 3: Hierarchy Builder ────────────────────────────────────────────────

def _build_hierarchy(blocks: list[RawBlock]) -> list[RawBlock]:
    """
    Walk blocks in document order and assign section_path/section_title.
    Tracks chapter → section → subsection independently.
    """
    chapter    = ""
    section    = ""
    subsection = ""

    for b in blocks:
        ct = b.content_type

        if ct == ContentType.TITLE:
            chapter    = b.text[:80]
            section    = ""
            subsection = ""

        elif ct == ContentType.HEADING:
            section    = b.text[:80]
            subsection = ""

        elif ct == ContentType.SUBHEADING:
            subsection = b.text[:80]

        parts = [p for p in [chapter, section, subsection] if p]
        b.section_path  = " > ".join(parts)
        b.section_title = parts[-1] if parts else ""

    return blocks


# ─── Step 4: Child Chunk Generation ──────────────────────────────────────────

def _make_child_chunks(
    blocks: list[RawBlock],
    table_blocks: list[RawBlock],
    source: str,
    doc_fp: str = "",
) -> list[DocumentChunk]:
    """
    Produce child chunks (~180 words each, word-boundary aligned).
    Tables are always one chunk each (no splitting).
    Headings are prepended to the next text block for context.
    """
    cfg = get_settings()
    target_words   = cfg.child_chunk_words        # 180
    overlap_words  = cfg.child_chunk_overlap_words  # 30

    chunks: list[DocumentChunk] = []
    idx = 0

    # Merge table_blocks into blocks at correct positions
    all_blocks = sorted(blocks + table_blocks, key=lambda b: (b.page_num, b.bbox[1]))

    # Group blocks into runs for sliding window
    # Tables → immediate single chunk; other types → word-window
    pending_words: list[str] = []
    pending_page  = 1
    pending_section_path  = ""
    pending_section_title = ""
    pending_ctype = ContentType.TEXT
    last_heading  = ""

    def _flush_pending() -> None:
        nonlocal pending_words, idx
        if not pending_words:
            return
        step = max(target_words - overlap_words, 1)
        pos  = 0
        while pos < len(pending_words):
            end   = min(pos + target_words, len(pending_words))
            text  = " ".join(pending_words[pos:end]).strip()
            wc    = end - pos
            if wc >= 10 and text:
                cid = _stable_id(source, doc_fp, "child", str(idx))
                chunks.append(DocumentChunk(
                    chunk_id      = cid,
                    chunk_role    = "child",
                    text          = text,
                    source        = source,
                    page_num      = pending_page,
                    content_type  = pending_ctype.value,
                    chunk_index   = idx,
                    parent_id     = None,   # filled in make_parent_chunks
                    section_path  = pending_section_path,
                    section_title = pending_section_title,
                    word_count    = wc,
                    doc_fp        = doc_fp,
                ))
                idx += 1
            if end >= len(pending_words):
                break
            pos += step
        pending_words.clear()

    for block in all_blocks:
        ct = block.content_type

        # --- Table: always its own chunk ---
        if ct == ContentType.TABLE:
            _flush_pending()
            text = block.text.strip()
            wc   = _word_count(text)
            if text:
                cid = _stable_id(source, doc_fp, "child", str(idx))
                chunks.append(DocumentChunk(
                    chunk_id      = cid,
                    chunk_role    = "child",
                    text          = text,
                    source        = source,
                    page_num      = block.page_num,
                    content_type  = ContentType.TABLE.value,
                    chunk_index   = idx,
                    parent_id     = None,
                    section_path  = block.section_path,
                    section_title = block.section_title,
                    word_count    = wc,
                    doc_fp        = doc_fp,
                ))
                idx += 1
            continue

        # --- Heading/subheading: remember for context prefix ---
        if ct in (ContentType.TITLE, ContentType.HEADING, ContentType.SUBHEADING):
            _flush_pending()
            last_heading = block.text.strip()
            # Update pending metadata
            pending_section_path  = block.section_path
            pending_section_title = block.section_title
            pending_page          = block.page_num
            # Add heading text as seed words for next chunk (context)
            pending_words = block.text.split()
            pending_ctype = ContentType.HEADING
            continue

        # --- Normal text / formula / list / footnote ---
        if pending_section_path != block.section_path and block.section_path:
            _flush_pending()
        pending_page          = block.page_num
        pending_section_path  = block.section_path or pending_section_path
        pending_section_title = block.section_title or pending_section_title
        pending_ctype         = ct
        pending_words.extend(block.text.split())

    _flush_pending()
    return chunks


# ─── Step 5: Parent Chunk Generation ─────────────────────────────────────────

def _make_parent_chunks(
    children: list[DocumentChunk],
    source: str,
    doc_fp: str = "",
) -> tuple[list[DocumentChunk], list[DocumentChunk]]:
    """
    Group children_per_parent child chunks into one parent chunk.
    Returns (updated_children_with_parent_ids, parent_chunks).
    """
    cfg = get_settings()
    group_size = cfg.children_per_parent  # default 4

    parents:  list[DocumentChunk] = []
    children_out: list[DocumentChunk] = []

    for gi, start in enumerate(range(0, len(children), group_size)):
        group = children[start : start + group_size]

        parent_text   = "\n\n".join(c.text for c in group)
        parent_page   = group[0].page_num
        parent_sec    = group[0].section_path
        parent_title  = group[0].section_title
        parent_wc     = sum(c.word_count for c in group)

        pid = _stable_id(source, doc_fp, "parent", str(gi))

        parent = DocumentChunk(
            chunk_id      = pid,
            chunk_role    = "parent",
            text          = parent_text,
            source        = source,
            page_num      = parent_page,
            content_type  = ContentType.TEXT.value,
            chunk_index   = gi,
            parent_id     = None,
            section_path  = parent_sec,
            section_title = parent_title,
            word_count    = parent_wc,
            doc_fp        = doc_fp,
        )
        parents.append(parent)

        for child in group:
            # Create new dataclass instance with parent_id set
            children_out.append(DocumentChunk(
                chunk_id      = child.chunk_id,
                chunk_role    = child.chunk_role,
                text          = child.text,
                source        = child.source,
                page_num      = child.page_num,
                content_type  = child.content_type,
                chunk_index   = child.chunk_index,
                parent_id     = pid,
                section_path  = child.section_path,
                section_title = child.section_title,
                word_count    = child.word_count,
                doc_fp        = doc_fp,
            ))

    return children_out, parents


# ─── Step 6: Coverage Verification + Fallback ────────────────────────────────

def _verify_coverage(
    children: list[DocumentChunk],
    total_pages: int,
) -> tuple[set[int], CoverageReport]:
    """Check which pages are covered; return missing pages."""
    covered = {c.page_num for c in children}
    missing = sorted(set(range(1, total_pages + 1)) - covered)
    pct = round(len(covered) / total_pages * 100, 1) if total_pages else 0.0
    return covered, CoverageReport(
        total_pages   = total_pages,
        covered_pages = len(covered),
        missing_pages = missing,
        coverage_pct  = pct,
        child_chunks  = len(children),
        parent_chunks = 0,   # filled later
        fallback_used = len(missing),
    )


def _fallback_page_chunks(
    pdf_bytes: bytes,
    missing_pages: list[int],
    source: str,
    start_index: int,
    doc_fp: str = "",
) -> list[DocumentChunk]:
    """
    For pages without any chunk, extract raw page text as a single fallback chunk.
    Tries OCR if digital extraction yields nothing.
    """
    doc    = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks = []
    idx    = start_index

    for page_num in missing_pages:
        if page_num < 1 or page_num > len(doc):
            continue
        page = doc[page_num - 1]
        text = _clean_text(page.get_text("text"))

        if not text:
            text = _ocr_page(page)

        if not text:
            text = f"[Page {page_num}: no extractable content]"

        cid = _stable_id(source, doc_fp, "fallback", str(page_num))
        chunks.append(DocumentChunk(
            chunk_id      = cid,
            chunk_role    = "child",
            text          = text,
            source        = source,
            page_num      = page_num,
            content_type  = ContentType.FALLBACK_PAGE.value,
            chunk_index   = idx,
            parent_id     = None,
            section_path  = "",
            section_title = f"Page {page_num} (fallback)",
            word_count    = _word_count(text),
            doc_fp        = doc_fp,
        ))
        idx += 1

    doc.close()
    return chunks


def _ocr_page(page: fitz.Page) -> str:
    """OCR a single fitz page. Returns empty string if unavailable."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        pix  = page.get_pixmap(dpi=200)
        data = pix.tobytes("png")
        from PIL import Image
        import io
        img  = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(img, lang="eng")
    except Exception:
        return ""


# ─── Step 7: OCR Fallback (full PDF) ─────────────────────────────────────────

def _ocr_pdf(pdf_bytes: bytes) -> str:
    """OCR entire PDF. Returns empty string if unavailable."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(pdf_bytes, dpi=200)
        return "\n\n".join(
            pytesseract.image_to_string(img, lang="eng") for img in images
        )
    except Exception:
        return ""


# ─── Public API ───────────────────────────────────────────────────────────────

def extract_pdf_chunks_advanced(
    pdf_bytes: bytes,
    filename: str,
) -> tuple[list[DocumentChunk], list[DocumentChunk], CoverageReport]:
    """
    Full pipeline: layout analysis → table extraction → hierarchy → child + parent chunks
    → coverage verification → fallback for missing pages.

    Returns:
        (child_chunks, parent_chunks, coverage_report)

    Raises:
        ValueError  if PDF has no extractable text AND no OCR available.
    """
    # 0a. Fingerprint the exact bytes. Every chunk id derives from this, so a
    #     revised PDF uploaded under the same filename yields new ids instead of
    #     colliding with the previous revision and being discarded as duplicate.
    doc_fp = document_fingerprint(pdf_bytes)

    # 0b. Open document to get total pages
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    # 1. Per-page layout analysis
    all_blocks: list[RawBlock] = []
    has_any_text = False

    for page in doc:
        page_num   = page.number + 1  # 1-indexed
        page_blocks = _analyze_page_layout(page, page_num)
        all_blocks.extend(page_blocks)
        if page_blocks:
            has_any_text = True

    doc.close()

    # 2. If digital extraction failed → OCR whole PDF
    if not has_any_text:
        ocr_text = _ocr_pdf(pdf_bytes)
        if not ocr_text.strip():
            raise ValueError(
                "PDF appears to be image-only and text extraction failed. "
                "Install Tesseract + pytesseract + pdf2image for OCR support."
            )
        # Treat OCR result as one big text block per page
        # (We don't have page-level OCR here, so assign all to page 1 and chunk)
        all_blocks = [RawBlock(
            page_num=1, content_type=ContentType.TEXT,
            text=ocr_text, bbox=(0, 0, 1, 1), font_size=11, is_bold=False,
        )]
        total_pages = max(total_pages, 1)

    # 3. Table extraction (pdfplumber)
    tables_by_page = _extract_tables_pdfplumber(pdf_bytes)
    table_blocks: list[RawBlock] = []
    for page_num, md_tables in tables_by_page.items():
        # Find section context from surrounding blocks
        nearby = [b for b in all_blocks if b.page_num == page_num]
        sec_path  = nearby[-1].section_path  if nearby else ""
        sec_title = nearby[-1].section_title if nearby else ""
        for md in md_tables:
            table_blocks.append(RawBlock(
                page_num      = page_num,
                content_type  = ContentType.TABLE,
                text          = md,
                bbox          = (0.0, 0.5, 1.0, 0.9),
                font_size     = 10.0,
                is_bold       = False,
                section_path  = sec_path,
                section_title = sec_title,
            ))

    # 4. Build heading hierarchy
    all_blocks = _build_hierarchy(all_blocks)

    # 5. Child chunks
    children = _make_child_chunks(all_blocks, table_blocks, filename, doc_fp)

    # 6. Coverage verification
    _, report_pre = _verify_coverage(children, total_pages)

    # 7. Fallback chunks for uncovered pages
    fallbacks: list[DocumentChunk] = []
    if report_pre.missing_pages:
        fallbacks = _fallback_page_chunks(
            pdf_bytes, report_pre.missing_pages, filename,
            start_index=len(children), doc_fp=doc_fp,
        )
        children.extend(fallbacks)

    # 8. Parent chunks
    children_linked, parents = _make_parent_chunks(children, filename, doc_fp)

    # 9. Final report
    covered_pages = {c.page_num for c in children_linked}
    missing_final = sorted(set(range(1, total_pages + 1)) - covered_pages)
    pct = round(len(covered_pages) / total_pages * 100, 1) if total_pages else 0.0
    report = CoverageReport(
        total_pages   = total_pages,
        covered_pages = len(covered_pages),
        missing_pages = missing_final,
        coverage_pct  = pct,
        child_chunks  = len(children_linked),
        parent_chunks = len(parents),
        fallback_used = len(fallbacks),
    )

    return children_linked, parents, report


# ─── Legacy compatibility (used by OpenAlex abstract chunking) ────────────────

def chunk_text(text: str, source: str, start_index: int = 0) -> list[dict]:
    """
    Simple word-boundary chunking for short texts (abstracts, etc.).
    Returns list of dicts compatible with the old API.
    """
    cfg = get_settings()
    chars_per_word = 5
    chunk_words    = max(cfg.chunk_size // chars_per_word, 80)
    overlap_words  = max(cfg.chunk_overlap // chars_per_word, 20)

    text = _clean_text(text)
    words = text.split()
    if not words:
        return []

    chunks   = []
    step     = max(chunk_words - overlap_words, 1)
    pos, idx = 0, start_index

    while pos < len(words):
        end  = min(pos + chunk_words, len(words))
        ct   = " ".join(words[pos:end]).strip()
        wc   = end - pos
        if ct and wc >= 10:
            chunks.append({"text": ct, "source": source, "chunk_index": idx})
            idx += 1
        if end >= len(words):
            break
        pos += step

    return chunks


# ─── Convenience: simple extract for backward-compat (no parent-child) ────────

def extract_pdf_chunks(pdf_bytes: bytes, filename: str) -> list[dict]:
    """
    Backward-compatible entry point used by existing pdf_service.py.
    Delegates to the advanced pipeline; returns flat list[dict] of child chunks.
    """
    children, _, _ = extract_pdf_chunks_advanced(pdf_bytes, filename)
    return [
        {
            "text":          c.text,
            "source":        c.source,
            "chunk_index":   c.chunk_index,
            "page_num":      c.page_num,
            "content_type":  c.content_type,
            "section_path":  c.section_path,
            "section_title": c.section_title,
            "parent_id":     c.parent_id or "",
            "chunk_role":    c.chunk_role,
        }
        for c in children
    ]
