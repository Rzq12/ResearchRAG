# ResearchRAG API (FastAPI wrapper)

A **thin HTTP layer** over the existing ResearchRAG backend. It imports the same
`app/` modules the Streamlit app uses (`app.rag`, `app.openalex_service`,
`app.pdf_service`, `app.semantic_search`, `app.auth`, …) and exposes them as
REST + SSE endpoints so the [React frontend](../frontend) can use every feature.

**No RAG / retrieval / inference logic is reimplemented or migrated here** — this
is a wrapper. The Streamlit app is unaffected.

---

## Run locally

```bash
# from the repo root
pip install -r requirements.txt -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
```

- Interactive docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/health>

Configuration is read from the same `.env` as the Streamlit app, plus one API
value: `CORS_ORIGINS` (comma-separated allowed origins; default `*`).

---

## Endpoints

| Method | Path                          | Purpose                                        |
| ------ | ----------------------------- | ---------------------------------------------- |
| GET    | `/api/health`                 | Liveness probe                                 |
| GET    | `/api/config`                 | Model catalog + settings for the UI            |
| POST   | `/api/auth/register`          | Create account                                 |
| POST   | `/api/auth/login`             | Verify credentials → `user_id`                 |
| POST   | `/api/openalex/search`        | Search OpenAlex (metadata only)                |
| POST   | `/api/openalex/ingest`        | Ingest works (abstracts / full-text / both)    |
| POST   | `/api/openalex/citations`     | Reference network for one work                 |
| POST   | `/api/openalex/topics`        | Classify works into research topics            |
| POST   | `/api/openalex/suggestions`   | Generate follow-up questions                   |
| GET    | `/api/documents`              | List KB documents                              |
| GET    | `/api/documents/stats`        | Chunk + document counts                        |
| POST   | `/api/documents/upload`       | Ingest an uploaded PDF (multipart)             |
| POST   | `/api/documents/summarize`    | 5-section paper summary                         |
| DELETE | `/api/documents`              | Delete a document's chunks                     |
| POST   | `/api/documents/clear`        | Clear the whole KB for a user                  |
| POST   | `/api/chat/stream`            | **SSE** streaming RAG answer + refs + reasoning |
| POST   | `/api/semantic-search`        | Raw vector search (no LLM)                      |

### Auth model

Username-scoped isolation (the normalized username is the `user_id` that scopes
every ChromaDB collection) — identical to the Streamlit app. The client stores
`user_id` after login and sends it with each request; no tokens are minted.

### API keys

LLM / OpenAlex keys are passed **per request** in the body (the user enters them
in the UI). They are never stored server-side, matching the Streamlit design.

### Streaming (`/api/chat/stream`)

`text/event-stream` with these events:

```
event: token   data: {"text": "..."}                         # 0..n, in order
event: meta    data: {references, openalex_used,
                      uploaded_used, reasoning, source}        # once, after tokens
event: error   data: {"category": "...", "message": "..."}    # on failure
event: done    data: {}                                       # always last
```

---

## Deployment

The API ships **inside this same repo** and is served from the **same container**
as Streamlit via nginx — see the repo root `Dockerfile` and
[`../deploy/`](../deploy). On the Hugging Face Space (or Railway), nginx routes
`/api/*` to this FastAPI app and everything else to Streamlit, so one service
exposes both. The React frontend (on Vercel) points `VITE_API_BASE_URL` at that
Space/Railway URL.
