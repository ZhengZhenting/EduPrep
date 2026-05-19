# EduPrep

An AI-powered learning platform for international students in Germany. Reduces language barriers through a structured **Preview → Learn → Review** cycle. All AI components run locally via Ollama — no cloud inference costs, no data sent externally.

---

## Features

### Preview
Upload a German lecture PDF and automatically receive a bilingual summary (German + Chinese) and a key vocabulary list with translations and examples.

### Learn
Ask questions about the lecture in natural language. Answers are grounded in the uploaded PDF via RAG-based semantic retrieval. When PDF content is insufficient, the system falls back to live web search via Tavily. A LangChain ReAct Agent enriches responses with diagrams (Mermaid), math formulas (LaTeX/KaTeX), or syntax-highlighted code when relevant.

### Review
Generate multiple-choice quiz questions from the lecture content. Questions are presented one at a time with immediate correctness feedback, Chinese explanations, and a mastery progress bar. Quiz results are persisted to localStorage.

---

## Architecture

```
React Frontend
      |
FastAPI Backend
      |
  ┌───┴────────────┐
  |                |
RAG Pipeline    LangChain ReAct Agent
  |                |
ChromaDB        Tools: Mermaid / KaTeX / highlight.js
  |
Ollama (LLM: qwen2.5:7b, Embeddings: embeddinggemma)
      |
Tavily Search API  (web fallback when RAG score >= 1.1)
```

**Request flow for /ask:**

1. Semantic search over ChromaDB — always executes, retrieves top-k chunks with page metadata
2. Score routing — cosine distance < 1.1 uses PDF content; >= 1.1 triggers Tavily web search
3. LangChain ReAct Agent — decides whether to invoke a tool (max 1 per response, enforced via prompt + `max_iterations=3`)
4. Two-part response — PDF citation block (raw source with page reference) + agent supplement

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite |
| Backend | FastAPI, Python 3.11 |
| LLM | Ollama — qwen2.5:7b |
| Embeddings | Ollama — embeddinggemma |
| RAG | LangChain, ChromaDB |
| Agent | LangChain ReAct Agent |
| Web Search | Tavily API |
| Database | PostgreSQL + SQLAlchemy (planned) |
| Task Queue | Celery + Redis (planned) |
| Auth | JWT + bcrypt (planned) |

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com)

### 1. Pull required models

```bash
ollama pull qwen2.5:7b
ollama pull embeddinggemma
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install fastapi uvicorn python-multipart pypdf \
    langchain langchain-community langchain-chroma \
    langchain-ollama langchain-text-splitters \
    chromadb tavily-python python-dotenv httpx
```

Create `backend/.env`:

```
TAVILY_API_KEY=tvly-your-key-here
```

Start the server:

```bash
uvicorn main:app --reload
# Interactive API docs: http://localhost:8000/docs
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
# Application: http://localhost:5173
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/upload` | Upload PDF, parse into chunks, embed and store in ChromaDB |
| POST | `/preview` | Generate bilingual summary and vocabulary list |
| POST | `/ask` | RAG Q&A with Agent tool support and web search fallback |
| POST | `/quiz` | Generate multiple-choice questions from PDF content |

**POST /ask — request**
```json
{
  "question": "Was ist Prompt Engineering?",
  "filename": "VL-06-Prompting.pdf",
  "history": [
    { "role": "user", "content": "...", "sources": [] },
    { "role": "assistant", "content": "...", "sources": [3, 5] }
  ]
}
```

**POST /ask — response**
```json
{
  "question": "Was ist Prompt Engineering?",
  "answer": "...",
  "source_type": "pdf",
  "sources": [3, 5, 7]
}
```

---

## Project Structure

```
eduprep/
├── backend/
│   ├── main.py             # FastAPI app, all API endpoints
│   ├── pdf_processor.py    # PDF parsing, chunking (800 chars, 300 overlap)
│   ├── rag.py              # ChromaDB storage, semantic search, score routing
│   ├── tools.py            # LangChain Tool definitions
│   ├── agent.py            # LangChain ReAct Agent
│   ├── chroma_db/          # Persistent vector store (auto-generated, gitignored)
│   └── .env                # Environment variables (gitignored)
├── frontend/
│   └── src/
│       └── App.jsx         # React single-page application
├── CLAUDE.md               # Project context for Claude Code
└── README.md
```

---

## Design Decisions

**Local-first** — LLM inference and embedding both run via Ollama. The only external call is the optional Tavily web search fallback.

**Score-based routing over LLM classification** — Uses cosine distance threshold (1.1) rather than LLM YES/NO intent classification. Small local models (3–7B) produce unreliable binary judgments; a numeric threshold is deterministic and tunable.

**Agent tool constraints** — Tool docstrings are the primary guardrail against overuse by small models, combined with `max_iterations=3`. This keeps tool invocation purposeful without requiring a larger model.

**German filename handling** — ChromaDB collection names are restricted to `[a-zA-Z0-9._-]`. `sanitize_collection_name()` in `rag.py` normalises German umlauts and special characters before any collection is created or queried.

**Chunk overlap** — `chunk_size=800, chunk_overlap=300`. The larger overlap (previously 150) was necessary to prevent content truncation at chunk boundaries, which caused RAG to miss relevant passages.

---

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| P1 | LangChain ReAct Agent, 3 tools, two-part response format | Backend complete — frontend pending |
| P2 | PostgreSQL, course management, Celery + Redis async PDF processing, conversation persistence, React Router multi-page layout | Planned |
| P3 | Observability — Loguru structured logs, Prometheus metrics, Jaeger distributed tracing, Grafana dashboard | Planned |
| P4 | Notes system (3 types), JWT authentication, session list and export | Planned |
| P5 | Redis AI response cache, token-bucket rate limiting, Ollama circuit breaker, prompt injection detection, security hardening | Planned |
| P6 | pytest unit + integration tests (>80% coverage), AI golden dataset regression (cosine similarity), Locust load tests | Planned |
| P7 | Docker + docker-compose (8 services), GitHub Actions CI/CD, Tailwind CSS, full documentation | Planned |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TAVILY_API_KEY` | Yes | Tavily Search API key — obtain at [tavily.com](https://tavily.com) |

---

## License

MIT
