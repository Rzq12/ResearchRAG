"""
Document / knowledge-base endpoints: PDF upload+ingest, list, delete,
summarize, clear-all, and KB stats. Thin wrappers over ``app.pdf_service``,
``app.rag`` and ``app.database``.

Every route is scoped to the authenticated user. The user id comes from the
bearer token via ``current_user`` and is never read from the request, so one
account cannot reach another's collection.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.database import get_collection, get_parent_collection
from app.pdf_service import delete_document, ingest_pdf, list_uploaded_docs
from app.rag import summarize_document

from api.rate_limit import limiter
from api.schemas import (
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
from api.security import current_user
from api.serialize import ingest_result_to_dict
from api.validation import read_validated_pdf

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=DocumentsResponse)
def list_documents(user_id: str = Depends(current_user)) -> DocumentsResponse:
    docs = list_uploaded_docs(user_id)
    return DocumentsResponse(documents=[DocumentModel(**d) for d in docs])


@router.get("/stats", response_model=KbStatsResponse)
def kb_stats(user_id: str = Depends(current_user)) -> KbStatsResponse:
    total = get_collection(user_id).count()
    docs = list_uploaded_docs(user_id)
    return KbStatsResponse(total_chunks=total, documents=len(docs))


@router.post("/upload", response_model=PdfIngestResponse)
@limiter.limit("10/minute")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(current_user),
) -> PdfIngestResponse:
    """
    Ingest a single uploaded PDF (advanced layout/table/parent-child pipeline).

    The payload is validated (size, magic bytes, structure) before it reaches
    the parser, so malformed input returns 422 instead of crashing the worker.
    """
    content = await read_validated_pdf(file)

    try:
        # ingest_pdf is fully synchronous and CPU-bound: layout parsing, optional
        # Tesseract OCR, then a sentence-transformers forward pass per chunk.
        # Called directly from this `async def` it pinned the event loop for the
        # whole ingest, so SSE streams froze and /api/health stopped answering —
        # long enough for the Docker HEALTHCHECK to restart the container
        # mid-ingest. Starlette's threadpool keeps the loop responsive.
        result = await run_in_threadpool(
            ingest_pdf, content, file.filename or "upload.pdf", user_id=user_id
        )
    except ValueError as exc:
        # e.g. image-only PDF with no OCR available — a client-side problem.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return PdfIngestResponse(**ingest_result_to_dict(result))


@router.post("/summarize", response_model=SummarizeResponse)
@limiter.limit("20/minute")
def summarize(
    request: Request,
    body: SummarizeRequest,
    user_id: str = Depends(current_user),
) -> SummarizeResponse:
    summary = summarize_document(
        body.title,
        user_id=user_id,
        api_key=body.api_key,
        model=body.model,
    )
    return SummarizeResponse(summary=summary)


@router.delete("", response_model=DeleteDocumentResponse)
@limiter.limit("10/minute")
def delete(
    request: Request,
    body: DeleteDocumentRequest,
    user_id: str = Depends(current_user),
) -> DeleteDocumentResponse:
    n = delete_document(body.title, user_id)
    return DeleteDocumentResponse(deleted=n)


@router.post("/clear", response_model=ClearResponse)
@limiter.limit("5/minute")
def clear_all(
    request: Request,
    user_id: str = Depends(current_user),
) -> ClearResponse:
    """Delete every chunk (child + parent) for the authenticated user."""
    cleared = 0
    for col in (get_collection(user_id), get_parent_collection(user_id)):
        # include=[] — ids come back regardless, and the default
        # include=["metadatas","documents"] pulled every chunk's full text into
        # RAM just to read the ids (~35 MB for a 40k-chunk KB, twice).
        ids = col.get(include=[])["ids"]
        if ids:
            col.delete(ids=ids)
            cleared += len(ids)
    return ClearResponse(cleared=cleared)
