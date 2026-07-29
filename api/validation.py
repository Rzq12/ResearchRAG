"""
Upload validation.

The PDF parsers (PyMuPDF, pdfplumber) are C extensions fed entirely
attacker-controlled bytes. Before anything reaches them we check that the
payload is bounded and actually looks like a PDF, and we translate every
failure into a 422 rather than letting an exception become a 500.

Audit reproductions this closes:
    - empty file named .pdf        → was 500, now 422
    - text file renamed to .pdf    → was 500, now 422
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings

# Every PDF begins with "%PDF-" per ISO 32000. Some generators emit a few junk
# bytes first, so we scan a small prefix rather than demanding offset 0.
_PDF_MAGIC = b"%PDF-"
_MAGIC_SEARCH_WINDOW = 1024

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",  # some browsers send this for drag-and-drop
    "",  # curl/multipart without an explicit type
}


def _reject(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


async def read_validated_pdf(file: UploadFile) -> bytes:
    """
    Read an uploaded file, enforcing size, declared type and magic bytes.

    Returns the raw bytes when valid; raises 413 (too large) or 422 (anything
    else) so the client always gets an actionable, non-5xx answer.
    """
    cfg = get_settings()
    max_bytes = cfg.max_upload_mb * 1024 * 1024

    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared not in _ALLOWED_CONTENT_TYPES:
        raise _reject(f"Unsupported content type '{declared}'. Only PDF files are accepted.")

    content = await file.read()

    if not content:
        raise _reject("The uploaded file is empty.")

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {cfg.max_upload_mb} MB limit.",
        )

    # Content sniffing — the filename and declared type are both client-supplied
    # and therefore untrusted.
    if _PDF_MAGIC not in content[:_MAGIC_SEARCH_WINDOW]:
        raise _reject(
            "File does not appear to be a valid PDF (missing %PDF- header). "
            "Renaming another file type to .pdf will not work."
        )

    _assert_parseable(content)
    return content


def _assert_parseable(content: bytes) -> None:
    """
    Structural probe: can the parser actually open this document?

    A correct ``%PDF-`` header proves nothing about the body — a truncated or
    corrupted file passes the magic-byte check and then raises deep inside the
    MuPDF C extension. Those errors are not ``ValueError`` and would surface as
    a 500, so we open the document here (cheap: headers and the xref table only)
    and convert *any* parser failure into a 422.
    """
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=content, filetype="pdf") as doc:
            if doc.page_count < 1:
                raise _reject("PDF contains no pages.")
            if doc.needs_pass:
                raise _reject("PDF is password-protected. Remove the password and retry.")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — any parser failure is a client error
        raise _reject(f"PDF could not be parsed: {type(exc).__name__}. The file may be corrupted.")
