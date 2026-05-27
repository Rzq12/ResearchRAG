import streamlit as st
import sys
import os
import httpx

# Make sure app/ is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_chroma, get_collection, get_parent_collection
from app.openalex_service import search_openalex, ingest_openalex_abstracts, fetch_citation_network
from app.pdf_service import ingest_pdf, list_uploaded_docs, delete_document
from app.rag import ask, ask_stream, summarize_document, generate_query_suggestions
from app.config import get_settings
from app.fulltext_service import fetch_fulltext_batch
from app.auth import init_auth_db, login_user, register_user
from app.semantic_search import semantic_search
from app.topic_classifier import classify_topics_batch, topic_badge_html, RESEARCH_TOPICS

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ResearchRAG",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* ── App styles ─────────────────────────── */
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

    /* ── Auth page styles ───────────────────── */
    .auth-hero {
        text-align: center;
        padding: 2rem 0 1.5rem;
    }
    .auth-hero h1 {
        font-size: 2.6rem;
        font-weight: 800;
        background: linear-gradient(135deg, #6366f1, #8b5cf6, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 0.3rem;
    }
    .auth-hero p {
        color: #64748b;
        font-size: 1rem;
    }
    .auth-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(99,102,241,0.2);
        border-radius: 20px;
        padding: 2rem 2.5rem;
        box-shadow: 0 20px 60px rgba(99,102,241,0.08);
    }
    .auth-divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(99,102,241,0.3), transparent);
        margin: 1.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ─── Init ────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Initializing...")
def startup():
    init_chroma()
    init_auth_db()
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
if "fulltext_pdf_urls" not in st.session_state:
    st.session_state.fulltext_pdf_urls = {}
if "query_suggestions" not in st.session_state:
    st.session_state.query_suggestions = []
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None
if "doc_summaries" not in st.session_state:
    st.session_state.doc_summaries = {}
if "topic_labels" not in st.session_state:
    # dict: openalex_id → topic label string
    st.session_state.topic_labels = {}
if "citation_cache" not in st.session_state:
    # dict: openalex_id → {ref_id: ref_title}
    st.session_state.citation_cache = {}
# Auth state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_user" not in st.session_state:
    st.session_state.current_user = ""
if "display_name" not in st.session_state:
    st.session_state.display_name = ""

# Pre-populate API keys from .env on fresh session
if "groq_api_key" not in st.session_state and cfg.groq_api_key:
    st.session_state["groq_api_key"] = cfg.groq_api_key
if "openalex_api_key" not in st.session_state and cfg.openalex_api_key:
    st.session_state["openalex_api_key"] = cfg.openalex_api_key


