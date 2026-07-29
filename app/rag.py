from app.llm_client import call_llm, stream_llm, get_provider
from app.database import get_collection, get_parent_collection, get_parents_by_ids, embed_query
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


def _vector_candidates(
    queries: list[str],
    child_col,
    candidate_k: int,
    where: dict | None = None,
) -> list[dict]:
    """
    Vector-search the child collection with one or more queries (the original
    question plus optional HyDE hypotheticals). Candidates found by several
    queries keep their best score. Returns dicts {id, text, metadata, _score}
    sorted by score descending.
    """
    best: dict[str, dict] = {}
    for q in queries:
        results = child_col.query(
            query_embeddings=[embed_query(q)],
            n_results=candidate_k,
            include=["documents", "metadatas", "distances"],
            where=where or None,
        )
        for cid, text, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            score = round(1 - dist, 4)
            if cid not in best or score > best[cid]["_score"]:
                best[cid] = {"id": cid, "text": text, "metadata": meta, "_score": score}

    return sorted(best.values(), key=lambda c: c["_score"], reverse=True)


def retrieve_chunks(
    query: str,
    top_k: int = None,
    user_id: str | None = None,
    api_key: str | None = None,   # enables HyDE when provided (needs an LLM)
    model: str | None = None,
    where: dict | None = None,    # optional Chroma metadata filter
) -> tuple[list[dict], list[dict]]:
    """
    Retrieval pipeline (notebook pattern, adapted to parent-child storage):

    1. HyDE      — LLM writes 2 hypothetical abstracts; used as extra queries
                   (skipped when api_key/model absent or enable_hyde=False)
    2. Ensemble  — vector search + BM25 keyword search, fused with RRF
                   (BM25 skipped when a `where` filter is active — the filter
                   is enforced natively by the vector search only)
    3. Rerank    — cross-encoder re-scores candidates against the ORIGINAL
                   query; scores sigmoid-normalized to [0,1]
    4. Parent    — fetch large parent chunks for the top children

    The top-1 reranker score is exposed as metadatas[0]["_retrieval_top1_score"]
    so ask()/ask_stream() can apply the relevance threshold + live fallback.
    """
    cfg = get_settings()
    k   = top_k or cfg.top_k_retrieval

    child_col = get_collection(user_id)
    if child_col.count() == 0:
        return [], []

    # ── Step 1: HyDE — hypothetical documents as extra retrieval queries ─────
    queries = [query]
    if getattr(cfg, "enable_hyde", False) and api_key and model:
        from app.hyde import generate_hypotheticals
        queries += generate_hypotheticals(query, api_key=api_key, model=model)

    # ── Step 2a: Vector search (3× more candidates for reranker/dedup room) ──
    candidate_k = min(k * 3, child_col.count(), 60)
    candidates  = _vector_candidates(queries, child_col, candidate_k, where=where)
    if not candidates:
        return [], []

    # ── Step 2b: BM25 keyword search + RRF fusion ─────────────────────────────
    if getattr(cfg, "enable_bm25", False) and not where:
        from app.retriever import bm25_search, rrf_fuse
        bm25_hits = bm25_search(query, user_id=user_id, k=candidate_k)
        if bm25_hits:
            candidates = rrf_fuse(
                candidates, bm25_hits,
                vector_weight = getattr(cfg, "vector_weight", 0.6),
                bm25_weight   = getattr(cfg, "bm25_weight", 0.4),
            )

    # ── Step 3: Rerank against the ORIGINAL query ─────────────────────────────
    top1_score: float | None = None
    if cfg.enable_reranker and candidates:
        try:
            from app.reranker import rerank
            reranked = rerank(
                query      = query,
                chunks     = candidates[: getattr(cfg, "rerank_max_candidates", 20)],
                model_name = cfg.reranker_model,
                top_k      = k,
            )
            candidates = [
                {"id": r.get("id", ""), "text": r["text"], "metadata": r["metadata"],
                 "_score": r["_rerank_score"]}
                for r in reranked
            ]
            top1_score = candidates[0]["_score"] if candidates else 0.0
        except Exception as exc:
            print(f"[Reranker] failed, using fusion order: {exc}")
            candidates = candidates[:k]
    else:
        candidates = candidates[:k]
        # Legacy soft check (only meaningful without reranker): if even the
        # best vector score is near zero, the query is completely unrelated.
        best_score = candidates[0]["_score"] if candidates else 0
        if best_score < cfg.similarity_threshold / 2:
            return [], []

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

    # Expose the reranker top-1 score for the relevance-threshold check.
    if final_metadatas and top1_score is not None:
        final_metadatas[0]["_retrieval_top1_score"] = top1_score

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
    reasoning: str = ""        # content of the <think> block, if any
    source: str = "kb"         # "kb" | "openalex-live" | "web" | "none"


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

