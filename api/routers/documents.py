"""
Document / knowledge-base endpoints: PDF upload+ingest, list, delete,
summarize, clear-all, and KB stats. Thin wrappers over ``app.pdf_service``,
``app.rag`` and ``app.database``.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.database import get_collection, get_parent_collection
from app.pdf_service import delete_document, ingest_pdf, list_uploaded_docs
from app.rag import summarize_document

from api.schemas import (
    ClearRequest,
    ClearResponse,
    DeleteDocumentRequest,
    DeleteDocumentResponse,
    DocumentModel,
    DocumentsResponse,
    KbStatsResponse,
    PdfIngestResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from api.serialize import ingest_result_to_dict

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=DocumentsResponse)
def list_documents(user_id: str | None = None) -> DocumentsResponse:
    docs = list_uploaded_docs(user_id)
    return DocumentsResponse(documents=[DocumentModel(**d) for d in docs])


@router.get("/stats", response_model=KbStatsResponse)
def kb_stats(user_id: str | None = None) -> KbStatsResponse:
    total = get_collection(user_id).count()
    docs = list_uploaded_docs(user_id)
    return KbStatsResponse(total_chunks=total, documents=len(docs))


@router.post("/upload", response_model=PdfIngestResponse)
def upload_pdf(
    file: UploadFile = File(...),
    user_id: str | None = Form(default=None),
) -> PdfIngestResponse:
    """Ingest a single uploaded PDF (advanced layout/table/parent-child pipeline)."""
    cfg = get_settings()
    content = file.file.read()

    if cfg.max_upload_mb and len(content) > cfg.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"{file.filename} too large (max {cfg.max_upload_mb} MB).",
        )

    try:
        result = ingest_pdf(content, file.filename or "upload.pdf", user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PdfIngestResponse(**ingest_result_to_dict(result))


@router.post("/summarize", response_model=SummarizeResponse)
def summarize(body: SummarizeRequest) -> SummarizeResponse:
    summary = summarize_document(
        body.title,
        user_id=body.user_id,
        api_key=body.api_key,
        model=body.model,
    )
    return SummarizeResponse(summary=summary)


@router.delete("", response_model=DeleteDocumentResponse)
def delete(body: DeleteDocumentRequest) -> DeleteDocumentResponse:
    n = delete_document(body.title, body.user_id)
    return DeleteDocumentResponse(deleted=n)


@router.post("/clear", response_model=ClearResponse)
def clear_all(body: ClearRequest) -> ClearResponse:
    """Delete every chunk (child + parent) for the user."""
    cleared = 0
    for col in (get_collection(body.user_id), get_parent_collection(body.user_id)):
        ids = col.get()["ids"]
        if ids:
            col.delete(ids=ids)
            cleared += len(ids)
    return ClearResponse(cleared=cleared)
