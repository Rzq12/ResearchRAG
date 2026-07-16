---
title: ResearchRAG
emoji: 🔬
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8501
pinned: false
---

# 🔬 ResearchRAG

AI-powered research assistant — cari, ingest, dan tanya paper ilmiah menggunakan **OpenAlex**, **ChromaDB**, dan pilihan LLM dari **Groq** maupun **Google Gemini**. Dilengkapi fitur autentikasi, streaming, summarizer, reranker, semantic search panel, topic classifier, dan query suggestion.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Groq](https://img.shields.io/badge/Groq-Llama_4_Scout-f55036)](https://console.groq.com)
[![Gemini](https://img.shields.io/badge/Google-Gemini-4285F4?logo=google&logoColor=white)](https://aistudio.google.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Fitur

| Kategori          | Fitur                                                                                  |
| ----------------- | -------------------------------------------------------------------------------------- |
| **Auth**          | Login & Sign Up — per-user knowledge base terisolasi di SQLite                         |
| **Ingestion**     | Search OpenAlex real-time, pilih mode: _Abstracts only / Full-text / Both_             |
| **Ingestion**     | Upload PDF sendiri (dengan OCR fallback untuk scanned PDF)                             |
| **Ingestion**     | Full-text open access via Semantic Scholar & Unpaywall                                 |
| **RAG**           | Streaming jawaban token-by-token (tidak perlu nunggu spinner)                          |
| **RAG**           | Multi-turn conversation dengan chat history                                            |
| **RAG**           | Parent-Child retrieval — embed child chunk kecil, kirim parent chunk besar ke LLM      |
| **RAG**           | **Multilingual embedding** (`multilingual-e5-base`) — query Indonesia menemukan paper Inggris |
| **RAG**           | **HyDE** — LLM menulis 2 abstrak hipotetis sebagai query retrieval tambahan            |
| **RAG**           | **Hybrid retrieval** — BM25 (keyword/akronim) + vector search, fusi RRF (0.4/0.6)      |
| **RAG**           | **Reranker multilingual** (mMARCO cross-encoder), skor sigmoid [0,1], ON by default    |
| **RAG**           | **Relevance threshold + fallback** — KB tidak relevan → OpenAlex live → DuckDuckGo     |
| **RAG**           | **Reasoning `<think>`** — model bernalar dulu, tampil sebagai blok collapsible          |
| **RAG**           | Metadata filtering — filter retrieval per dokumen / section / tahun dari sidebar        |
| **RAG**           | Sitasi `[1]`, `[2]` per jawaban dengan relevance score + sitasi akademik (author, tahun, section) |
| **LLM**           | Triple provider: **Groq**, **Google Gemini**, & **self-hosted** (`hf:` — vLLM/TGI untuk model fine-tuned sendiri) |
| **Produktivitas** | 💡 Query suggestions — 5 pertanyaan otomatis setelah ingest                            |
| **Produktivitas** | 📝 Paper summarizer — ringkasan 5-seksi per dokumen                                    |
| **Produktivitas** | 🏷️ Topic classifier — label otomatis per paper (ML, NLP, CV, RAG, dll)                |
| **Produktivitas** | 🔍 Semantic Search panel — jelajahi knowledge base tanpa memanggil LLM                 |
| **Download**      | Export abstrak (`.txt` / `.json`), full-text PDF link, export chat (`.md`)             |
| **KB Management** | Lihat, summarize, dan hapus dokumen per-user                                           |

---

## 🏗️ Arsitektur

```
User (login) ──► Auth Gate (SQLite)
                      │
                      ▼
              [Streamlit UI]
             /              \
  Search OpenAlex          Upload PDF
  (Abstracts / Full-text)  (Advanced PDF Pipeline)
             \              /     |
              ▼            ▼      ▼
       Layout Analysis + Table Extraction
       (PyMuPDF + pdfplumber)
                     │
            Hierarchy Builder
            (section_path tracking)
                     │
          ┌──────────┴──────────┐
          │                     │
     Child Chunks          Parent Chunks
     (~180 words)          (~700 words)
     [embedded]            [sent to LLM]
                     │
         [Sentence Transformer]
   intfloat/multilingual-e5-base (local)
   prefix "passage:" / "query:" wajib
                     │
                     ▼
              [ChromaDB] ← per-user collection (v2)
                     │
      Query ─► [HyDE] LLM menulis 2 abstrak hipotetis
                     │  (query asli + hipotetis di-embed semua)
          ┌──────────┴──────────┐
          │                     │
   Vector Search           BM25 Keyword
   (semantic)              (akronim, nama author)
          └───────RRF 0.6/0.4───┘
                     │
  [Cross-Encoder Reranker — multilingual]
  mmarco-mMiniLMv2 · sigmoid → skor [0,1]
                     │
        skor Top-1 ≥ 0.5 ?
        ├─ ya  → Parent Chunks fetched (KB lokal)
        └─ tidak → fallback: OpenAlex live → DuckDuckGo
                     │
                     ▼
       [LLM — streaming]
       Groq (Llama / Qwen / GPT OSS)
    OR Google Gemini (Flash / Pro)
    OR self-hosted "hf:" (vLLM / TGI)
                     │
       <think> reasoning </think>
                     ▼
        Answer + Citations [1][2]
```

### 📏 Hasil evaluasi retrieval (30 query EN/ID/campur, `eval/`)

| Metrik | Baseline (MiniLM) | Final (e5 + hybrid + reranker) |
| --- | --- | --- |
| hit@1 | 0.60 | **0.97** |
| MRR@10 | 0.725 | **0.983** |
| MRR@10 (query Indonesia) | 0.475 | **1.00** |
| Latensi retrieval p95 (CPU) | 24 ms | 1.7 s |

Reproduksi: `python -m eval.run_eval --tag saya --compare eval/results/baseline.json`
Test case wajib (perlu API key): `python -m eval.test_case`

> ⚠️ **Migrasi dari versi lama:** embedding berubah 384-dim → 768-dim, koleksi
> ChromaDB lama tidak kompatibel. Data lama bisa dimigrasi tanpa hilang:
> `python -m scripts.reindex --apply` (teks chunk tersimpan di Chroma, jadi
> re-embed dilakukan dari data yang ada).

---

## 🤖 Model yang Didukung

| Provider       | Model                                        | Keterangan                        |
| -------------- | -------------------------------------------- | --------------------------------- |
| **Gemini**     | `gemini-3.5-flash` _(recommended)_           | Context besar, gratis             |
| **Gemini**     | `gemini-3.1-flash-lite`                      | Paling cepat & ringan             |
| **Gemini**     | `gemini-3.1-pro-preview`                     | Kualitas terbaik                  |
| **Groq/Meta**  | `meta-llama/llama-4-scout-17b-16e-instruct`  | 512k context window               |
| **Groq/Meta**  | `llama-3.3-70b-versatile`                    | Versi versatile 70B               |
| **Groq/Meta**  | `llama-3.1-8b-instant`                       | Paling cepat di Groq              |
| **Groq/Alibaba**| `qwen/qwen3-32b`                            | Qwen3 32B                         |
| **Groq native**| `groq/compound`, `groq/compound-mini`        | Model compound Groq               |
| **Groq/OpenAI**| `openai/gpt-oss-120b`, `openai/gpt-oss-20b` | GPT OSS via Groq                  |

Provider auto-detected dari nama model: prefix `gemini-` → Gemini, lainnya → Groq.

---

## 🚀 Setup Lokal

### 1. Clone & install

```bash
git clone https://github.com/riezqidr/ResearchRAG.git
cd ResearchRAG

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Setup environment

```bash
cp .env.example .env
# Edit .env dan isi minimal salah satu API key:
#   GROQ_API_KEY=gsk_...        → dapatkan gratis di https://console.groq.com
#   GEMINI_API_KEY=AIza...      → dapatkan gratis di https://aistudio.google.com/app/apikey
```

### 3. Jalankan

```bash
streamlit run streamlit_app.py
# Buka http://localhost:8501
```

### 4. (Opsional) OCR untuk scanned PDF

Sudah ter-include di `requirements.txt`. Cukup install Tesseract binary:

- **Windows**: [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki)
- **Linux**: `sudo apt install tesseract-ocr`
- **macOS**: `brew install tesseract`

### 5. (Opsional) Cross-encoder Reranker

Aktifkan dengan set `ENABLE_RERANKER=true` di `.env`. Model `cross-encoder/ms-marco-MiniLM-L-6-v2` (~80MB) akan diunduh otomatis pada penggunaan pertama.

---

## 📖 Cara Pakai

1. **Buka app** → halaman Login muncul (sidebar disembunyikan)
2. **Sign Up** → buat akun (username + password, tersimpan lokal di `data/users.db`)
3. **Login** → masuk ke dashboard utama
4. **Pilih LLM** → pilih provider & model di sidebar, isi API key Groq atau Gemini
5. **Cari paper** → Search OpenAlex, pilih _Ingest mode_, klik _Search & Ingest_
6. **Upload PDF** → drag & drop, klik _Ingest PDFs_ (pipeline advanced: layout + table + parent-child)
7. **Tanya** → ketik pertanyaan di chat, atau klik salah satu _Suggested questions_
8. **Semantic Search** → jelajahi knowledge base langsung tanpa LLM (debug retrieval)
9. **Summarize** → di sidebar Knowledge Base, klik 📝 per dokumen

---

## 🔧 Konfigurasi `.env`

| Variable                    | Default                                       | Keterangan                                                              |
| --------------------------- | --------------------------------------------- | ----------------------------------------------------------------------- |
| `GROQ_API_KEY`              | _(opsional)_                                  | API key Groq — gratis di [console.groq.com](https://console.groq.com)  |
| `GROQ_MODEL`                | `meta-llama/llama-4-scout-17b-16e-instruct`   | Model Groq default                                                      |
| `GEMINI_API_KEY`            | _(opsional)_                                  | API key Gemini — gratis di [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| `CHROMA_PATH`               | `./data/chroma_db`                            | Path penyimpanan ChromaDB                                               |
| `TOP_K_RETRIEVAL`           | `15`                                          | Jumlah child chunks yang diambil per query                              |
| `SIMILARITY_THRESHOLD`      | `0.1`                                         | Soft threshold cosine similarity (0.05–0.15 recommended)                |
| `MAX_TOKENS_RESPONSE`       | `2000`                                        | Max tokens jawaban LLM                                                  |
| `CHUNK_SIZE`                | `1200`                                        | Panjang chunk legacy (karakter) — untuk abstrak/teks pendek             |
| `CHUNK_OVERLAP`             | `200`                                         | Overlap chunk legacy                                                    |
| `CHILD_CHUNK_WORDS`         | `180`                                         | Target kata per child chunk (PDF pipeline)                              |
| `CHILD_CHUNK_OVERLAP_WORDS` | `30`                                          | Overlap kata antar child chunk                                          |
| `PARENT_CHUNK_WORDS`        | `700`                                         | Target kata per parent chunk                                            |
| `CHILDREN_PER_PARENT`       | `4`                                           | Jumlah child per parent chunk                                           |
| `ENABLE_RERANKER`           | `false`                                       | Aktifkan cross-encoder reranker (~80MB download pertama kali)           |
| `TOP_K_OPENALEX`            | `5`                                           | Jumlah works dari OpenAlex per search                                   |
| `OPENALEX_API_KEY`          | _(opsional)_                                  | API key OpenAlex                                                        |
| `OPENALEX_MAILTO`           | _(opsional)_                                  | Email untuk polite usage OpenAlex                                       |
| `FULLTEXT_MAILTO`           | _(opsional)_                                  | Email untuk Unpaywall polite pool                                       |
| `FULLTEXT_MAX_PDF_MB`       | `30`                                          | Ukuran maks PDF yang akan didownload                                    |

> **Catatan similarity threshold**: Dengan parent-child retrieval, threshold hanya berlaku sebagai soft check. Query ditolak hanya jika skor child terbaik < `SIMILARITY_THRESHOLD / 2`. Nilai 0.05–0.15 direkomendasikan.

---

## 📁 Struktur Proyek

```
ResearchRAG/
├── streamlit_app.py              # Frontend, auth gate & orchestration
├── app/
│   ├── auth.py                   # Login/signup — SQLite + salted SHA-256
│   ├── config.py                 # Settings (pydantic-settings, .env)
│   ├── database.py               # ChromaDB + embedding singleton
│   ├── chunker.py                # Advanced PDF pipeline: layout, table, parent-child
│   ├── openalex_service.py       # OpenAlex search + abstract ingestion
│   ├── pdf_service.py            # PDF upload management
│   ├── fulltext_service.py       # Full-text via Semantic Scholar & Unpaywall
│   ├── llm_client.py             # Unified LLM client (Groq + Gemini)
│   ├── rag.py                    # RAG pipeline — ask, ask_stream, summarize, suggestions
│   ├── reranker.py               # Cross-encoder reranker (opsional)
│   ├── semantic_search.py        # Vector search panel (tanpa LLM)
│   └── topic_classifier.py       # Topic labeling per paper via LLM
├── data/
│   ├── chroma_db/                # Per-user vector store (gitignored)
│   └── users.db                  # Auth database (gitignored)
├── .streamlit/
│   └── config.toml               # Streamlit server config
├── .github/
│   └── workflows/main.yml        # CI/CD sync ke Hugging Face Spaces
├── Dockerfile
├── railway.json
├── requirements.txt
├── .env.example
└── README.md
```

---

## ☁️ Deploy

### Railway

1. Push ke GitHub:

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/riezqidr/ResearchRAG.git
git push -u origin main
```

2. Buka [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub** → pilih repo `ResearchRAG`

3. Tambahkan **Volume** untuk persistent storage:
   - Settings → Volumes → Mount path: `/app/data`
     > ⚠️ Mount ke `/app/data` agar ChromaDB **dan** `users.db` sama-sama persisten

4. Set **Environment Variables**:

   ```
   GROQ_API_KEY=gsk_...
   # dan/atau
   GEMINI_API_KEY=AIza...
   CHROMA_PATH=/app/data/chroma_db
   ```

5. Deploy otomatis via `railway.json`

### Hugging Face Spaces

Sudah dikonfigurasi via `.github/workflows/main.yml` — setiap push ke branch `master` otomatis sync ke [HF Spaces](https://huggingface.co/spaces/riezqidr/ResearchRAG).

---

## 🧪 Contoh Pertanyaan

- _"Apa itu attention mechanism dan bagaimana cara kerjanya?"_
- _"Jelaskan perbedaan BERT dan GPT dalam hal arsitektur"_
- _"Apa kelemahan RAG dibanding fine-tuning?"_
- _"What are the main contributions of the papers I uploaded?"_
- _"Bandingkan metodologi antar paper yang sudah saya ingest"_
- _"Tampilkan tabel hasil eksperimen dari paper ini"_

---

## 🔐 Keamanan Autentikasi

- Password di-hash menggunakan **SHA-256 + random salt** (32 karakter)
- Tidak ada plain-text password yang disimpan
- Semua data tersimpan **lokal** — tidak dikirim ke server eksternal apapun
- Per-user knowledge base isolation via ChromaDB collection ID

---

## 📝 Lisensi

MIT © 2025