_REASONING_INSTRUCTIONS = """
Before answering, reason inside <think> and </think> tags: which papers in the
context are relevant, whether they agree or conflict, and what the context does
NOT cover. Keep the reasoning brief (3-6 sentences). After </think>, write the
final answer with citations [1], [2]. The reasoning may be in English; the
final answer MUST be in the same language as the question.
"""


def _system_prompt() -> str:
    cfg = get_settings()
    if getattr(cfg, "enable_reasoning", False):
        return SYSTEM_PROMPT + _REASONING_INSTRUCTIONS
    return SYSTEM_PROMPT


def _resolve_relevance(metadatas: list[dict]) -> float | None:
    """Reranker top-1 score exposed by retrieve_chunks, or None if unavailable."""
    if not metadatas:
        return None
    return metadatas[0].get("_retrieval_top1_score")


def _fallback_refs(raw_refs: list[dict]) -> list[Reference]:
    return [
        Reference(
            title           = r.get("title", ""),
            authors         = r.get("authors", ""),
            published       = r.get("published", ""),
            url             = r.get("url", ""),
            source          = r.get("source", "web"),
            relevance_score = 0.0,
        )
        for r in raw_refs
    ]


_NO_SOURCE_ANSWER = (
    "Tidak ada sumber yang cukup relevan — baik di knowledge base Anda maupun "
    "dari pencarian langsung (OpenAlex / web). Saya tidak akan menebak jawaban.\n\n"
    "No sufficiently relevant source was found in your knowledge base or via "
    "live search, so I won't guess an answer."
)


def make_citation(meta: dict) -> str:
    """
    Short academic citation string for a chunk — the domain analogue of the
    legal notebook's 'PP No. 35 Tahun 2021, Pasal 78':
    e.g. 'Vaswani et al., 2017 [methods]'.
    """
    authors = meta.get("authors", "")
    first   = authors.split(",")[0].strip() if authors else ""
    et_al   = " et al." if authors.count(",") >= 1 else ""

    published = str(meta.get("published", ""))
    year      = published[:4] if published[:4].isdigit() else ""

    label = meta.get("section_label", "") or ""
    if label in ("", "other"):
        label = ""

    core = f"{first}{et_al}" if first and first != "Uploaded by user" else meta.get("title", "")
    if year:
        core += f", {year}"
    if label:
        core += f" [{label}]"
    return core


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

        ref_num  = seen_titles[title]
        citation = make_citation(meta)
        cite_tag = f" ({citation})" if citation and citation != title else ""
        # Include section label if available
        section_tag = f" [{section}]" if section else ""
        context_parts.append(f"[{ref_num}]{cite_tag}{section_tag} {chunk}")

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
    """Shared helper: assemble the full messages list for the LLM."""
    user_message = (
        f"Context from papers:\n{context}\n\n"
        f"Available references:\n{refs_text}\n\n"
        f"Question: {query}\n\n"
        "Answer based on the context above and cite references using [1], [2], etc. "
        "IMPORTANT: write the final answer in the language of the QUESTION above — "
        "ignore the language of the context passages."
    )
    messages = [{"role": "system", "content": _system_prompt()}]
    if chat_history:
        messages.extend(chat_history[-6:])
    messages.append({"role": "user", "content": user_message})
    return messages


def _prepare_context(
    query: str,
    cfg,
    user_id: str | None,
    api_key: str | None,
    model: str | None,
    where: dict | None,
    kb_only: bool = False,
) -> tuple[str, list[Reference], str] | None:
    """
    Shared retrieval front-end for ask()/ask_stream():
    retrieve → relevance threshold → (local KB context | live fallback).

    Returns (context, refs, source) — source is "kb", "openalex-live", "web",
    or "none" (nothing relevant anywhere). Returns None when the KB is simply
    empty/unmatched and the caller should use _no_chunks_response.

    kb_only: when True, never fall back to live OpenAlex/web — answer strictly
    from the user's knowledge base (used by the React frontend's "KB-only"
    toggle). Defaults to False, so existing callers (Streamlit) are unaffected.
    """
    chunks, metadatas = retrieve_chunks(
        query, user_id=user_id, api_key=api_key, model=model, where=where,
    )

    top1 = _resolve_relevance(metadatas)
    below_threshold = (
        not kb_only
        and top1 is not None
        and top1 < getattr(cfg, "relevance_threshold", 0.5)
        and getattr(cfg, "enable_web_fallback", False)
    )

    if below_threshold:
        # Local KB not relevant enough → OpenAlex live → DuckDuckGo.
        print(f"[fallback] top-1 rerank score {top1} < "
              f"{cfg.relevance_threshold} — trying live sources")
        from app.fallback import fallback_context
        context, raw_refs, note = fallback_context(query)
        if not context:
            return "", [], "none"
        return context, _fallback_refs(raw_refs), note

    if not chunks:
        return None

    context, refs = build_context(chunks, metadatas)
    return context, refs, "kb"


