---
title: ResearchRAG
emoji: 🔬
colorFrom: indigo
colorTo: cyan
sdk: docker
app_port: 8501
pinned: false
---

# 🔬 ResearchRAG

AI-powered research assistant — cari, ingest, dan tanya paper ilmiah menggunakan **OpenAlex**, **ChromaDB**, dan **Groq LLM**. Dilengkapi fitur autentikasi, streaming, summarizer, dan query suggestion.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Groq](https://img.shields.io/badge/Groq-LLaMA_3.3_70B-f55036)](https://console.groq.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Fitur

| Kategori          | Fitur                                                                      |
| ----------------- | -------------------------------------------------------------------------- |
| **Auth**          | Login & Sign Up — per-user knowledge base terisolasi di SQLite             |
| **Ingestion**     | Search OpenAlex real-time, pilih mode: _Abstracts only / Full-text / Both_ |
| **Ingestion**     | Upload PDF sendiri (dengan OCR fallback untuk scanned PDF)                 |
| **Ingestion**     | Full-text open access via Semantic Scholar & Unpaywall                     |
| **RAG**           | Streaming jawaban token-by-token (tidak perlu nunggu spinner)              |
| **RAG**           | Multi-turn conversation dengan chat history                                |
| **RAG**           | Similarity threshold — chunk tidak relevan difilter sebelum masuk LLM      |
| **RAG**           | Sitasi `[1]`, `[2]` per jawaban dengan relevance score                     |
| **Produktivitas** | 💡 Query suggestions — 5 pertanyaan otomatis setelah ingest                |
| **Produktivitas** | 📝 Paper summarizer — ringkasan 5-seksi per dokumen                        |
| **Download**      | Export abstrak (`.txt` / `.json`), full-text PDF link, export chat (`.md`) |
| **KB Management** | Lihat, summarize, dan hapus dokumen per-user                               |

---

## 🏗️ Arsitektur

```
User (login) ──► Auth Gate (SQLite)
                      │
                      ▼
              [Streamlit UI]
             /              \
  Search OpenAlex          Upload PDF
  (Abstracts / Full-text)  (+ OCR fallback)
             \              /
              ▼            ▼
           [Sentence Transformer]
           all-MiniLM-L6-v2 (local)
                    │
                    ▼
             [ChromaDB] ← per-user collection
          (cosine similarity, threshold filter)
                    │
              Top-K Chunks
                    │
                    ▼
      [Groq LLM — streaming]
      llama-3.3-70b-versatile
                    │
                    ▼
       Answer + Citations [1][2]
```

---

## 🚀 Setup Lokal

### 1. Clone & install

```bash
git clone https://github.com/username/ResearchRAG.git
cd ResearchRAG

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Setup environment

```bash
cp .env.example .env
# Edit .env dan isi minimal:
#   GROQ_API_KEY=gsk_...
# Dapatkan API key gratis di: https://console.groq.com
```

### 3. Jalankan

```bash
streamlit run streamlit_app.py
# Buka http://localhost:8501
```

### 4. (Opsional) OCR untuk scanned PDF

Aktifkan dengan uncomment di `requirements.txt`:

```
pytesseract==0.3.13
pdf2image==1.17.0
```

Lalu install Tesseract binary:

- **Windows**: [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki)
- **Linux/macOS**: `sudo apt install tesseract-ocr` / `brew install tesseract`

---

## 📖 Cara Pakai

1. **Buka app** → halaman Login muncul (sidebar disembunyikan)
2. **Sign Up** → buat akun (username + password, tersimpan lokal di `data/users.db`)
3. **Login** → masuk ke dashboard utama
4. **Groq API key** → isi di sidebar, atau set `GROQ_API_KEY` di `.env` (auto pre-filled)
5. **Cari paper** → Search OpenAlex, pilih _Ingest mode_, klik _Search & Ingest_
6. **Upload PDF** → drag & drop, klik _Ingest PDFs_
7. **Tanya** → ketik pertanyaan di chat, atau klik salah satu _Suggested questions_
8. **Summarize** → di sidebar Knowledge Base, klik 📝 per dokumen

---

## 🔧 Konfigurasi `.env`

| Variable               | Default                   | Keterangan                                                            |
| ---------------------- | ------------------------- | --------------------------------------------------------------------- |
| `GROQ_API_KEY`         | _(wajib)_                 | API key Groq — gratis di [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL`           | `llama-3.3-70b-versatile` | Model Groq yang digunakan                                             |
| `CHROMA_PATH`          | `./data/chroma_db`        | Path penyimpanan ChromaDB                                             |
| `TOP_K_RETRIEVAL`      | `6`                       | Jumlah chunks yang diambil per query                                  |
| `SIMILARITY_THRESHOLD` | `0.2`                     | Min cosine similarity; chunk di bawah ini difilter                    |
| `MAX_TOKENS_RESPONSE`  | `1500`                    | Max tokens jawaban LLM                                                |
| `CHUNK_SIZE`           | `800`                     | Panjang tiap chunk (karakter)                                         |
| `CHUNK_OVERLAP`        | `150`                     | Overlap antar chunk                                                   |
| `TOP_K_OPENALEX`       | `5`                       | Jumlah works dari OpenAlex per search                                 |
| `OPENALEX_API_KEY`     | _(opsional)_              | API key OpenAlex                                                      |
| `OPENALEX_MAILTO`      | _(opsional)_              | Email untuk polite usage OpenAlex                                     |
| `FULLTEXT_MAILTO`      | _(opsional)_              | Email untuk Unpaywall polite pool                                     |
| `FULLTEXT_MAX_PDF_MB`  | `30`                      | Ukuran maks PDF yang akan didownload                                  |

---

## 📁 Struktur Proyek

```
ResearchRAG/
├── streamlit_app.py         # Frontend, auth gate & orchestration
├── app/
│   ├── auth.py              # Login/signup — SQLite + salted SHA-256
│   ├── config.py            # Settings (pydantic-settings, .env)
│   ├── database.py          # ChromaDB + embedding singleton
│   ├── chunker.py           # PDF extraction, OCR fallback & text chunking
│   ├── openalex_service.py  # OpenAlex search + abstract ingestion
│   ├── pdf_service.py       # PDF upload management
│   ├── fulltext_service.py  # Full-text via Semantic Scholar & Unpaywall
│   └── rag.py               # RAG pipeline — ask, ask_stream, summarize, suggestions
├── data/
│   ├── chroma_db/           # Per-user vector store (gitignored)
│   └── users.db             # Auth database (gitignored)
├── .streamlit/
│   └── config.toml          # Streamlit server config
├── Dockerfile
├── railway.json
├── requirements.txt
├── .env.example
└── README.md
```

---

## ☁️ Deploy ke Railway

1. Push ke GitHub:

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/username/ResearchRAG.git
git push -u origin main
```

2. Buka [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub** → pilih repo `ResearchRAG`

3. Tambahkan **Volume** untuk persistent storage:
   - Settings → Volumes → Mount path: `/app/data`
     > ⚠️ Mount ke `/app/data` agar ChromaDB **dan** `users.db` sama-sama persisten

4. Set **Environment Variables**:

   ```
   GROQ_API_KEY=gsk_...
   CHROMA_PATH=/app/data/chroma_db
   ```

5. Deploy otomatis via `railway.json`

---

## 🧪 Contoh Pertanyaan

- _"Apa itu attention mechanism dan bagaimana cara kerjanya?"_
- _"Jelaskan perbedaan BERT dan GPT dalam hal arsitektur"_
- _"Apa kelemahan RAG dibanding fine-tuning?"_
- _"What are the main contributions of the papers I uploaded?"_
- _"Bandingkan metodologi antar paper yang sudah saya ingest"_

---

## 🔐 Keamanan Autentikasi

- Password di-hash menggunakan **SHA-256 + random salt** (32 karakter)
- Tidak ada plain-text password yang disimpan
- Semua data tersimpan **lokal** — tidak dikirim ke server eksternal apapun
- Per-user knowledge base isolation via ChromaDB collection ID

---

## 📝 Lisensi

MIT © 2025
