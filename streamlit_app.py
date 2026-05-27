import streamlit as st
import sys
import os
import httpx

# Make sure app/ is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_chroma, get_collection
from app.openalex_service import search_openalex, ingest_openalex_abstracts
from app.pdf_service import ingest_pdf, list_uploaded_docs, delete_document
from app.rag import ask
from app.config import get_settings
from app.fulltext_service import fetch_fulltext_batch

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OpenAlex RAG Chatbot",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .ref-card {
        background: #f8f9fa;
        border-left: 3px solid #4A90D9;
        padding: 10px 14px;
        margin: 6px 0;
        border-radius: 0 6px 6px 0;
        font-size: 13px;
    }
    .ref-card a { color: #4A90D9; text-decoration: none; }
    .ref-card a:hover { text-decoration: underline; }
    .badge-openalex {
        background: #fff3e0; color: #e65100;
        padding: 2px 8px; border-radius: 12px;
        font-size: 11px; font-weight: 600;
    }
    .badge-upload {
        background: #e8f5e9; color: #2e7d32;
        padding: 2px 8px; border-radius: 12px;
        font-size: 11px; font-weight: 600;
    }
    .stChatMessage { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ─── Init ────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Initializing database...")
def startup():
    init_chroma()
    return True

startup()

cfg = get_settings()


@st.cache_data(show_spinner=False, ttl=300)
def cached_search_openalex(query: str, max_results: int):
    return search_openalex(query, max_results=max_results, api_key=None)

# ─── Session state ───────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "openalex_results" not in st.session_state:
    st.session_state.openalex_results = []

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔬 OpenAlex RAG")
    st.caption("Research Assistant with Citations")

    user_id = st.text_input(
        "User ID",
        key="user_id",
        help="Gunakan ID yang sama agar knowledge base stabil per akun.",
    )

    groq_key = st.text_input(
        "Groq API key",
        type="password",
        key="groq_api_key",
        help="Stored in session only. Leave empty to use .env",
    )

    active_user_id = (st.session_state.get("user_id") or "").strip() or None
    previous_user_id = st.session_state.get("active_user_id")
    if previous_user_id and previous_user_id != active_user_id:
        st.session_state.messages = []
        st.session_state.openalex_results = []
    st.session_state.active_user_id = active_user_id

    st.divider()

    # ── OpenAlex Search ───────────────────────────────────────────────────
    st.subheader("📡 Search OpenAlex")
    search_query = st.text_input(
        "Search papers",
        placeholder="e.g. attention mechanism transformer",
        key="openalex_query",
    )
    col1, col2 = st.columns(2)
    n_results = col1.number_input("Papers", min_value=1, max_value=20, value=5)
    openalex_key = col2.text_input(
        "OpenAlex API key (optional)",
        type="password",
        key="openalex_api_key",
    )
    col2.caption("OpenAlex uses abstracts only")

    if st.button("🔍 Search & Ingest", use_container_width=True):
        if not search_query.strip():
            st.warning("Please enter a search query.")
        elif cfg.require_user_id and not active_user_id:
            st.warning("User ID wajib diisi untuk memisahkan database per akun.")
        else:
            try:
                with st.spinner(f"Searching OpenAlex for '{search_query}'..."):
                    if openalex_key:
                        works = search_openalex(
                            search_query,
                            max_results=int(n_results),
                            api_key=openalex_key,
                        )
                    else:
                        works = cached_search_openalex(
                            search_query,
                            max_results=int(n_results),
                        )
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 429:
                    st.error("OpenAlex rate limit hit. Please wait a few seconds and try again.")
                else:
                    st.error(f"OpenAlex error: {exc}")
                st.stop()
            except httpx.RequestError as exc:
                st.error(f"Network error contacting OpenAlex: {exc}")
                st.stop()

            if works:
                st.session_state.openalex_results = works
                with st.spinner("Ingesting abstracts into ChromaDB..."):
                    ingest_openalex_abstracts(works, user_id=active_user_id)
                st.success(f"✅ {len(works)} works ingested!")
            else:
                st.error("No works found.")

    # Show last search results + full-text fetch
    if st.session_state.openalex_results:
        with st.expander(f"📄 OpenAlex results ({len(st.session_state.openalex_results)} works)"):
            for w in st.session_state.openalex_results:
                st.markdown(f"**[{w.title}]({w.url})**")
                st.caption(f"{', '.join(w.authors[:2])} · {w.published}")
                st.write("")

        # ── Full-text fetch button ────────────────────────────────────────
        if st.button("🔗 Fetch Full-Text (Open Access)", use_container_width=True,
                     help="Coba download PDF lengkap via Semantic Scholar & Unpaywall"):
            if cfg.require_user_id and not active_user_id:
                st.warning("User ID wajib diisi.")
            else:
                status_ph = st.empty()
                def _cb(msg: str):
                    status_ph.caption(msg)

                with st.spinner("Fetching full-text PDFs…"):
                    ft_result = fetch_fulltext_batch(
                        st.session_state.openalex_results,
                        user_id=active_user_id,
                        status_callback=_cb,
                    )
                status_ph.empty()

                fetched = ft_result["fetched"]
                skipped = ft_result["skipped"]
                failed  = ft_result["failed"]

                if fetched > 0:
                    st.success(f"✅ Full-text ingested: {fetched} paper(s)")
                if skipped > 0:
                    st.info(f"ℹ️ Already indexed: {skipped} paper(s)")
                if failed > 0:
                    st.warning(f"⚠️ No open-access PDF found: {failed} paper(s)")

                with st.expander("📋 Full-text details"):
                    for d in ft_result["details"]:
                        icon = {"ingested": "✅", "already_indexed": "ℹ️"}.get(
                            d["status"], "⚠️"
                        )
                        src = f" [{d['source']}]" if d.get("source") else ""
                        chunks = f" — {d['chunks']} chunks" if d.get("chunks") else ""
                        st.caption(f"{icon} {d['title'][:60]}{src}{chunks}")

    st.divider()

    # ── PDF Upload ────────────────────────────────────────────────────────
    st.subheader("📎 Upload PDF")
    uploaded_files = st.file_uploader(
        "Upload your own papers",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_upload",
    )
    if uploaded_files:
        if st.button("📥 Ingest PDFs", use_container_width=True):
            if cfg.require_user_id and not active_user_id:
                st.warning("User ID wajib diisi untuk memisahkan database per akun.")
                st.stop()
            for f in uploaded_files:
                size_bytes = getattr(f, "size", None)
                if size_bytes is None:
                    try:
                        size_bytes = len(f.getbuffer())
                    except Exception:
                        size_bytes = 0

                if size_bytes and size_bytes > cfg.max_upload_mb * 1024 * 1024:
                    st.warning(f"{f.name} terlalu besar (maks {cfg.max_upload_mb} MB).")
                    continue
                with st.spinner(f"Processing {f.name}..."):
                    try:
                        result = ingest_pdf(f.read(), f.name, user_id=active_user_id)
                    except ValueError as e:
                        st.warning(f"⚠️ {f.name}: {e}")
                        continue
                if result["chunks_added"] > 0:
                    st.success(f"✅ {f.name}: {result['chunks_added']} chunks added")
                else:
                    st.info(f"ℹ️ {f.name}: already indexed")

    st.divider()

    # ── Knowledge Base Stats ──────────────────────────────────────────────
    st.subheader("🗄️ Knowledge Base")
    col_a, col_b = st.columns(2)
    col_a.metric("Total Chunks", get_collection(active_user_id).count())
    docs = list_uploaded_docs(active_user_id)
    col_b.metric("Documents", len(docs))

    if docs:
        with st.expander("Manage documents"):
            for doc in docs[:20]:
                c1, c2 = st.columns([4, 1])
                c1.caption(f"{'📄' if doc['source']=='upload' else '📰'} {doc['title'][:40]}")
                if c2.button("🗑️", key=f"del_{doc['title']}", help="Delete"):
                    n = delete_document(doc["title"], active_user_id)
                    st.success(f"Deleted {n} chunks")
                    st.rerun()

    if st.button("🗑️ Clear All", use_container_width=True, type="secondary"):
        col = get_collection(active_user_id)
        all_ids = col.get()["ids"]
        if all_ids:
            col.delete(ids=all_ids)
        st.session_state.messages = []
        st.session_state.openalex_results = []
        st.rerun()

    st.divider()
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ─── Main Chat ───────────────────────────────────────────────────────────────
st.title("🔬 Research Assistant")
st.caption("Ask questions about your papers. I'll answer with citations from OpenAlex and uploaded PDFs.")

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("references"):
            with st.expander(f"📚 References ({len(msg['references'])})"):
                for i, ref in enumerate(msg["references"], 1):
                    badge = (
                        '<span class="badge-openalex">OpenAlex</span>'
                        if ref["source"] == "openalex"
                        else '<span class="badge-upload">Uploaded</span>'
                    )
                    link = f'<a href="{ref["url"]}" target="_blank">{ref["title"]}</a>' if ref["url"] else ref["title"]
                    st.markdown(
                        f'<div class="ref-card">'
                        f'[{i}] {badge} {link}<br>'
                        f'<span style="color:#888">{ref["authors"]} · {ref["published"]} · '
                        f'score: {ref["relevance_score"]:.2f}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

# Chat input
if prompt := st.chat_input("Ask a research question..."):
    if cfg.require_user_id and not active_user_id:
        st.warning("User ID wajib diisi untuk memisahkan database per akun.")
        st.stop()
    if get_collection(active_user_id).count() == 0:
        st.warning("⚠️ No documents in database yet. Search OpenAlex or upload a PDF first!")
        st.stop()

    cfg = get_settings()
    groq_key = st.session_state.get("groq_api_key") or cfg.groq_api_key
    if not groq_key:
        st.error("Groq API key belum diisi. Isi di sidebar atau .env.")
        st.stop()

    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build history for Groq (exclude references metadata)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
        if m["role"] in ("user", "assistant")
    ]

    # Get RAG response
    with st.chat_message("assistant"):
        with st.spinner("Searching knowledge base and thinking..."):
            result = ask(
                prompt,
                chat_history=history,
                groq_api_key=groq_key,
                user_id=active_user_id,
            )

        st.markdown(result.answer)

        # Show references
        if result.references:
            source_summary = []
            if result.openalex_papers_used:
                source_summary.append(f"{result.openalex_papers_used} OpenAlex")
            if result.uploaded_docs_used:
                source_summary.append(f"{result.uploaded_docs_used} uploaded")
            label = " · ".join(source_summary)

            with st.expander(f"📚 References ({len(result.references)}) — {label}"):
                for i, ref in enumerate(result.references, 1):
                    badge = (
                        '<span class="badge-openalex">OpenAlex</span>'
                        if ref.source == "openalex"
                        else '<span class="badge-upload">Uploaded</span>'
                    )
                    link = (f'<a href="{ref.url}" target="_blank">{ref.title}</a>'
                            if ref.url else ref.title)
                    st.markdown(
                        f'<div class="ref-card">'
                        f'[{i}] {badge} {link}<br>'
                        f'<span style="color:#888">{ref.authors} · {ref.published} · '
                        f'relevance: {ref.relevance_score:.2f}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    # Save to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": result.answer,
        "references": [
            {
                "title": r.title,
                "authors": r.authors,
                "published": r.published,
                "url": r.url,
                "source": r.source,
                "relevance_score": r.relevance_score,
            }
            for r in result.references
        ],
    })
