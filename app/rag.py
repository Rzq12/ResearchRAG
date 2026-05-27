from groq import Groq
from app.database import get_collection, embed_texts
from app.config import get_settings
from dataclasses import dataclass


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


def retrieve_chunks(query: str, top_k: int = None) -> tuple[list[dict], list[dict]]:
    """
    Retrieve top-k relevant chunks from ChromaDB.
    Returns (chunks, metadatas).
    """
    cfg = get_settings()
    k = top_k or cfg.top_k_retrieval
    collection = get_collection()

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

    return chunks, metadatas


def build_context(chunks: list[str], metadatas: list[dict]) -> tuple[str, list[Reference]]:
    """
    Build context string and deduplicated reference list.
    """
    seen_titles = {}
    refs: list[Reference] = []
    context_parts = []

    for chunk, meta in zip(chunks, metadatas):
        title = meta.get("title", "Unknown")

        # Deduplicate references by title
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


def ask(query: str, chat_history: list[dict] = None, groq_api_key: str | None = None) -> RAGResponse:
    """
    Full RAG pipeline: retrieve → build context → call Groq → return answer + refs.
    """
    cfg = get_settings()
    api_key = groq_api_key or cfg.groq_api_key
    if not api_key:
        raise ValueError("Groq API key is required")
    client = Groq(api_key=api_key)

    # 1. Retrieve
    chunks, metadatas = retrieve_chunks(query)

    if not chunks:
        return RAGResponse(
            answer="Belum ada dokumen di database. Silakan search OpenAlex atau upload PDF terlebih dahulu.",
            references=[],
            openalex_papers_used=0,
            uploaded_docs_used=0,
        )

    # 2. Build context + references
    context, refs = build_context(chunks, metadatas)
    refs_text = format_references_for_prompt(refs)

    # 3. Count sources
    openalex_count = sum(1 for r in refs if r.source == "openalex")
    upload_count = sum(1 for r in refs if r.source == "upload")

    # 4. Build messages
    user_message = f"""Context from papers:
{context}

Available references:
{refs_text}

Question: {query}

Answer based on the context above and cite references using [1], [2], etc."""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Inject chat history (last 6 turns for context window)
    if chat_history:
        messages.extend(chat_history[-6:])

    messages.append({"role": "user", "content": user_message})

    # 5. Call Groq
    response = client.chat.completions.create(
        model=cfg.groq_model,
        messages=messages,
        temperature=0.3,
        max_tokens=1500,
    )

    answer = response.choices[0].message.content

    return RAGResponse(
        answer=answer,
        references=refs,
        openalex_papers_used=openalex_count,
        uploaded_docs_used=upload_count,
    )