def _truncate_context(
    context: str,
    max_tokens: int = 8000,
    chars_per_token: int = 4,
) -> str:
    """
    Trim context to stay within token budget.
    Uses a simple char-based estimate (4 chars ≈ 1 token).
    Removes chunks from the end (least relevant first, since build_context
    orders by relevance descending).

    Parameters
    ----------
    context        : full context string from build_context()
    max_tokens     : target max tokens for the context portion
    chars_per_token: rough approximation (OpenAI/Groq tokenizers ≈ 4 chars/token)
    """
    max_chars = max_tokens * chars_per_token
    if len(context) <= max_chars:
        return context

    # Split by double-newline (chunk boundaries), trim from the end
    parts = context.split("\n\n")
    while parts and len("\n\n".join(parts)) > max_chars:
        parts.pop()   # remove least-relevant chunk

    trimmed = "\n\n".join(parts)
    trimmed += "\n\n[... context truncated to fit token limit ...]" if trimmed else ""
    return trimmed


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
            "- Coba turunkan `SIMILARITY_THRESHOLD` di `.env` (contoh: `0.05`)\n"
            "- Coba ulangi pertanyaan dalam bahasa Inggris\n"
            "- Pastikan dokumen yang relevan sudah ter-ingest"
        )
    return RAGResponse(answer=answer, references=[], openalex_papers_used=0, uploaded_docs_used=0)


# ─── Standard (non-streaming) ask ─────────────────────────────────────────────────────

def ask(
    query: str,
    chat_history: list[dict] = None,
    api_key: str | None = None,       # Groq key OR Gemini key, depending on model
    model: str | None = None,
    user_id: str | None = None,
    where: dict | None = None,        # optional metadata filter (year, section, …)
    kb_only: bool = False,            # True → never fall back to live sources
    # Backward-compat alias
    groq_api_key: str | None = None,
) -> RAGResponse:
    """Full RAG pipeline: HyDE → hybrid retrieve → rerank → threshold/fallback
    → build context → call LLM → parse <think> → return answer + refs.
    """
    cfg = get_settings()
    _key         = api_key or groq_api_key or cfg.groq_api_key
    chosen_model = model or cfg.groq_model
    _provider    = get_provider(chosen_model)

    if not _key:
        raise ValueError(f"API key required for provider '{_provider}'.")

    prepared = _prepare_context(query, cfg, user_id, _key, chosen_model, where, kb_only)
    if prepared is None:
        return _no_chunks_response(cfg, user_id)

    context, refs, source = prepared
    if source == "none":
        return RAGResponse(
            answer=_NO_SOURCE_ANSWER, references=[], openalex_papers_used=0,
            uploaded_docs_used=0, source="none",
        )

    # Gemini has 1M context — no need to truncate aggressively.
    # Groq free tier: ~12k TPM — keep context under 9k tokens.
    budget  = 200_000 if _provider == "gemini" else cfg.max_tokens_response * 3
    context = _truncate_context(context, max_tokens=budget)

    refs_text      = format_references_for_prompt(refs)
    openalex_count = sum(1 for r in refs if r.source == "openalex")
    upload_count   = sum(1 for r in refs if r.source == "upload")

    messages = _build_rag_messages(query, context, refs_text, chat_history)
    raw      = call_llm(
        model       = chosen_model,
        messages    = messages,
        api_key     = _key,
        max_tokens  = cfg.max_tokens_response,
        temperature = 0.3,
    )

    from app.reasoning import parse_think
    reasoning, answer = parse_think(raw)

    return RAGResponse(
        answer               = answer,
        references           = refs,
        openalex_papers_used = openalex_count,
        uploaded_docs_used   = upload_count,
        reasoning            = reasoning,
        source               = source,
    )

 # ─── Streaming ask ───────────────────────────────────────────────────────────────