# ─── Login / Sign-Up page ────────────────────────────────────────────────────
def show_auth_page():
    """Full-screen login/signup UI. Calls st.stop() implicitly via return."""
    # Hide sidebar on auth page
    st.markdown(
        "<style>[data-testid='stSidebar']{display:none}</style>",
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1.6, 1])
    with center:
        # Hero
        st.markdown(
            """
            <div class="auth-hero">
                <h1>🔬 ResearchRAG</h1>
                <p>AI-powered research assistant &mdash; search, ingest &amp; ask your papers</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab_login, tab_signup = st.tabs(["🔑  Login", "✨  Sign Up"])

        # ── Login tab ────────────────────────────────────────────────────────
        with tab_login:
            st.markdown('<div class="auth-divider"></div>', unsafe_allow_html=True)
            uname_l = st.text_input(
                "Username", key="login_username", placeholder="your_username"
            )
            pwd_l = st.text_input(
                "Password", type="password", key="login_password",
                placeholder="••••••••"
            )
            st.markdown("")
            if st.button("Login  →", use_container_width=True, type="primary"):
                if not uname_l.strip() or not pwd_l:
                    st.error("Isi username dan password terlebih dahulu.")
                else:
                    ok, msg, dname = login_user(uname_l, pwd_l)
                    if ok:
                        st.session_state.logged_in = True
                        st.session_state.current_user = uname_l.strip().lower()
                        st.session_state.display_name = dname
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        # ── Sign-up tab ──────────────────────────────────────────────────────
        with tab_signup:
            st.markdown('<div class="auth-divider"></div>', unsafe_allow_html=True)
            uname_r = st.text_input(
                "Username", key="reg_username",
                placeholder="min. 3 karakter, huruf/angka/_",
            )
            dname_r = st.text_input(
                "Display name", key="reg_displayname",
                placeholder="Nama yang ditampilkan (opsional)",
            )
            pwd_r = st.text_input(
                "Password", type="password", key="reg_password",
                placeholder="min. 6 karakter",
            )
            pwd_r2 = st.text_input(
                "Confirm password", type="password", key="reg_password2",
                placeholder="Ulangi password",
            )
            st.markdown("")
            if st.button("Buat Akun  →", use_container_width=True, type="primary"):
                if not uname_r.strip() or not pwd_r:
                    st.error("Username dan password wajib diisi.")
                elif pwd_r != pwd_r2:
                    st.error("Password dan konfirmasi tidak cocok.")
                else:
                    ok, msg = register_user(uname_r, dname_r, pwd_r)
                    if ok:
                        st.success(msg + " Silakan klik tab Login.")
                    else:
                        st.error(msg)

        st.markdown(
            "<br><p style='text-align:center;color:#94a3b8;font-size:0.78rem'>"
            "Data tersimpan lokal &middot; password tidak pernah dikirim ke server eksternal</p>",
            unsafe_allow_html=True,
        )


# ─── Auth gate ───────────────────────────────────────────────────────────────
if not st.session_state.logged_in:
    show_auth_page()
    st.stop()


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔬 ResearchRAG")
    # Logged-in user badge
    st.markdown(
        f"<div style='background:linear-gradient(135deg,#6366f1,#8b5cf6);"
        f"padding:8px 14px;border-radius:10px;margin-bottom:4px'>"
        f"<span style='color:white;font-size:0.85rem'>👤 </span>"
        f"<strong style='color:white'>{st.session_state.display_name}</strong>"
        f"<span style='color:rgba(255,255,255,0.6);font-size:0.75rem'> @{st.session_state.current_user}</span></div>",
        unsafe_allow_html=True,
    )
    if st.button("🚪 Logout", use_container_width=True):
        # Clear auth state but keep API keys
        st.session_state.logged_in = False
        st.session_state.current_user = ""
        st.session_state.display_name = ""
        st.session_state.messages = []
        st.session_state.openalex_results = []
        st.session_state.query_suggestions = []
        st.session_state.doc_summaries = {}
        st.rerun()

    groq_key = st.text_input(
        "Groq API key",
        type="password",
        key="groq_api_key",
        help="Stored in session only. Leave empty to use .env",
    )
    _key_in_session = bool(st.session_state.get("groq_api_key"))
    _key_from_env   = bool(cfg.groq_api_key)
    if _key_in_session:
        st.caption("✅ Groq key active" + (" (from .env)" if _key_from_env and not groq_key else " (from sidebar)"))
    else:
        st.caption("⚠️ Groq key not set")

    # active_user_id comes from the logged-in user
    active_user_id = st.session_state.current_user or None

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

    ingest_mode = st.radio(
        "Ingest mode",
        options=["Abstracts only", "Full-text (Open Access)", "Both"],
        index=0,
        horizontal=True,
        help=(
            "**Abstracts only** — cepat, selalu tersedia.\n"
            "**Full-text** — download PDF open-access via Semantic Scholar & Unpaywall (lebih lambat).\n"
            "**Both** — ingest abstrak dulu, lalu cari full-text."
        ),
    )

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

                # ── Abstract ingestion ────────────────────────────────────────
                if ingest_mode in ("Abstracts only", "Both"):
                    with st.spinner("Ingesting abstracts into ChromaDB..."):
                        ingest_openalex_abstracts(works, user_id=active_user_id)
                    st.success(f"✅ {len(works)} abstracts ingested!")

                    # Auto-generate query suggestions
                    _groq_key = st.session_state.get("groq_api_key") or cfg.groq_api_key
                    if _groq_key:
                        with st.spinner("💡 Generating query suggestions..."):
                            st.session_state.query_suggestions = generate_query_suggestions(
                                works, groq_api_key=_groq_key
                            )

                # ── Full-text ingestion ────────────────────────────────────
                if ingest_mode in ("Full-text (Open Access)", "Both"):
                    status_ph = st.empty()
                    def _cb(msg: str):
                        status_ph.caption(msg)

                    with st.spinner("Fetching full-text PDFs (Semantic Scholar / Unpaywall)..."):
                        ft_result = fetch_fulltext_batch(
                            works,
                            user_id=active_user_id,
                            status_callback=_cb,
                        )
                    status_ph.empty()

                    fetched  = ft_result["fetched"]
                    skipped  = ft_result["skipped"]
                    failed   = ft_result["failed"]

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
                            src    = f" [{d['source']}]" if d.get("source") else ""
                            chunks = f" — {d['chunks']} chunks" if d.get("chunks") else ""
                            st.caption(f"{icon} {d['title'][:60]}{src}{chunks}")

                    # Store PDF URLs in session state for download links
                    for d in ft_result["details"]:
                        if d.get("pdf_url"):
                            st.session_state.fulltext_pdf_urls[d["title"]] = {
                                "url": d["pdf_url"],
                                "source": d.get("source", ""),
                            }
            else:
                st.error("No works found.")

            # ── Auto-classify topics after ingest ──────────────────────────
            if works:
                _groq_key_topic = st.session_state.get("groq_api_key") or cfg.groq_api_key
                if _groq_key_topic:
                    unclassified = [
                        w for w in works
                        if w.openalex_id not in st.session_state.topic_labels
                    ]
                    if unclassified:
                        with st.spinner("🏷️ Classifying paper topics..."):
                            labels = classify_topics_batch(
                                unclassified,
                                groq_api_key=_groq_key_topic,
                            )
                            st.session_state.topic_labels.update(labels)

    # Show last search results + download
    if st.session_state.openalex_results:
        works_res = st.session_state.openalex_results
        with st.expander(f"📄 OpenAlex results ({len(works_res)} works)"):
            for w in works_res:
                col_t, col_dl = st.columns([5, 1])

                # Topic badge
                topic_label = st.session_state.topic_labels.get(w.openalex_id, "")
                badge_html  = topic_badge_html(topic_label) if topic_label else ""

                col_t.markdown(
                    f"**[{w.title}]({w.url})**&nbsp;&nbsp;{badge_html}",
                    unsafe_allow_html=True,
                )
                # Authors + concepts
                concepts_str = " · ".join(w.concepts[:3]) if w.concepts else ""
                meta_line = f"{', '.join(w.authors[:2])} · {w.published}"
                if concepts_str:
                    meta_line += f"  |  🔑 {concepts_str}"
                if w.citation_count:
                    meta_line += f"  |  📊 {w.citation_count} citations"
                col_t.caption(meta_line)

                # Full-text PDF link if available
                ft_info = st.session_state.fulltext_pdf_urls.get(w.title)
                if ft_info and ft_info.get("url"):
                    col_dl.markdown(
                        f'<a href="{ft_info["url"]}" target="_blank" '
                        f'title="Download full-text PDF ({ft_info["source"]})">📅 PDF</a>',
                        unsafe_allow_html=True,
                    )

                # Citation network expander
                if w.referenced_works:
                    _cite_key = f"cite_{w.openalex_id}"
                    if st.button(
                        f"🔗 References ({len(w.referenced_works)})",
                        key=_cite_key,
                    ):
                        if w.openalex_id not in st.session_state.citation_cache:
                            with st.spinner("Fetching citation network..."):
                                refs = fetch_citation_network(
                                    w.openalex_id,
                                    api_key=st.session_state.get("openalex_api_key"),
                                )
                                st.session_state.citation_cache[w.openalex_id] = refs

                    if w.openalex_id in st.session_state.citation_cache:
                        refs = st.session_state.citation_cache[w.openalex_id]
                        if refs:
                            for ref_id, ref_title in list(refs.items())[:15]:
                                short = ref_id.replace("https://openalex.org/", "")
                                st.caption(
                                    f"&nbsp;&nbsp;&nbsp;↳ [{ref_title[:80]}]({ref_id})",
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.caption("  (No reference data available)")

            st.divider()
            # ── Download abstracts ────────────────────────────────────
            import json as _json
            # Build .txt content
            txt_lines = []
            for i, w in enumerate(works_res, 1):
                txt_lines.append(f"[{i}] {w.title}")
                if w.authors:
                    txt_lines.append(f"Authors : {', '.join(w.authors)}")
                txt_lines.append(f"Published: {w.published}")
                txt_lines.append(f"URL      : {w.url}")
                txt_lines.append(f"Abstract :\n{w.abstract}")
                txt_lines.append("-" * 60)
            txt_content = "\n".join(txt_lines)

            # Build .json content
            json_content = _json.dumps(
                [
                    {
                        "title": w.title,
                        "authors": w.authors,
                        "published": w.published,
                        "url": w.url,
                        "abstract": w.abstract,
                    }
                    for w in works_res
                ],
                indent=2,
                ensure_ascii=False,
            )

            dl1, dl2 = st.columns(2)
            dl1.download_button(
                label="⬇️ Download Abstracts (.txt)",
                data=txt_content.encode("utf-8"),
                file_name="abstracts.txt",
                mime="text/plain",
                use_container_width=True,
            )
            dl2.download_button(
                label="⬇️ Download Abstracts (.json)",
                data=json_content.encode("utf-8"),
                file_name="abstracts.json",
                mime="application/json",
                use_container_width=True,
            )

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
                    coverage = result.get("coverage")
                    if coverage:
                        pct = coverage.coverage_pct
                        icon_cv = "✅" if pct == 100 else ("⚠️" if pct >= 80 else "❌")
                        color   = "green" if pct == 100 else ("orange" if pct >= 80 else "red")
                        st.success(
                            f"**{f.name}** — {result['chunks_added']} child chunks + "
                            f"{result['parents_added']} parent chunks"
                        )
                        st.markdown(
                            f"<div style='border-left:3px solid {color};padding:6px 12px;"
                            f"border-radius:0 6px 6px 0;background:rgba(0,0,0,0.2);margin-bottom:8px'>"
                            f"{icon_cv} <b>Coverage: {pct}%</b> "
                            f"({coverage.covered_pages}/{coverage.total_pages} pages)"
                            f"{'  |  🔧 ' + str(coverage.fallback_used) + ' fallback chunks' if coverage.fallback_used else ''}"
                            f"{'  |  ❌ Missing: ' + str(coverage.missing_pages) if coverage.missing_pages else ''}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.success(f"✅ {f.name}: {result['chunks_added']} chunks added")
                else:
                    st.info(f"ℹ️ {f.name}: already indexed")

            # Generate suggestions from uploaded PDF titles
            _groq_key = st.session_state.get("groq_api_key") or cfg.groq_api_key
            if _groq_key:
                pdf_titles = [f.name.replace(".pdf", "") for f in uploaded_files]
                with st.spinner("💡 Generating query suggestions..."):
                    st.session_state.query_suggestions = generate_query_suggestions(
                        pdf_titles, groq_api_key=_groq_key
                    )

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
                icon = "📄" if doc["source"] == "upload" else "📰"
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.caption(f"{icon} {doc['title'][:38]}")

                # Summarize button — stores result in session_state, shown OUTSIDE this expander
                if c2.button("📝", key=f"sum_{doc['title']}", help="Summarize"):
                    _groq_key = st.session_state.get("groq_api_key") or cfg.groq_api_key
                    if not _groq_key:
                        st.warning("⚠️ Groq API key diperlukan untuk summarize.")
                    else:
                        with st.spinner(f"Summarizing {doc['title'][:30]}..."):
                            summary = summarize_document(
                                doc["title"], user_id=active_user_id, groq_api_key=_groq_key
                            )
                        st.session_state.doc_summaries[doc["title"]] = summary

                # Delete button
                if c3.button("🗑️", key=f"del_{doc['title']}", help="Delete"):
                    n = delete_document(doc["title"], active_user_id)
                    # Also clear any cached summary for this doc
                    st.session_state.doc_summaries.pop(doc["title"], None)
                    st.success(f"Deleted {n} chunks")
                    st.rerun()

        # ── Show doc summaries OUTSIDE the Manage expander (no nesting) ──────────
        for title, summary_text in st.session_state.doc_summaries.items():
            st.markdown(f"📝 **Summary: {title[:50]}**")
            st.markdown(summary_text)
            if st.button("❌ Close summary", key=f"close_sum_{title}"):
                st.session_state.doc_summaries.pop(title, None)
                st.rerun()
            st.divider()


    if st.button("🗑️ Clear All", use_container_width=True, type="secondary"):
        col = get_collection(active_user_id)
        all_ids = col.get()["ids"]
        if all_ids:
            col.delete(ids=all_ids)
        st.session_state.messages = []
        st.session_state.openalex_results = []
        st.session_state.fulltext_pdf_urls = {}
        st.session_state.query_suggestions = []
        st.session_state.topic_labels = {}
        st.session_state.citation_cache = {}
        st.session_state.doc_summaries = {}
        # Also clear parent collection
        parent_col = get_parent_collection(active_user_id)
        parent_ids = parent_col.get()["ids"]
        if parent_ids:
            parent_col.delete(ids=parent_ids)
        st.rerun()

    st.divider()
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    # ── Export chat ───────────────────────────────────────────
    if st.session_state.messages:
        chat_md_lines = ["# Research Assistant — Chat Export\n"]
        for m in st.session_state.messages:
            role_icon = "👤" if m["role"] == "user" else "🤖"
            chat_md_lines.append(f"### {role_icon} {m['role'].capitalize()}\n")
            chat_md_lines.append(m["content"] + "\n")
            if m.get("references"):
                chat_md_lines.append("**References:**\n")
                for i, r in enumerate(m["references"], 1):
                    link = f"[{r['title']}]({r['url']})" if r.get("url") else r["title"]
                    chat_md_lines.append(f"{i}. {link} ({r.get('published', '')})\n")
            chat_md_lines.append("---\n")
        chat_md = "\n".join(chat_md_lines)
        st.download_button(
            label="⬇️ Export Chat (.md)",
            data=chat_md.encode("utf-8"),
            file_name="chat_export.md",
            mime="text/markdown",
            use_container_width=True,
        )

# ─── Main Content Tabs ───────────────────────────────────────────────────────
tab_chat, tab_search = st.tabs(["💬 Chat", "🔍 Semantic Search"])

with tab_chat:
    st.title("🔬 Research Assistant")
    st.caption("Ask questions about your papers. I'll answer with citations from OpenAlex and uploaded PDFs.")

    # ── Query Suggestions ─────────────────────────────────────────────────────────
    if st.session_state.query_suggestions:
        st.markdown("**💡 Suggested questions** *(click to ask)*")
        cols = st.columns(min(len(st.session_state.query_suggestions), 3))
        for i, suggestion in enumerate(st.session_state.query_suggestions):
            col = cols[i % 3]
            if col.button(
                suggestion,
                key=f"suggestion_{i}",
                use_container_width=True,
                help="Click to ask this question",
            ):
                st.session_state.pending_query = suggestion
                st.rerun()
        st.divider()

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

    # ── Chat Input (typed or from suggestion button) ──────────────────────────────
    typed_input = st.chat_input("Ask a research question...")

    # Consume pending query from suggestion click (one shot)
    if st.session_state.pending_query:
        prompt = st.session_state.pending_query
        st.session_state.pending_query = None
    else:
        prompt = typed_input

    if prompt:
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

        # Build history for Groq
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[:-1]
            if m["role"] in ("user", "assistant")
        ]

        # ── Streaming RAG response ────────────────────────────────────────────────
        with st.chat_message("assistant"):
            gen, refs, oa_count, up_count = ask_stream(
                prompt,
                chat_history=history,
                groq_api_key=groq_key,
                user_id=active_user_id,
            )
            full_answer = st.write_stream(gen)

            if refs:
                source_parts = []
                if oa_count:
                    source_parts.append(f"{oa_count} OpenAlex")
                if up_count:
                    source_parts.append(f"{up_count} uploaded")
                label = " · ".join(source_parts)

                with st.expander(f"📚 References ({len(refs)}) — {label}"):
                    for i, ref in enumerate(refs, 1):
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

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_answer,
            "references": [
                {
                    "title": r.title,
                    "authors": r.authors,
                    "published": r.published,
                    "url": r.url,
                    "source": r.source,
                    "relevance_score": r.relevance_score,
                }
                for r in refs
            ],
        })


# ─── Semantic Search Panel ────────────────────────────────────────────────────
with tab_search:
    st.title("🔍 Semantic Search")
    st.caption(
        "Search your knowledge base directly — no LLM, no hallucination. "
        "See raw chunks with similarity scores. Useful for debugging retrieval quality."
    )

    if get_collection(active_user_id).count() == 0:
        st.info("⚠️ Knowledge base is empty. Ingest papers or upload PDFs first.")
    else:
        ss_col1, ss_col2, ss_col3 = st.columns([4, 2, 2])
        ss_query   = ss_col1.text_input(
            "Search query",
            placeholder="e.g. attention mechanism self-attention",
            key="semantic_search_query",
        )
        ss_top_k   = ss_col2.slider("Results", 5, 30, 15, key="semantic_search_k")
        ss_ctype   = ss_col3.selectbox(
            "Filter by type",
            options=["All", "text", "table", "formula", "heading", "list", "fallback_page"],
            key="semantic_search_type",
        )
        ss_min_score = st.slider(
            "Min similarity score", 0.0, 1.0, 0.0, 0.05,
            key="semantic_search_min_score",
        )

        if st.button("🔍 Search", key="semantic_search_btn", type="primary"):
            if not ss_query.strip():
                st.warning("Enter a search query.")
            else:
                with st.spinner("Searching..."):
                    ct_filter = None if ss_ctype == "All" else ss_ctype
                    results   = semantic_search(
                        query               = ss_query,
                        user_id             = active_user_id,
                        top_k               = ss_top_k,
                        content_type_filter = ct_filter,
                        min_score           = ss_min_score,
                    )

                st.markdown(f"**{len(results)} results** for: *{ss_query}*")
                st.divider()

                for hit in results:
                    score     = hit["score"]
                    score_bar = int(score * 10)  # 0-10
                    score_col = "#10b981" if score >= 0.5 else ("#f59e0b" if score >= 0.3 else "#ef4444")

                    ct_label = hit["content_type"].replace("_", " ").title()
                    page_info = f"p.{hit['page_num']}" if hit["page_num"] != "?" else ""
                    sec_info  = f" › {hit['section_title'][:40]}" if hit["section_title"] else ""
                    role_info = f" [{hit['chunk_role']}]" if hit.get("chunk_role") else ""

                    st.markdown(
                        f"""
<div style='border:1px solid rgba(255,255,255,0.08);border-radius:8px;
     padding:12px 16px;margin-bottom:10px;background:rgba(255,255,255,0.02)'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px'>
    <span style='font-size:12px;color:#94a3b8'>
      📄 <b>{hit['title'][:50]}</b>&nbsp;&nbsp;
      🏷 <code>{ct_label}</code>&nbsp;&nbsp;
      {page_info}{sec_info}{role_info}
    </span>
    <span style='background:{score_col};color:white;padding:2px 8px;
          border-radius:12px;font-size:11px;font-weight:700'>
      {score:.3f}
    </span>
  </div>
  <div style='font-size:13px;line-height:1.5;color:#e2e8f0'>{hit['text'][:500]}{'…' if len(hit['text']) > 500 else ''}</div>
</div>""",
                        unsafe_allow_html=True,
                    )
