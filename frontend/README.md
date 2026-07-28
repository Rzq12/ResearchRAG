# ResearchRAG — React Frontend

A modern, responsive React (Vite + TypeScript + Tailwind) frontend for
**ResearchRAG**. It replicates and improves the Streamlit UX and talks to the
existing backend through the thin FastAPI wrapper in [`../api`](../api).

The original Streamlit app is untouched — this is an additional, standalone
frontend you can deploy to Vercel.

---

## ✨ What it does

Every Streamlit feature, re-implemented as reusable React components:

- **Auth** — login / sign-up gate (per-user knowledge base)
- **Model picker** — all Groq / Gemini / self-hosted models from the API, with a
  single dynamic API-key field per provider (stored in `localStorage`)
- **OpenAlex search & ingest** — abstracts / full-text / both, topic badges,
  abstract download (.txt / .json)
- **PDF upload & ingest** — multi-file, coverage feedback
- **Streaming chat** — token-by-token answers (SSE), `<think>` reasoning,
  inline citations with relevance scores, live-fallback source badges, query
  suggestions
- **KB-only toggle** — "Answer only from my knowledge base" (ON by default):
  forces answers from your ingested papers and never falls back to live
  OpenAlex/web. Sends `kb_only` to the API (additive backend flag).
- **Semantic search** — raw chunk search with similarity scores, no LLM
- **Knowledge base** — stats, per-document summarize/delete, clear all
- **Retrieval filters** — document / section / year metadata filtering
- **Export** — chat as Markdown

### Design system

Built to the `.agents` design-taste rules: **Geist** type (no Inter), a single
desaturated **emerald** accent (no AI-purple), **Phosphor** icons (no emoji, no
lucide), an off-black **zinc-950** base, hairline borders, and tactile
`cubic-bezier` motion. Reference source badges are colour-coded by true origin —
Uploaded / OpenAlex / OpenAlex · live / Web — so live-fallback answers never
masquerade as your knowledge base.

---

## 🧱 Project structure

```
frontend/
├── index.html
├── vite.config.ts · tsconfig*.json · tailwind.config.js · postcss.config.js
├── vercel.json                 # Vercel build + SPA rewrite
├── .env.example                # VITE_API_BASE_URL
└── src/
    ├── main.tsx · App.tsx · index.css
    ├── lib/                    # api client, types, SSE chat stream, utils
    ├── context/                # Auth, Settings, Workspace, Toast
    ├── hooks/                  # useLocalStorage, React Query data hooks
    ├── components/
    │   ├── ui/                 # Button, Input, Select, Card, Badge, Spinner, Collapsible, Markdown, Toggle
    │   ├── layout/             # AppShell (responsive), Sidebar
    │   ├── auth/               # AuthPage
    │   ├── sidebar/            # ModelSelector, OpenAlexSearch, PdfUpload…
    │   ├── chat/               # ChatPanel, MessageBubble, References…
    │   └── search/             # SemanticSearchPanel
    └── pages/                  # DashboardPage
```

---

## 🚀 Run locally

**Prerequisites:** Node 18+ and the backend API running (see [`../api/README.md`](../api/README.md)).

```bash
cd frontend
cp .env.example .env          # then edit if your API isn't on :8000
npm install
npm run dev                   # http://localhost:5173
```

`.env`:

```
VITE_API_BASE_URL=http://localhost:8000
```

> Start the backend first:
> ```bash
> # from the repo root
> pip install -r requirements.txt -r api/requirements.txt
> uvicorn api.main:app --reload --port 8000
> ```

Build & preview a production bundle:

```bash
npm run build     # tsc typecheck + vite build → dist/
npm run preview
```

---

## ▲ Deploy to Vercel

1. Push this repo to GitHub (the frontend lives in `frontend/`).
2. In Vercel: **New Project → Import** the repo.
3. Set **Root Directory** to `frontend/`. Vercel auto-detects Vite
   (build `npm run build`, output `dist`) — `vercel.json` also pins this.
4. Add an **Environment Variable**:

   | Name                 | Value                                   |
   | -------------------- | --------------------------------------- |
   | `VITE_API_BASE_URL`  | `https://<your-backend-url>`            |

   Point it at wherever the FastAPI wrapper is reachable — e.g. your Hugging
   Face Space URL (`https://<user>-researchrag.hf.space`) or Railway URL.
5. **Deploy.**

> **CORS:** the API must allow your Vercel origin. Set `CORS_ORIGINS` in the
> backend environment to your Vercel URL (e.g.
> `CORS_ORIGINS=https://researchrag.vercel.app`). See `../.env.example`.

---

## 🔌 How it talks to the backend

`VITE_API_BASE_URL` is the only configuration. All calls live in
[`src/lib/api.ts`](src/lib/api.ts); the streaming chat uses `fetch` + a manual
SSE reader in [`src/lib/chatStream.ts`](src/lib/chatStream.ts) (because the chat
endpoint is a POST). API keys are entered in the UI and sent per-request — they
are never stored on the server, mirroring the Streamlit app.
