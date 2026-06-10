# EduPrep

An AI-powered learning platform for international students in Germany. Reduces language barriers through a structured **Preview → Learn → Review** cycle.

---
## Demo
[![Demo Video](https://img.youtube.com/vi/EDPW8Nq5G64/0.jpg)](https://youtu.be/EDPW8Nq5G64)

---

## Features

### Preview
Upload a German lecture PDF and automatically receive a bilingual summary (German + Chinese), a key vocabulary list with translations, and a Mermaid structure diagram of the lecture.

### Learn
Ask questions about the lecture in natural language. Answers are grounded in the PDF via hybrid RAG retrieval. When the PDF content score falls below the relevance threshold, the system automatically supplements with live web search via Tavily and labels the answer source (`pdf` / `pdf+web`). Conversation history is compressed and persisted per PDF.

### Quiz
Generate personalised multiple-choice questions from the lecture content. The system reads tracked weak concepts from memory and prioritises them in question generation. Quiz results and scores are persisted to PostgreSQL.

---

## Architecture

```
React SPA (Auth → Courses → PDF → Learn/Preview/Quiz)
        |
FastAPI Backend (JWT-protected endpoints)
        |
  ┌─────┴──────────────────────┐
  |                            |
Hybrid RAG Pipeline        Memory System
  |                            |
  ├─ Vector Search (ChromaDB)  ├─ Conversation Memory (PostgreSQL)
  ├─ BM25 Keyword Search       └─ Quiz Progress (PostgreSQL)
  └─ RRF Fusion
        |
  Score Routing (threshold 0.9)
  ├─ score < 0.9 → Claude API (PDF answer)
  └─ score ≥ 0.9 → Tavily Search → Claude API (PDF + web supplement)
        |
  LangFuse v4 (full LLM call tracing)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, inline styles |
| Backend | FastAPI, Python 3.11 |
| LLM | Claude API — claude-sonnet-4-5 |
| Embeddings | Ollama — nomic-embed-text (local) |
| RAG | LangChain + ChromaDB + BM25 (rank-bm25) |
| Retrieval Fusion | Reciprocal Rank Fusion (RRF) |
| Web Search | Tavily API |
| Memory | PostgreSQL — memory + quiz_progress tables |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Auth | JWT (python-jose) + bcrypt |
| Observability | LangFuse v4 + Loguru |

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL
- [Ollama](https://ollama.com)

### 1. Pull embedding model

```bash
ollama pull nomic-embed-text
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

Create `backend/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
POSTGRESQL_PASSWORD=your-password
JWT_SECRET_KEY=your-64-char-random-hex
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

Initialise the database (run once):

```bash
python init_db.py
```

Start the server:

```bash
uvicorn main:app --reload
# API docs: http://localhost:8000/docs
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
# App: http://localhost:5173
```

---

## API Reference

All endpoints except `/auth/*` require `Authorization: Bearer <token>`.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Login, returns access + refresh tokens |
| POST | `/auth/refresh` | Exchange refresh token for new access token |
| POST | `/courses` | Create course |
| GET | `/courses` | List user's courses |
| GET | `/courses/{id}` | Course detail + PDF list |
| PATCH | `/courses/{id}` | Rename course |
| DELETE | `/courses/{id}` | Delete course (cascade) |
| POST | `/upload` | Upload PDF → chunk → embed → ChromaDB |
| DELETE | `/pdfs/{id}` | Delete PDF + ChromaDB collection |
| POST | `/preview` | Bilingual summary + vocabulary + Mermaid diagram |
| POST | `/ask` | Hybrid RAG Q&A with optional web supplement |
| GET | `/message/{filename}` | Load conversation history |
| POST | `/quiz` | Generate personalised quiz questions |
| POST | `/quiz/result` | Save quiz score |
| POST | `/notes` | Save note |
| GET | `/notes/{filename}` | Load notes |
| DELETE | `/notes/{id}` | Delete note |

---

## Project Structure

```
eduprep/
├── backend/
│   ├── main.py             # FastAPI app — all endpoints
│   ├── auth.py             # JWT auth — hash, verify, token creation
│   ├── rag.py              # ChromaDB + BM25 hybrid search + RRF
│   ├── pdf_processor.py    # PyPDFLoader, chunking (800 chars, 300 overlap)
│   ├── memory.py           # Conversation memory + quiz progress (PostgreSQL)
│   ├── tools.py            # Plain functions: search_web, generate_mermaid_chart
│   ├── models.py           # SQLAlchemy ORM — 7 tables
│   ├── database.py         # PostgreSQL connection
│   ├── observability.py    # LangFuse + Loguru initialisation
│   ├── init_db.py          # One-time DB + default user setup
│   ├── alembic/            # Migration scripts
│   └── .env                # Environment variables (gitignored)
├── frontend/
│   └── src/
│       ├── App.jsx          # React SPA — auth, sidebar, 3-view navigation
│       └── AnswerRenderer.jsx  # Renders Mermaid / LaTeX / code / text
├── docs/
│   └── architecture/
│       └── er_diagram.svg
├── CLAUDE.md
└── README.md
```

---

## Key Design Decisions

**Hybrid retrieval over vector-only** — BM25 handles exact keyword matches (e.g. German technical terms) that semantic search misses. RRF fusion (`score = Σ 1/(60+rank)`) combines both rankings without requiring score normalisation.

**Score-based routing** — Cosine distance threshold (0.9) decides whether to call Tavily. Deterministic and tunable; avoids an extra LLM classification call.

**Two-step Preview prompting** — Summary JSON and Mermaid diagram are generated in separate Claude calls. Mixing structured JSON output with Mermaid syntax in a single prompt causes format collisions.

**Memory compression** — Conversation history is compressed by Claude every 6 turns into a ≤200-character summary, keeping context window usage bounded across long sessions.

**Local embeddings** — Ollama/nomic-embed-text runs locally. Only LLM inference and web search make external API calls.

---

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| P1 | Tool layer, hybrid RAG, dual-source Q&A | Complete |
| P2 | PostgreSQL, course + PDF management, conversation persistence | Complete |
| P3 | LangFuse observability, Loguru structured logging | Complete |
| P4 | JWT auth, frontend redesign, memory system, personalised quiz | Complete |
| P5 | Redis cache, rate limiting, circuit breaker, security hardening | Planned |
| P6 | pytest unit + integration tests, AI golden dataset, Locust load tests | Planned |
| P7 | Docker + docker-compose, GitHub Actions CI/CD, Celery async, Tailwind | Planned |

---

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `TAVILY_API_KEY` | Tavily Search API key |
| `POSTGRESQL_PASSWORD` | PostgreSQL password |
| `JWT_SECRET_KEY` | 64-char random hex for JWT signing |
| `LANGFUSE_PUBLIC_KEY` | LangFuse project public key |
| `LANGFUSE_SECRET_KEY` | LangFuse project secret key |
| `LANGFUSE_HOST` | LangFuse host URL |

---

## License

MIT
