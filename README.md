# Docwise API

**Chat with your PDFs.** A production-style RAG (Retrieval-Augmented Generation) API — upload a PDF, ask questions about it, and get streamed, context-grounded answers in real time.

Built with **FastAPI**, **pgvector**, **LlamaIndex**, and **Gemini** (chat + embeddings).

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.138-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white)
![Gemini](https://img.shields.io/badge/LLM-Gemini-8E75B2?logo=googlegemini&logoColor=white)

---

## Features

- **PDF ingestion pipeline** — parses PDFs with LlamaIndex, splits them into overlapping sentence-aware chunks, and embeds each chunk with the **Gemini embeddings API** (`gemini-embedding-001`, 768 dims), batched and with automatic retry on rate limits.
- **Vector similarity search** — embeddings are stored in PostgreSQL with the `pgvector` extension and retrieved via cosine distance (`<=>`), so no external vector database is needed.
- **Query expansion** — before searching, the user's question is rewritten by Gemini (acronyms expanded, synonyms added, English translation appended for non-English questions) so vector search matches the document's vocabulary. The LLM still answers the original question.
- **Asymmetric embeddings** — documents are embedded with `task_type=RETRIEVAL_DOCUMENT` and queries with `task_type=RETRIEVAL_QUERY`, the pairing Gemini optimizes for search.
- **Streaming chat (SSE)** — answers stream token-by-token as Server-Sent Events, so the client renders the response as it's generated instead of waiting for the full completion.
- **Grounded answers** — the LLM is instructed to answer _only_ from the retrieved document context, and to say so when the answer isn't in the document.
- **Session lifecycle management** — each upload creates a session with a question quota (default: 20) and a TTL (default: 24h). A background task purges expired sessions hourly (chunks removed via cascade delete), and an internal API-key-protected endpoint allows triggering cleanup on demand.
- **Fully async** — SQLAlchemy 2.0 async ORM with `asyncpg`, async request handlers, async Gemini client, and async streaming end-to-end.

## How It Works

```mermaid
flowchart TB
    subgraph Ingestion["1 — Document Ingestion"]
        direction LR
        A[PDF Upload] --> B["LlamaIndex<br/>PDF parsing"]
        B --> C["SentenceSplitter<br/>512 tokens, 50 overlap"]
        C --> D["Gemini embeddings API<br/>gemini-embedding-001 · 768 dims"]
    end

    subgraph Storage["PostgreSQL + pgvector"]
        E[("sessions<br/>chunks + embeddings")]
    end

    subgraph Chat["2 — RAG Chat"]
        direction LR
        F[Question] --> G["Query expansion<br/>acronyms · synonyms · translation"]
        G --> H["Embed expanded query<br/>same Gemini model"]
        H --> I["Cosine similarity search<br/>top-k = 5 chunks"]
        I --> J["Gemini<br/>grounded prompt"]
        J --> K["SSE token stream<br/>to the client"]
    end

    D -->|store vectors| E
    E -->|retrieve chunks| I
```

**How a question is answered:**

1. The question is rewritten by Gemini for better recall (e.g. `"LLM"` → `"Large Language Model (LLM)"`); if expansion fails, the original question is used — it never breaks the chat.
2. The expanded query is embedded with the same Gemini model used at ingestion time.
3. pgvector runs a cosine-distance search scoped to the session's chunks and returns the top 5 matches.
4. The chunks are injected into a grounding prompt and sent to Gemini with streaming enabled — using the **original** question, not the expanded one.
5. Tokens are relayed to the client as SSE events; the session's question counter is updated when the stream completes.

## Tech Stack

| Layer            | Technology                                               | Why                                                                     |
| ---------------- | -------------------------------------------------------- | ----------------------------------------------------------------------- |
| API              | FastAPI + Uvicorn                                        | Async-first, automatic OpenAPI docs, streaming support                  |
| Document parsing | LlamaIndex (`SimpleDirectoryReader`, `SentenceSplitter`) | Battle-tested PDF extraction and sentence-aware chunking                |
| Embeddings       | Gemini embeddings API (`gemini-embedding-001`, 768 dims) | Multilingual, no heavy model in memory, same API key as the chat LLM    |
| Vector store     | PostgreSQL + pgvector                                    | One database for relational data _and_ vectors; no extra infrastructure |
| LLM              | Google Gemini (streaming)                                | Fast, low-cost generation with native streaming                         |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic                         | Type-annotated models, versioned schema                                 |
| Package manager  | uv                                                       | Fast, reproducible dependency management                                |

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker (for the local PostgreSQL + pgvector instance)
- A [Gemini API key](https://aistudio.google.com/apikey) — used for both chat and embeddings

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

| Method   | Endpoint                          | Description                                                                                     |
| -------- | --------------------------------- | ----------------------------------------------------------------------------------------------- |
| `POST`   | `/documents/upload`               | Upload a PDF (max 10 MB). Chunks, embeds, and stores it. Returns a `session_id`.                |
| `GET`    | `/documents/status/{session_id}`  | Session status: processing state, questions used/remaining.                                     |
| `DELETE` | `/documents/session/{session_id}` | Delete a session and all its chunks (to switch documents).                                      |
| `POST`   | `/chat/{session_id}`              | Ask a question about the document. Streams the answer as SSE.                                   |
| `GET`    | `/health`                         | Health check.                                                                                   |
| `GET`    | `/config`                         | Public limits (max questions, upload size, TTL) so the frontend stays in sync with the backend. |
| `POST`   | `/internal/cleanup`               | Purge expired sessions on demand. Requires the `X-Internal-Api-Key` header.                     |

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

# Trigger cleanup manually (also runs automatically every hour)
curl -X POST http://localhost:8000/internal/cleanup \
  -H "X-Internal-Api-Key: your-secret-key"
# → {"sessions_deleted": 3}
```

## Configuration

All settings are managed with `pydantic-settings` and can be overridden via environment variables:

| Variable                       | Default                | Description                                               |
| ------------------------------ | ---------------------- | --------------------------------------------------------- |
| `SESSION_TTL_HOURS`            | `24`                   | Hours before a session expires                            |
| `MAX_QUESTIONS`                | `20`                   | Question quota per document                               |
| `MAX_PDF_SIZE_MB`              | `10`                   | Upload size limit                                         |
| `EMBEDDING_MODEL`              | `gemini-embedding-001` | Gemini embeddings model                                   |
| `EMBEDDING_DIMS`               | `768`                  | Embedding dimensionality (must match the pgvector column) |
| `GEMINI_MODEL`                 | `gemini-3.5-flash`     | Chat / query-expansion model                              |
| `TOP_K_RESULTS`                | `5`                    | Chunks retrieved per question                             |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `512` / `50`           | Chunking parameters (tokens)                              |
| `INTERNAL_API_KEY`             | —                      | Secret for the `/internal/*` endpoints                    |

## Tests

The automated suite lives in `tests/` and runs with:

```bash
uv run pytest
```

It only needs the Postgres container running — a dedicated `docwise_test` database is created (and dropped) automatically on the same instance, so pgvector behaves exactly like production. All Gemini calls are mocked; no test touches the network or needs an API key.

Coverage: upload validation and ingestion (`test_documents.py`), session replacement, chat validation/quota/retrieval scoping/SSE streaming (`test_chat.py`), and TTL cleanup + the internal endpoint (`test_cleanup.py`).

The `scripts/` folder additionally contains manual smoke scripts that exercise the pipeline against live services (running database + Gemini API key required):

```bash
uv run python scripts/smoke_llm.py           # Gemini streaming with a stub context
uv run python scripts/smoke_ingestion.py     # chunk + embed a local PDF
uv run python scripts/smoke_chat_service.py  # full RAG flow against a real session
```

## Evaluation

Beyond tests that verify the code works, `evals/` measures **how well the RAG pipeline answers**. A golden dataset (`evals/golden/dataset.json`, 13 questions over a reference PDF, including multilingual and abstention cases) runs through the real pipeline — ingestion, query expansion, pgvector retrieval, Gemini generation, no mocks — and every answer is scored by an LLM-as-judge with [DeepEval](https://github.com/confident-ai/deepeval):

- **Faithfulness** — does the answer invent facts outside the retrieved context? (hallucination detection)
- **Answer Relevancy** — does the answer actually address the question?

```bash
uv run --group evals python evals/run_evals.py            # full dataset (~25 min on free tier)
uv run --group evals python evals/run_evals.py --limit 3  # quick smoke run
```

Requires Postgres running and a `GEMINI_API_KEY`. All calls are paced to respect the Gemini free-tier limit (5 req/min); with billing enabled, set `EVAL_REQUEST_INTERVAL=0` and a stronger judge via `EVAL_JUDGE_MODEL=gemini-3.1-pro-preview`. The report prints per-question scores, averages, and the judge's reasoning for any answer below threshold — making it possible to compare configurations (`CHUNK_SIZE`, `TOP_K_RESULTS`, query expansion) with numbers instead of vibes.

## Project Structure

```
app/
├── api/routes/        # HTTP layer: documents, chat, health, internal
├── core/              # RAG engine: ingestion, embeddings, retrieval, LLM
│   ├── ingestion.py   #   PDF → chunks → embeddings
│   ├── embeddings.py  #   Gemini embeddings API (batched, rate-limit retries)
│   ├── retrieval.py   #   pgvector cosine-distance search
│   └── llm.py         #   Gemini streaming, grounding prompt, query expansion
├── services/          # Business logic: uploads, chat orchestration, cleanup
├── db/                # Async SQLAlchemy models, engine, Alembic migrations
├── schemas/           # Pydantic request/response models
└── config.py          # pydantic-settings configuration
tests/                 # automated pytest suite (see Tests section)
evals/                 # RAG quality evaluation with DeepEval (see Evaluation section)
scripts/               # manual smoke scripts against live services
```

## Design Decisions

- **Gemini API embeddings over a local model** — one API key powers chat, embeddings, and query expansion; the server stays lightweight (no model in memory, instant startup) and the multilingual `gemini-embedding-001` handles non-English documents. Asymmetric task types (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`) keep document and query vectors optimized for search.
- **pgvector over a dedicated vector DB** — for this scale, Postgres handles both relational session data and vector search in a single store, with cascade deletes keeping vectors and sessions consistent for free.
- **SSE over WebSockets** — the chat is strictly server-to-client streaming, so SSE gives real-time UX with plain HTTP and zero connection-management complexity.
- **Quota + TTL per session** — a question limit and automatic expiry make the demo safe to expose publicly without runaway LLM costs. An in-process background task deletes expired sessions every hour, and `/internal/cleanup` allows an external scheduler to trigger the same purge.

## License

MIT

---

_Built by [edderleonardo](https://github.com/edderleonardo)_
