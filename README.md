# 🔬 Research RAG Chatbot

Research assistant yang menjawab pertanyaan ilmiah dengan sitasi dari **OpenAlex** dan **PDF yang kamu upload**, menggunakan **ChromaDB + Groq LLM**.

## ✨ Fitur

- 🔍 **Search OpenAlex real-time** — cari paper by keyword, langsung diingest ke ChromaDB
- 📎 **Upload PDF sendiri** — paper apapun bisa dijadikan knowledge base
- 🔗 **Full-text open access** — otomatis cari & download PDF lengkap via Semantic Scholar & Unpaywall
- 💬 **Chat dengan sitasi** — setiap jawaban disertai referensi `[1]`, `[2]` yang bisa diklik
- 🧠 **Multi-turn conversation** — ingat konteks percakapan sebelumnya
- 🗄️ **Persistent storage** — ChromaDB tersimpan di disk, tidak hilang setelah restart
- 📊 **Relevance score** — setiap referensi menampilkan skor kemiripan semantik
- 🎯 **Similarity threshold** — chunk tidak relevan (< 0.3) difilter sebelum masuk LLM

## 🏗️ Arsitektur

```
User Query
    │
    ▼
[Streamlit UI]
   │
   ├── Search OpenAlex API ──► Abstracts ──► Chunking
   │                                             │
   └── Upload PDF ─────────► Extraction ──► Chunking
                                              │
                                              ▼
                                    [Sentence Transformer]
                                    (all-MiniLM-L6-v2, local)
                                              │
                                              ▼
                                       [ChromaDB]
                                    (cosine similarity)
                                              │
                                    Top-K Chunks Retrieved
                                              │
                                              ▼
                                     [Groq LLM API]
                                   (llama3-70b-8192)
                                              │
                                              ▼
                                  Answer + Citations [1][2]
```

## 🚀 Setup Lokal

### 1. Clone & install

```bash
git clone https://github.com/username/arxiv-rag.git
cd arxiv-rag

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Setup environment

```bash
cp .env.example .env
# (Opsional) isi GROQ_API_KEY di .env
# Dapatkan API key gratis di: https://console.groq.com
# OpenAlex API key opsional (bisa isi di UI)
```

### 3. Jalankan

```bash
streamlit run streamlit_app.py
# Buka http://localhost:8501
```

## 📖 Cara Pakai

1. **Isi Groq API key**: Masukkan di sidebar (atau set di `.env`)
2. **Search OpenAlex**: Ketik topik (misal: "RAG retrieval augmented generation"), klik Search & Ingest
3. **Upload PDF**: Upload paper PDF kamu, klik Ingest PDFs
4. **Chat**: Tanya apapun, jawaban akan disertai referensi `[1]`, `[2]` yang bisa diklik ke paper aslinya
5. **Manage KB**: Lihat dan hapus dokumen di sidebar Knowledge Base

Catatan: OpenAlex menyediakan abstrak, bukan full-text. Untuk full-text, gunakan upload PDF.

## ☁️ Deploy ke Railway

### Langkah-langkah

1. Push ke GitHub:

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/username/arxiv-rag.git
git push -u origin main
```

2. Buka [railway.app](https://railway.app) → New Project → Deploy from GitHub

3. Pilih repo `arxiv-rag`

4. Tambahkan **Volume** untuk persistent ChromaDB:
   - Settings → Volumes → Mount path: `/app/data/chroma_db`

5. Set **Environment Variables**:
   - `GROQ_API_KEY` = your key
   - `OPENALEX_API_KEY` = optional
   - `OPENALEX_MAILTO` = optional
   - `CHROMA_PATH` = `/app/data/chroma_db`

6. Deploy! Railway otomatis detect `railway.json`

### Catatan

- Cek kuota & pricing Railway terbaru di halaman resmi mereka
- Perlu volume agar ChromaDB tidak hilang saat redeploy

## 🔧 Konfigurasi

Edit `.env` untuk custom behavior:

| Variable               | Default                   | Keterangan                                     |
| ---------------------- | ------------------------- | ---------------------------------------------- |
| `GROQ_MODEL`           | `llama-3.3-70b-versatile` | Pilih model Groq yang tersedia                 |
| `TOP_K_RETRIEVAL`      | `6`                       | Jumlah chunks yang diambil dari ChromaDB       |
| `SIMILARITY_THRESHOLD` | `0.3`                     | Minimum cosine similarity; chunk di bawah ini difilter |
| `MAX_TOKENS_RESPONSE`  | `1500`                    | Max tokens jawaban LLM                         |
| `TOP_K_OPENALEX`       | `5`                       | Jumlah works dari OpenAlex per search          |
| `OPENALEX_API_KEY`     | `(empty)`                 | API key OpenAlex (opsional)                    |
| `OPENALEX_MAILTO`      | `(empty)`                 | Email untuk identifikasi polite usage          |
| `CHUNK_SIZE`           | `800`                     | Panjang tiap chunk (karakter)                  |
| `CHUNK_OVERLAP`        | `150`                     | Overlap antar chunk                            |
| `FULLTEXT_MAILTO`      | `(empty)`                 | Email untuk Unpaywall polite pool (opsional)   |
| `FULLTEXT_MAX_PDF_MB`  | `30`                      | Ukuran maks PDF yang akan didownload           |

## 📁 Struktur Proyek

```
arxiv-rag/
├── streamlit_app.py      # Frontend & orchestration
├── app/
│   ├── config.py         # Settings (pydantic)
│   ├── database.py       # ChromaDB + embedding singleton
│   ├── chunker.py        # PDF extraction & text chunking
│   ├── openalex_service.py  # OpenAlex search + ingestion
│   ├── pdf_service.py    # PDF upload management
│   ├── fulltext_service.py  # Full-text via Semantic Scholar & Unpaywall
│   └── rag.py            # Retrieval + Groq LLM chain
├── data/
│   └── chroma_db/        # Persistent vector store (gitignored)
├── .streamlit/
│   └── config.toml       # Streamlit server config
├── Dockerfile
├── railway.json
├── requirements.txt
└── .env.example
```

## 🧪 Contoh Pertanyaan

- _"Apa itu attention mechanism dan bagaimana cara kerjanya?"_
- _"Jelaskan perbedaan BERT dan GPT"_
- _"Apa kelemahan RAG dibanding fine-tuning?"_
- _"Summarize the key contributions of the papers I uploaded"_

## 📝 Lisensi

MIT
