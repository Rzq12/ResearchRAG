FROM python:3.11-slim

WORKDIR /app

# System deps for PyMuPDF + the reverse proxy that fronts Streamlit and the API.
RUN apt-get update && apt-get install -y \
    libmupdf-dev \
    libfreetype6-dev \
    tesseract-ocr \
    poppler-utils \
    nginx \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# CPU-only torch FIRST — otherwise sentence-transformers pulls the CUDA build
# (~6 GB of nvidia libs that a CPU container never uses).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# FastAPI wrapper deps (thin layer on top of the RAG stack above).
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# Pre-download models at build time (faster cold start; ~1.6 GB total).
# Must match EMBEDDING_MODEL / RERANKER_MODEL in app/config.py — a mismatch
# means the container re-downloads at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('intfloat/multilingual-e5-base')"
RUN python -c "from sentence_transformers import CrossEncoder; \
CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')"

COPY . .

# Persistent volume mount point (ChromaDB index + users.db)
RUN mkdir -p /app/data/chroma_db

# Combined launcher: nginx (public) → Streamlit + FastAPI (internal).
# Drop the distro's default site so it can't clash with our server block.
RUN rm -f /etc/nginx/sites-enabled/default && chmod +x /app/deploy/start.sh

# ── Least privilege ──────────────────────────────────────────────────────────
# PyMuPDF/pdfplumber parse entirely untrusted input; running that as root means
# any parser RCE owns the container. nginx normally wants root to bind :80 and
# to write /var/{log,lib,run}/nginx — we listen on a high port and hand those
# paths to appuser instead, so no privileged user is needed at runtime.
RUN adduser --disabled-password --gecos "" --uid 10001 appuser \
    && mkdir -p /var/cache/nginx /var/log/nginx /var/lib/nginx /var/run \
    && chown -R appuser:appuser /app /var/cache/nginx /var/log/nginx /var/lib/nginx /var/run \
    && touch /var/run/nginx.pid && chown appuser:appuser /var/run/nginx.pid \
    && chown -R appuser:appuser /etc/nginx/conf.d \
    # `user www-data;` only applies when the master runs as root. We don't, so
    # nginx would warn on every start; drop it to keep the logs meaningful.
    && sed -i '/^user /d' /etc/nginx/nginx.conf

USER appuser

EXPOSE 8501

# Probes BOTH services: a dead API behind a live Streamlit used to report
# healthy, so the platform never restarted it.
HEALTHCHECK --interval=30s --timeout=8s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request as u; \
u.urlopen('http://localhost:8501/_stcore/health', timeout=5); \
u.urlopen('http://localhost:8501/api/health', timeout=5)"

# Runs Streamlit AND the FastAPI wrapper behind nginx on one port.
# To serve Streamlit only (the old behaviour), override with:
#   CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0"]
CMD ["bash", "/app/deploy/start.sh"]
