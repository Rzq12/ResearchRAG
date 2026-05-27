from groq import Groq
from app.database import get_collection, get_parent_collection, get_parents_by_ids, embed_texts
from app.config import get_settings
from dataclasses import dataclass
import re


@dataclass
class Reference:
    title: str
    authors: str
    published: str
    url: str
    source: str
    relevance_score: float


@dataclass
class RAGResponse:
    answer: str
    references: list[Reference]
    openalex_papers_used: int
    uploaded_docs_used: int


SYSTEM_PROMPT = """You are a research assistant with access to scientific papers from OpenAlex and user-uploaded documents.

Your job is to answer questions accurately, grounding your answer in the provided context.

Rules:
1. Base your answer ONLY on the provided context chunks.
2. When referencing information, cite the paper using [1], [2], etc. matching the reference list.
3. If multiple papers support a claim, cite all of them: [1][3].
4. If the context doesn't contain enough information, say so honestly.
5. Be concise but thorough. Use bullet points for complex answers.
6. Always end with a brief summary of key references used.
7. Write in the same language as the question (Indonesian or English).
"""


def retrieve_chunks(
    query: str,
    top_k: int = None,
    user_id: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Retrieve relevant context using Parent-Child retrieval strategy:

    1. Embed query → search CHILD collection (small, precise chunks) for top-K*3 candidates
    2. Optional: cross-encoder reranker re-scores candidates
    3. Collect parent_ids from top children
    4. Fetch PARENT chunks (large, rich context) from parent collection
    5. Return parent texts as context to LLM (deduped, ordered by relevance)

    Falls back to child text if parent lookup fails or parent_id is missing.

    NOTE: We do NOT apply similarity_threshold during child search because child chunks
    (~180 words) naturally have lower per-chunk scores. Threshold is only used to
    detect when the top result is completely unrelated (score < threshold/2).
    """
    cfg = get_settings()
    k   = top_k or cfg.top_k_retrieval

    child_col = get_collection(user_id)
    if child_col.count() == 0:
        return [], []

    # ── Step 1: Child search (NO threshold filter here) ──────────────────────
    # Retrieve 3× more candidates to give reranker / parent dedup room to work
    candidate_k     = min(k * 3, child_col.count(), 60)
    query_embedding = embed_texts([query])[0]

    results = child_col.query(
        query_embeddings=[query_embedding],
        n_results=candidate_k,
        include=["documents", "metadatas", "distances"],
    )

    child_texts = results["documents"][0]
    child_metas = results["metadatas"][0]
    distances   = results["distances"][0]

    if not child_texts:
        return [], []

    # Attach similarity score (1 - cosine distance)
    candidates = []
    for text, meta, dist in zip(child_texts, child_metas, distances):
        score = round(1 - dist, 4)
        candidates.append({
            "text":     text,
            "metadata": meta,
            "_score":   score,
        })

    # Soft threshold check: if the BEST candidate is below threshold/2, the query
    # is completely unrelated to anything in KB → return empty so LLM can say so.
    best_score = candidates[0]["_score"] if candidates else 0
    if best_score < cfg.similarity_threshold / 2:
        return [], []

    # ── Step 2: Optional reranker ─────────────────────────────────────────────
    if cfg.enable_reranker and candidates:
        try:
            from app.reranker import rerank
            flat = [{"text": c["text"], **c} for c in candidates]
            reranked = rerank(
                query      = query,
                chunks     = flat,
                model_name = cfg.reranker_model,
                top_k      = k,
            )
            candidates = [
                {"text": r["text"], "metadata": r["metadata"], "_score": r.get("_rerank_score", r["_score"])}
                for r in reranked
            ]
        except Exception:
            candidates = candidates[:k]
    else:
        candidates = candidates[:k]

    # ── Step 3: Fetch parent chunks ───────────────────────────────────────────
    parent_ids_ordered: list[str] = []
    seen_parent_ids: set[str]     = set()
    no_parent_candidates: list[dict] = []

    for c in candidates:
        pid = c["metadata"].get("parent_id", "")
        if pid and pid not in seen_parent_ids:
            parent_ids_ordered.append(pid)
            seen_parent_ids.add(pid)
        else:
            # No parent_id: either old-pipeline chunk or parent lookup needed
            no_parent_candidates.append(c)

    # Fetch parent chunks (large context) from parent collection
    parent_docs  = get_parents_by_ids(parent_ids_ordered, user_id) if parent_ids_ordered else []
    parent_by_id = {p["id"]: p for p in parent_docs}

    final_chunks:    list[str]  = []
    final_metadatas: list[dict] = []

    # Prefer parent chunks (rich context) in order of child relevance
    for pid in parent_ids_ordered:
        parent = parent_by_id.get(pid)
        if parent and parent.get("text"):
            final_chunks.append(parent["text"])
            final_metadatas.append({**parent["metadata"], "_score": 1.0})
        else:
            # Parent not found in parent collection → use child chunk as fallback
            # Find the child candidate that pointed to this parent_id
            for c in candidates:
                if c["metadata"].get("parent_id", "") == pid:
                    final_chunks.append(c["text"])
                    final_metadatas.append({**c["metadata"], "_score": c["_score"]})
                    break

    # Chunks without parent_id (old pipeline or fallback pages)
    for c in no_parent_candidates:
        if c["text"] not in final_chunks:   # avoid duplicates
            final_chunks.append(c["text"])
            final_metadatas.append({**c["metadata"], "_score": c["_score"]})

    return final_chunks, final_metadatas




@dataclass
class Reference:
    title: str
    authors: str
    published: str
    url: str
    source: str
    relevance_score: float


@dataclass
class RAGResponse:
    answer: str
    references: list[Reference]
    openalex_papers_used: int
    uploaded_docs_used: int


SYSTEM_PROMPT = """You are a research assistant with access to scientific papers from OpenAlex and user-uploaded documents.

Your job is to answer questions accurately, grounding your answer in the provided context.

Rules:
1. Base your answer ONLY on the provided context chunks.
2. When referencing information, cite the paper using [1], [2], etc. matching the reference list.
3. If multiple papers support a claim, cite all of them: [1][3].
4. If the context doesn't contain enough information, say so honestly.
5. Be concise but thorough. Use bullet points for complex answers.
6. Always end with a brief summary of key references used.
7. Write in the same language as the question (Indonesian or English).
"""



def build_context(chunks: list[str], metadatas: list[dict]) -> tuple[str, list[Reference]]:
    """
    Build context string and deduplicated reference list.

    Each unique document gets a metadata header (title, authors, year, section)
    prepended once. This lets the LLM answer questions like "siapa authornya?"
    even when author info is only in metadata, not in chunk text.
    """
    seen_titles: dict[str, int] = {}
    refs: list[Reference] = []
    context_parts: list[str] = []

    for chunk, meta in zip(chunks, metadatas):
        title     = meta.get("title", "Unknown")
        authors   = meta.get("authors", "")
        published = meta.get("published", "")
        section   = meta.get("section_title", "") or meta.get("section_path", "")

        if title not in seen_titles:
            ref_num = len(refs) + 1
            seen_titles[title] = ref_num
            refs.append(Reference(
                title          = title,
                authors        = authors,
                published      = published,
                url            = meta.get("url", ""),
                source         = meta.get("source", "unknown"),
                relevance_score = meta.get("_score", 0.0),
            ))
            # Prepend metadata header for this document (first occurrence)
            header_parts = [f"--- Paper [{ref_num}]: {title}"]
            if authors:
                header_parts.append(f"Authors: {authors}")
            if published and published not in ("N/A", ""):
                header_parts.append(f"Year: {published}")
            context_parts.append("\n".join(header_parts))

        ref_num = seen_titles[title]
        # Include section label if available
        section_label = f" [{section}]" if section else ""
        context_parts.append(f"[{ref_num}]{section_label} {chunk}")

    context = "\n\n".join(context_parts)
    return context, refs


def format_references_for_prompt(refs: list[Reference]) -> str:
    lines = []
    for i, ref in enumerate(refs, 1):
        line = f"[{i}] {ref.title}"
        if ref.authors:
            line += f" — {ref.authors}"
        if ref.published and ref.published != "N/A":
            line += f" ({ref.published})"
        lines.append(line)
    return "\n".join(lines)


def _build_rag_messages(
    query: str,
    context: str,
    refs_text: str,
    chat_history: list[dict] | None,
) -> list[dict]:
    """Shared helper: assemble the full messages list for Groq."""
    user_message = (
        f"Context from papers:\n{context}\n\n"
        f"Available references:\n{refs_text}\n\n"
        f"Question: {query}\n\n"
        "Answer based on the context above and cite references using [1], [2], etc."
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if chat_history:
        messages.extend(chat_history[-6:])
    messages.append({"role": "user", "content": user_message})
    return messages


def _no_chunks_response(cfg, user_id: str | None) -> RAGResponse:
    """Return appropriate RAGResponse when retrieval yields no chunks."""
    collection = get_collection(user_id)
    if collection.count() == 0:
        answer = "Belum ada dokumen di database. Silakan search OpenAlex atau upload PDF terlebih dahulu."
    else:
        answer = (
            f"Tidak ada chunk yang cukup relevan ditemukan untuk pertanyaan ini "
            f"(threshold similarity: {cfg.similarity_threshold}).\n\n"
            "Kemungkinan penyebab:\n"
            "- Pertanyaan terlalu jauh dari topik dokumen yang ada\n"
            "- Coba turunkan `SIMILARITY_THRESHOLD` di `.env` (contoh: `0.1`)\n"
            "- Coba ulangi pertanyaan dalam bahasa Inggris\n"
            "- Pastikan dokumen yang relevan sudah ter-ingest"
        )
    return RAGResponse(answer=answer, references=[], openalex_papers_used=0, uploaded_docs_used=0)


# ─── Standard (non-streaming) ask ────────────────────────────────────────────

def ask(
    query: str,
    chat_history: list[dict] = None,
    groq_api_key: str | None = None,
    user_id: str | None = None,
) -> RAGResponse:
    """Full RAG pipeline: retrieve → build context → call Groq → return answer + refs."""
    cfg = get_settings()
    api_key = groq_api_key or cfg.groq_api_key
    if not api_key:
        raise ValueError("Groq API key is required")
    client = Groq(api_key=api_key)

    chunks, metadatas = retrieve_chunks(query, user_id=user_id)
    if not chunks:
        return _no_chunks_response(cfg, user_id)

    context, refs = build_context(chunks, metadatas)
    refs_text = format_references_for_prompt(refs)
    openalex_count = sum(1 for r in refs if r.source == "openalex")
    upload_count = sum(1 for r in refs if r.source == "upload")

    messages = _build_rag_messages(query, context, refs_text, chat_history)
    response = client.chat.completions.create(
        model=cfg.groq_model,
        messages=messages,
        temperature=0.3,
        max_tokens=cfg.max_tokens_response,
    )
    answer = response.choices[0].message.content

    return RAGResponse(
        answer=answer,
        references=refs,
        openalex_papers_used=openalex_count,
        uploaded_docs_used=upload_count,
    )


# ─── Streaming ask ────────────────────────────────────────────────────────────

def ask_stream(
    query: str,
    chat_history: list[dict] = None,
    groq_api_key: str | None = None,
    user_id: str | None = None,
) -> tuple:
    """
    Streaming RAG pipeline.
    Returns (text_generator, refs, openalex_count, upload_count).

    Usage in Streamlit:
        gen, refs, oa, up = ask_stream(...)
        full_answer = st.write_stream(gen)   # streams tokens, returns full string
    """
    cfg = get_settings()
    api_key = groq_api_key or cfg.groq_api_key
    if not api_key:
        raise ValueError("Groq API key is required")
    client = Groq(api_key=api_key)

    chunks, metadatas = retrieve_chunks(query, user_id=user_id)
    if not chunks:
        fallback = _no_chunks_response(cfg, user_id)

        def _fallback_gen():
            yield fallback.answer

        return _fallback_gen(), [], 0, 0

    context, refs = build_context(chunks, metadatas)
    refs_text = format_references_for_prompt(refs)
    openalex_count = sum(1 for r in refs if r.source == "openalex")
    upload_count = sum(1 for r in refs if r.source == "upload")

    messages = _build_rag_messages(query, context, refs_text, chat_history)
    stream = client.chat.completions.create(
        model=cfg.groq_model,
        messages=messages,
        temperature=0.3,
        max_tokens=cfg.max_tokens_response,
        stream=True,
    )

    def _gen():
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    return _gen(), refs, openalex_count, upload_count


# ─── Paper Summarizer ─────────────────────────────────────────────────────────

_SUMMARIZE_SYSTEM = (
    "You are a research paper summarization assistant. Be precise, structured, and concise."
)

_SUMMARIZE_PROMPT = """Summarize the following research paper content in a structured format.

Title: {title}

Content:
{content}

Provide exactly these sections:
1. **Main Topic**: What is this paper about? (1-2 sentences)
2. **Key Contributions**: What are the main contributions or findings? (2-3 bullet points)
3. **Methodology**: What methods or approaches are used? (1-2 sentences)
4. **Key Results**: What are the main quantitative or qualitative results? (2-3 bullet points)
5. **Limitations**: Any limitations or future work mentioned? (1-2 sentences, or "Not mentioned")

Write in the same language as the content."""


def summarize_document(
    title: str,
    user_id: str | None = None,
    groq_api_key: str | None = None,
) -> str:
    """
    Generate a structured 5-section summary of a document from its stored chunks.

    Content selection strategy (to always capture Limitations/Conclusion):
    - Fetch ALL chunks sorted by chunk_index (document order).
    - If total chars ≤ summarize_max_chars: use everything.
    - Otherwise: fill from the BEGINNING until half the limit is used,
      then fill from the END going backwards until the other half is used.
      A separator signals any omitted middle.
    This guarantees that both the abstract/intro AND the results/limitations
    are always present in the summarizer context.
    """
    cfg = get_settings()
    api_key = groq_api_key or cfg.groq_api_key
    if not api_key:
        raise ValueError("Groq API key is required")
    client = Groq(api_key=api_key)

    collection = get_collection(user_id)
    # Fetch documents + metadatas so we can sort by chunk_index
    results = collection.get(
        where={"title": title},
        include=["documents", "metadatas"],
    )
    raw_chunks = results.get("documents", [])
    raw_metas  = results.get("metadatas", []) or [{}] * len(raw_chunks)

    if not raw_chunks:
        return f"Tidak ada konten yang ditemukan untuk dokumen: **{title}**"

    # Sort by chunk_index to maintain document order
    paired = sorted(
        zip(raw_chunks, raw_metas),
        key=lambda x: x[1].get("chunk_index", 0) if x[1] else 0,
    )
    chunks = [c for c, _ in paired]

    max_chars = cfg.summarize_max_chars  # default 20 000 chars

    total_chars = sum(len(c) for c in chunks)

    if total_chars <= max_chars:
        # Short enough: use the full paper
        content = "\n\n---\n\n".join(chunks)
    else:
        # Distribute budget: 55 % beginning, 45 % end
        # (methods/results tend to be longer than intro)
        budget_begin = int(max_chars * 0.55)
        budget_end   = max_chars - budget_begin

        # Build beginning section
        begin_parts: list[str] = []
        used = 0
        for chunk in chunks:
            if used + len(chunk) > budget_begin:
                # Add partial chunk so we don't waste budget
                remaining = budget_begin - used
                if remaining > 100:
                    begin_parts.append(chunk[:remaining] + " …")
                break
            begin_parts.append(chunk)
            used += len(chunk)

        # Build end section (walk backwards)
        end_parts: list[str] = []
        used = 0
        for chunk in reversed(chunks):
            if used + len(chunk) > budget_end:
                remaining = budget_end - used
                if remaining > 100:
                    end_parts.insert(0, "… " + chunk[-remaining:])
                break
            end_parts.insert(0, chunk)
            used += len(chunk)

        # Detect if there is a gap between begin and end
        n_begin = len(begin_parts)
        n_end   = len(end_parts)
        gap_chunks = len(chunks) - n_begin - n_end

        separator = (
            f"\n\n[... {gap_chunks} chunk(s) from middle sections omitted for length ...]\n\n"
            if gap_chunks > 0 else "\n\n"
        )

        content = (
            "\n\n---\n\n".join(begin_parts)
            + separator
            + "\n\n---\n\n".join(end_parts)
        )

    prompt = _SUMMARIZE_PROMPT.format(title=title, content=content)

    response = client.chat.completions.create(
        model=cfg.groq_model,
        messages=[
            {"role": "system", "content": _SUMMARIZE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1200,
    )
    return response.choices[0].message.content


# ─── Query Suggestions ────────────────────────────────────────────────────────

def generate_query_suggestions(
    works_or_titles: list,
    groq_api_key: str | None = None,
    n: int = 5,
) -> list[str]:
    """
    Generate n specific research question suggestions based on ingested works.

    Parameters
    ----------
    works_or_titles : list
        List of OpenAlexWork objects (with .title / .abstract) or plain title strings.
    groq_api_key : str | None
    n : int
        Number of questions to generate.
    """
    cfg = get_settings()
    api_key = groq_api_key or cfg.groq_api_key
    if not api_key:
        return []

    client = Groq(api_key=api_key)

    context_parts = []
    for item in works_or_titles[:6]:
        if isinstance(item, str):
            context_parts.append(f"- {item}")
        else:
            abstract = getattr(item, "abstract", "") or ""
            snippet = abstract[:200].strip()
            ellipsis = "…" if len(abstract) > 200 else ""
            context_parts.append(f"- **{item.title}**: {snippet}{ellipsis}")
    context = "\n".join(context_parts)

    prompt = (
        f"Based on these research papers, generate exactly {n} specific and insightful research questions "
        "that can be answered from the content:\n\n"
        f"Papers:\n{context}\n\n"
        "Rules:\n"
        "- Each question on its own line starting with a number and period (e.g. '1. What is...')\n"
        "- Questions should be specific, not generic\n"
        "- Mix question types: comparison, explanation, methodology, results, limitations\n"
        "- No introductory text, just the numbered list\n\n"
        f"Generate {n} questions:"
    )

    try:
        response = client.chat.completions.create(
            model=cfg.groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        raw = response.choices[0].message.content.strip()
        questions = []
        for line in raw.split("\n"):
            line = line.strip()
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
            if cleaned and len(cleaned) > 15:
                questions.append(cleaned)
        return questions[:n]
    except Exception:
        return []
