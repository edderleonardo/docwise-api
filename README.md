# Docwise API

**Chat with your PDFs.** A production-style RAG (Retrieval-Augmented Generation) API — upload a PDF, ask questions about it, and get streamed, context-grounded answers in real time.

Built with **FastAPI**, **pgvector**, **LlamaIndex**, **sentence-transformers**, and **Gemini**.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.138-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white)
![Gemini](https://img.shields.io/badge/LLM-Gemini-8E75B2?logo=googlegemini&logoColor=white)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)

---

## Features

- **PDF ingestion pipeline** — parses PDFs with LlamaIndex, splits them into overlapping sentence-aware chunks, and embeds each chunk locally with `sentence-transformers` (no per-token embedding costs).
- **Vector similarity search** — embeddings are stored in PostgreSQL with the `pgvector` extension and retrieved via cosine distance (`<=>`), so no external vector database is needed.
- **Streaming chat (SSE)** — answers stream token-by-token as Server-Sent Events, so the client renders the response as it's generated instead of waiting for the full completion.
- **Grounded answers** — the LLM is instructed to answer *only* from the retrieved document context, and to say so when the answer isn't in the document.
- **Session lifecycle management** — each upload creates a session with a question quota (default: 20) and a TTL (default: 24h); an internal cleanup endpoint purges expired sessions and their chunks via cascade delete.
- **Fast first request** — the embedding model is preloaded during app startup (FastAPI lifespan), so users never pay the model cold-start cost.
- **Fully async** — SQLAlchemy 2.0 async ORM with `asyncpg`, async request handlers, and async streaming end-to-end.

## How It Works

```mermaid
flowchart TB
    subgraph Ingestion["1 — Document Ingestion"]
        direction LR
        A[PDF Upload] --> B["LlamaIndex<br/>PDF parsing"]
        B --> C["SentenceSplitter<br/>512 tokens, 50 overlap"]
        C --> D["sentence-transformers<br/>MiniLM · 384 dims"]
    end

    subgraph Storage["PostgreSQL + pgvector"]
        E[("sessions<br/>chunks + embeddings")]
    end

    subgraph Chat["2 — RAG Chat"]
        direction LR
        F[Question] --> G["Embed question<br/>same local model"]
        G --> H["Cosine similarity search<br/>top-k = 5 chunks"]
        H --> I["Gemini<br/>grounded prompt"]
        I --> J["SSE token stream<br/>to the client"]
    end

    D -->|store vectors| E
    E -->|retrieve chunks| H
```

**How a question is answered:**

1. The question is embedded with the same local model used at ingestion time.
2. pgvector runs a cosine-distance search scoped to the session's chunks and returns the top 5 matches.
3. The chunks are injected into a grounding prompt and sent to Gemini with streaming enabled.
4. Tokens are relayed to the client as SSE events; the session's question counter is updated when the stream completes.

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| API | FastAPI + Uvicorn | Async-first, automatic OpenAPI docs, streaming support |
| Document parsing | LlamaIndex (`SimpleDirectoryReader`, `SentenceSplitter`) | Battle-tested PDF extraction and sentence-aware chunking |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`, 384 dims) | Local inference — fast, free, and consistent between ingestion and query |
| Vector store | PostgreSQL + pgvector | One database for relational data *and* vectors; no extra infrastructure |
| LLM | Google Gemini (streaming) | Fast, low-cost generation with native streaming |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic | Type-annotated models, versioned schema |
| Package manager | uv | Fast, reproducible dependency management |
| Testing | pytest + pytest-asyncio + httpx | Async unit and API tests |

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker (for the local PostgreSQL + pgvector instance)
- A [Gemini API key](https://aistudio.google.com/apikey)

### 1. Clone and install

```bash
git clone https://github.com/edderleonardo/docwise-api.git
cd docwise-api
uv sync
```

### 2. Start the database

```bash
docker compose up -d
```

This starts a `pgvector/pgvector:pg16` container with a persistent volume.

### 3. Configure the environment

```bash
cp .env.example .env
```

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/docwise
GEMINI_API_KEY=your-gemini-api-key
INTERNAL_API_KEY=your-secret-key
```

### 4. Run migrations and start the server

```bash
uv run alembic upgrade head
uv run fastapi dev app/main.py
```

The API is now available at `http://localhost:8000` — interactive docs at [`/docs`](http://localhost:8000/docs).

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/documents/upload` | Upload a PDF (max 10 MB). Chunks, embeds, and stores it. Returns a `session_id`. |
| `GET` | `/documents/status/{session_id}` | Session status: processing state, questions used/remaining. |
| `DELETE` | `/documents/session/{session_id}` | Delete a session and all its chunks (to switch documents). |
| `POST` | `/chat/{session_id}` | Ask a question about the document. Streams the answer as SSE. |
| `GET` | `/health` | Health check. |

### Example

```bash
# Upload a PDF
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@paper.pdf"
# → {"session_id": "3f2b...", "status": "ready", "chunk_count": 42, ...}

# Ask a question (streams as SSE)
curl -N -X POST http://localhost:8000/chat/3f2b... \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main conclusion of this paper?"}'
# → data: The paper concludes...
# → data: [DONE]
```

## Configuration

All settings are managed with `pydantic-settings` and can be overridden via environment variables:

| Variable | Default | Description |
|---|---|---|
| `SESSION_TTL_HOURS` | `24` | Hours before a session expires |
| `MAX_QUESTIONS` | `20` | Question quota per document |
| `MAX_PDF_SIZE_MB` | `10` | Upload size limit |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model |
| `TOP_K_RESULTS` | `5` | Chunks retrieved per question |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `512` / `50` | Chunking parameters (tokens) |

## Tests

```bash
uv run pytest
```

Covers the ingestion pipeline (chunking + embedding), the RAG chat service (session validation, quota enforcement, streaming), and the LLM prompt building.

## Project Structure

```
app/
├── api/routes/        # HTTP layer: documents, chat, health
├── core/              # RAG engine: ingestion, embeddings, retrieval, LLM
│   ├── ingestion.py   #   PDF → chunks → embeddings
│   ├── embeddings.py  #   sentence-transformers wrapper (preloaded at startup)
│   ├── retrieval.py   #   pgvector cosine-distance search
│   └── llm.py         #   Gemini streaming + grounding prompt
├── services/          # Business logic: uploads, chat orchestration, cleanup
├── db/                # Async SQLAlchemy models, engine, Alembic migrations
├── schemas/           # Pydantic request/response models
└── config.py          # pydantic-settings configuration
tests/                 # pytest + pytest-asyncio suite
```

## Design Decisions

- **Local embeddings instead of an API** — embedding happens on the server with MiniLM. This keeps ingestion free and fast, and guarantees the query and document vectors live in the same embedding space.
- **pgvector over a dedicated vector DB** — for this scale, Postgres handles both relational session data and vector search in a single store, with cascade deletes keeping vectors and sessions consistent for free.
- **SSE over WebSockets** — the chat is strictly server-to-client streaming, so SSE gives real-time UX with plain HTTP and zero connection-management complexity.
- **Quota + TTL per session** — a question limit and automatic expiry make the demo safe to expose publicly without runaway LLM costs.

## License

MIT

---

*Built by [Edder Leonardo Ramírez](https://github.com/edderleonardo)*
