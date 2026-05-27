from groq import Groq
from app.database import get_collection, embed_texts
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


def retrieve_chunks(query: str, top_k: int = None, user_id: str | None = None) -> tuple[list[dict], list[dict]]:
    """
    Retrieve top-k relevant chunks from ChromaDB.
    Returns (chunks, metadatas).
    """
    cfg = get_settings()
    k = top_k or cfg.top_k_retrieval
    collection = get_collection(user_id)

    if collection.count() == 0:
        return [], []

    query_embedding = embed_texts([query])[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    # Attach similarity score (1 - cosine distance)
    for i, meta in enumerate(metadatas):
        meta["_score"] = round(1 - distances[i], 4)

    # Filter out chunks below similarity threshold
    threshold = cfg.similarity_threshold
    filtered = [
        (c, m) for c, m in zip(chunks, metadatas)
        if m.get("_score", 0) >= threshold
    ]
    if filtered:
        chunks, metadatas = zip(*filtered)
        chunks, metadatas = list(chunks), list(metadatas)
    else:
        chunks, metadatas = [], []

    return chunks, metadatas


def build_context(chunks: list[str], metadatas: list[dict]) -> tuple[str, list[Reference]]:
    """Build context string and deduplicated reference list."""
    seen_titles = {}
    refs: list[Reference] = []
    context_parts = []

    for chunk, meta in zip(chunks, metadatas):
        title = meta.get("title", "Unknown")

        if title not in seen_titles:
            ref_num = len(refs) + 1
            seen_titles[title] = ref_num
            refs.append(Reference(
                title=title,
                authors=meta.get("authors", ""),
                published=meta.get("published", ""),
                url=meta.get("url", ""),
                source=meta.get("source", "unknown"),
                relevance_score=meta.get("_score", 0.0),
            ))

        ref_num = seen_titles[title]
        context_parts.append(f"[{ref_num}] {chunk}")

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
    """
    cfg = get_settings()
    api_key = groq_api_key or cfg.groq_api_key
    if not api_key:
        raise ValueError("Groq API key is required")
    client = Groq(api_key=api_key)

    collection = get_collection(user_id)
    results = collection.get(where={"title": title}, include=["documents"])
    chunks = results.get("documents", [])

    if not chunks:
        return f"Tidak ada konten yang ditemukan untuk dokumen: **{title}**"

    # Use first 6 chunks to stay within context limits (~4800 chars)
    sample_text = "\n\n---\n\n".join(chunks[:6])
    prompt = _SUMMARIZE_PROMPT.format(title=title, content=sample_text)

    response = client.chat.completions.create(
        model=cfg.groq_model,
        messages=[
            {"role": "system", "content": _SUMMARIZE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=900,
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