def ask_stream(
    query: str,
    chat_history: list[dict] = None,
    api_key: str | None = None,        # Groq key OR Gemini key, depending on model
    model: str | None = None,
    user_id: str | None = None,
    where: dict | None = None,         # optional metadata filter (year, section, …)
    kb_only: bool = False,             # True → never fall back to live sources
    # Backward-compat alias
    groq_api_key: str | None = None,
) -> tuple:
    """
    Streaming RAG pipeline (Groq + Gemini + self-hosted).
    Returns (text_generator, refs, openalex_count, upload_count,
             think_holder, source).

    - think_holder["think"] holds the <think> reasoning; read it AFTER the
      generator is fully consumed (st.write_stream returns first).
    - source: "kb" | "openalex-live" | "web" | "none" — non-"kb" means the
      answer did NOT come from the user's knowledge base.

    Usage in Streamlit:
        gen, refs, oa, up, think, source = ask_stream(...)
        full_answer = st.write_stream(gen)
        if think["think"]: st.expander("Reasoning").markdown(think["think"])
    """
    from app.reasoning import split_think_stream

    cfg = get_settings()
    _key         = api_key or groq_api_key or cfg.groq_api_key
    chosen_model = model or cfg.groq_model
    _provider    = get_provider(chosen_model)

    if not _key:
        raise ValueError(f"API key required for provider '{_provider}'.")

    empty_holder = {"think": ""}

    prepared = _prepare_context(query, cfg, user_id, _key, chosen_model, where, kb_only)
    if prepared is None:
        no_chunks = _no_chunks_response(cfg, user_id)

        def _no_chunks_gen():
            yield no_chunks.answer

        return _no_chunks_gen(), [], 0, 0, empty_holder, "kb"

    context, refs, source = prepared
    if source == "none":
        def _no_source_gen():
            yield _NO_SOURCE_ANSWER

        return _no_source_gen(), [], 0, 0, empty_holder, "none"

    # Gemini: 1M context — large budget. Groq free tier: conservative 9k tokens.
    budget  = 200_000 if _provider == "gemini" else 9_000
    context = _truncate_context(context, max_tokens=budget)

    refs_text      = format_references_for_prompt(refs)
    openalex_count = sum(1 for r in refs if r.source == "openalex")
    upload_count   = sum(1 for r in refs if r.source == "upload")

    messages = _build_rag_messages(query, context, refs_text, chat_history)

    raw_stream = stream_llm(
        model       = chosen_model,
        messages    = messages,
        api_key     = _key,
        max_tokens  = cfg.max_tokens_response,
        temperature = 0.3,
    )
    answer_stream, think_holder = split_think_stream(raw_stream)

    return (
        answer_stream,
        refs,
        openalex_count,
        upload_count,
        think_holder,
        source,
    )


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
    api_key: str | None = None,
    model: str | None = None,
    # backward-compat alias
    groq_api_key: str | None = None,
) -> str:
    """
    Generate a structured 5-section summary of a document from its stored chunks.
    Works with Gemini or Groq — provider is auto-detected from model name.

    Content selection strategy (to always capture Limitations/Conclusion):
    - Fetch ALL chunks sorted by chunk_index (document order).
    - If total chars ≤ summarize_max_chars: use everything.
    - Otherwise: fill from the BEGINNING until 55 % of the limit is used,
      then fill from the END going backwards until the other 45 % is used.
      A separator signals any omitted middle.
    This guarantees that both the abstract/intro AND the results/limitations
    are always present in the summarizer context.
    """
    cfg = get_settings()
    _key   = api_key or groq_api_key or cfg.groq_api_key or cfg.gemini_api_key
    _model = model or cfg.groq_model
    if not _key:
        raise ValueError("API key diperlukan untuk summarize (Groq atau Gemini).")

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
        budget_begin = int(max_chars * 0.55)
        budget_end   = max_chars - budget_begin

        # Build beginning section
        begin_parts: list[str] = []
        used = 0
        for chunk in chunks:
            if used + len(chunk) > budget_begin:
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
        n_begin    = len(begin_parts)
        n_end      = len(end_parts)
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

    prompt   = _SUMMARIZE_PROMPT.format(title=title, content=content)
    messages = [
        {"role": "system", "content": _SUMMARIZE_SYSTEM},
        {"role": "user",   "content": prompt},
    ]

    return call_llm(
        model       = _model,
        messages    = messages,
        api_key     = _key,
        max_tokens  = 1200,
        temperature = 0.2,
    )


# ─── Query Suggestions ────────────────────────────────────────────────────────

def generate_query_suggestions(
    works_or_titles: list,
    api_key: str | None = None,
    model: str | None = None,
    n: int = 5,
    # backward-compat alias
    groq_api_key: str | None = None,
) -> list[str]:
    """
    Generate n specific research question suggestions based on ingested works.
    Works with Gemini or Groq — provider auto-detected from model name.
    """
    cfg    = get_settings()
    _key   = api_key or groq_api_key or cfg.groq_api_key or cfg.gemini_api_key
    _model = model or cfg.groq_model
    if not _key:
        return []

    context_parts = []
    for item in works_or_titles[:6]:
        if isinstance(item, str):
            context_parts.append(f"- {item}")
        else:
            abstract = getattr(item, "abstract", "") or ""
            snippet  = abstract[:200].strip()
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
        raw = call_llm(
            model       = _model,
            messages    = [{"role": "user", "content": prompt}],
            api_key     = _key,
            max_tokens  = 400,
            temperature = 0.7,
        )
        questions = []
        for line in raw.split("\n"):
            line    = line.strip()
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
            if cleaned and len(cleaned) > 15:
                questions.append(cleaned)
        return questions[:n]
    except Exception:
        return []
