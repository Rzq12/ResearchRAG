FROM python:3.11-slim

WORKDIR /app

# System deps for PyMuPDF
RUN apt-get update && apt-get install -y \
    libmupdf-dev \
    libfreetype6-dev \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# CPU-only torch FIRST — otherwise sentence-transformers pulls the CUDA build
# (~6 GB of nvidia libs that a CPU container never uses).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

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

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4)"

CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0"]
