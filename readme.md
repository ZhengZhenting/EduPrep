<div align="center">

# EduPrep

**English** · [中文](./README.zh.md)

**An AI learning system for international students in Germany.**
Not just a tool that chats with PDFs — it builds a **knowledge graph** for every course, **tracks your mastery** of each concept, and schedules your **Preview → Learn → Review** along the forgetting curve.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Claude](https://img.shields.io/badge/LLM-Claude-D97757)
![Status](https://img.shields.io/badge/status-active%20development-brightgreen)

[Demo](#demo) · [What Makes It Different](#what-makes-eduprep-different) · [Architecture](#architecture) · [Tech Stack](#tech-stack) · [Roadmap](#roadmap--where-its-heading) · [Docs](./docs)

</div>

---

## Demo

[![Demo Video](https://img.youtube.com/vi/EDPW8Nq5G64/0.jpg)](https://youtu.be/EDPW8Nq5G64)

---

## What Makes EduPrep Different

Most "AI study tools" stop at *retrieval-augmented chat over a single document*. EduPrep is built around three ideas that turn isolated PDFs into a **living model of what a student knows**:

| Principle | What it means |
|---|---|
| 🕸️ **Knowledge-graph-driven** | Concepts are extracted from every PDF and stitched into a **course-level knowledge graph** — with prerequisite, related, and German-term-equivalence edges. A concept that appears in week 3 and week 9 is *one node*, not two. |
| 🎯 **Adaptive & personalised** | A per-concept **learner model** tracks your mastery from quiz results. Quizzes prioritise your weak spots; difficulty adapts to you. |
| 🔁 **A truly closed learning loop** | Preview → Learn → Review isn't three isolated tabs. Every session updates the knowledge graph + mastery model, so the *next* preview, quiz, and review change accordingly. |

> **The unit of learning is a course, not a PDF.** Over a semester, EduPrep grows each course into a complete, mastery-annotated map of everything you've studied.

---

## Features

> The features below are shipping today. Each is being upgraded along the [roadmap](#roadmap--where-its-heading) — e.g. the Preview mind-map is evolving into the full knowledge graph, and Learn is becoming an Agent.

### 📖 Preview
Upload a German lecture PDF and automatically receive a **bilingual summary (German + Chinese)**, a key vocabulary list with translations, and a Mermaid structure diagram of the lecture.

### 💬 Learn
Ask questions in natural language. Answers are grounded in the PDF via **hybrid RAG retrieval** (BM25 + vector + RRF fusion). The **LLM itself decides** (via Anthropic tool use) whether the lecture is enough or a **live web search (Tavily)** is needed — when it searches, the PDF answer (with page numbers) and the web supplement (with source URLs) are shown as **two separate, clearly-sourced parts** (`pdf` / `pdf+web`). Conversation history is compressed and persisted per PDF.

### 📝 Quiz
Generate **personalised** multiple-choice questions from the lecture. The system reads tracked weak concepts from memory and prioritises them. Scores are persisted to PostgreSQL.

---

## Architecture

```
React SPA (Auth → Courses → PDF → Preview / Learn / Quiz)
        |
FastAPI Backend (JWT-protected endpoints)
        |
  ┌─────┴──────────────────────┐
  |                            |
Hybrid RAG Pipeline        Memory System
  ├─ Vector Search (ChromaDB)  ├─ Conversation Memory (PostgreSQL)
  ├─ BM25 Keyword Search       └─ Quiz Progress (PostgreSQL)
  └─ RRF Fusion
        |
  Claude API (PDF answer, always)
        |
  LLM tool-use decision (Anthropic tool_choice=auto)
  ├─ lecture sufficient → PDF answer only
  └─ insufficient → Tavily Search → Claude API (separate web supplement)
        |
  LangFuse v4 (full LLM call tracing)
```

📐 Detailed design docs live in [`docs/architecture/`](./docs/architecture) — including the upcoming [knowledge-graph schema](./docs/architecture/knowledge-graph-schema.md).

---

## Tech Stack

| Layer | Now (shipping) | Planned (roadmap) |
|---|---|---|
| Frontend | React 18, Vite, TanStack Router + Query, Tailwind + shadcn/ui | Knowledge-graph viz (react-flow / cytoscape.js) |
| Backend | FastAPI, Python 3.11 | Celery + Redis async workers |
| LLM | Claude API — `claude-sonnet-4-5` | Model tiering — `claude-opus-4-8` (Agent) / `claude-sonnet-4-6` (tools) |
| Embeddings | Ollama — `nomic-embed-text` (local) | — |
| RAG | LangChain + ChromaDB + BM25 + RRF; semantic chunking (SemanticChunker) | **GraphRAG** (graph-expanded retrieval) |
| Agent | Plain tool functions | **LangGraph** orchestration + **MCP server** |
| Learning science | weak-concept tracking | **Knowledge tracing (BKT)** + **spaced repetition (FSRS)** + adaptive quizzing |
| Web search | Tavily API | — |
| Database | PostgreSQL + SQLAlchemy + Alembic | Course-level concept graph tables |
| Auth | JWT (python-jose) + bcrypt | — |
| Observability | LangFuse v4 + Loguru | Prometheus + Grafana + Jaeger |
| Eval | — | Golden dataset + retrieval/answer metrics |

---

## Getting Started

### Prerequisites
- Python 3.10+ · Node.js 18+ · PostgreSQL · [Ollama](https://ollama.com)

### 1. Pull embedding model
```bash
ollama pull nomic-embed-text
```

### 2. Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate         # Windows  ·  source venv/bin/activate on macOS/Linux
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

Initialise the DB (run once) and start the server:
```bash
python init_db.py
uvicorn main:app --reload      # API docs: http://localhost:8000/docs
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev                    # App: http://localhost:5173
```

---

## API Reference

All endpoints except `/auth/*` require `Authorization: Bearer <token>`.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` · `/auth/login` · `/auth/refresh` | Account + JWT token lifecycle |
| POST/GET/PATCH/DELETE | `/courses` · `/courses/{id}` | Course CRUD (per-user, ownership-checked) |
| POST/DELETE | `/upload` · `/pdfs/{id}` | PDF → chunk → embed → ChromaDB; delete + cleanup |
| POST | `/preview` | Bilingual summary + vocabulary + Mermaid diagram |
| POST | `/ask` | Hybrid RAG Q&A with optional web supplement |
| GET | `/message/{filename}` | Load conversation history |
| POST | `/quiz` · `/quiz/result` | Generate personalised quiz · save score |
| POST/GET/DELETE | `/notes` · `/notes/{filename}` · `/notes/{id}` | Notes CRUD |
| GET | `/me/stats` | Gamification stats (days active, level, xp) derived from existing data |

---

## Project Structure

```
eduprep/
├── backend/
│   ├── main.py             # FastAPI app — all endpoints
│   ├── auth.py             # JWT auth — hash, verify, token creation
│   ├── rag.py              # ChromaDB + BM25 hybrid search + RRF
│   ├── pdf_processor.py    # PyPDFLoader + SemanticChunker (percentile 90) + 1100-char guard split
│   ├── memory.py           # Conversation memory + quiz progress (PostgreSQL)
│   ├── tools.py            # Plain functions: search_web, generate_mermaid_chart
│   ├── models.py           # SQLAlchemy ORM — 7 tables (+ knowledge-graph tables planned)
│   ├── database.py         # PostgreSQL connection
│   ├── observability.py    # LangFuse + Loguru initialisation
│   ├── eval/               # AI evaluation harness (planned P6)
│   └── alembic/            # Migration scripts
├── frontend/src/
│   ├── routes/             # login, register, dashboard, courses, workspace
│   ├── lib/                # api.ts (axios + JWT), auth.tsx, use-auth.ts
│   └── components/         # ui/ (shadcn) + workspace/ (Preview/Learn/Quiz/Notes/Mermaid)
├── docs/
│   ├── architecture/       # knowledge-graph-schema.md, ER diagram, design docs
│   ├── adr/                # Architecture Decision Records
│   ├── evaluation/         # Eval baselines + benchmark reports
│   ├── research/           # User personas, journey maps, competitor analysis
│   ├── roadmap/            # eduprep_roadmap.html (bilingual interactive roadmap)
│   └── blog/               # Technical write-ups
├── CLAUDE.md
└── README.md
```

---

## Key Design Decisions

Full rationale is recorded as [ADRs](./docs/adr). Highlights:

- **Hybrid retrieval over vector-only** — BM25 catches exact German technical terms that semantic search misses; RRF fusion (`Σ 1/(60+rank)`) merges rankings without score normalisation.
- **Semantic chunking** — chunks break on embedding-similarity shifts (SemanticChunker) instead of a fixed character count, keeping each chunk topically coherent; an 1100-char guard split caps over-long chunks.
- **LLM-decided web search** — instead of a fixed cosine threshold, the model decides via Anthropic tool use whether the lecture suffices or Tavily is needed (defaults to trusting the lecture, capped at one call). PDF and web answers stay separately sourced (page numbers vs. URLs).
- **Two-step Preview prompting** — summary JSON and Mermaid diagram are generated separately to avoid format collisions.
- **Course-level knowledge layer** — concepts/mastery are modelled at the course level (not per-PDF), because the real unit of learning spans many documents. See [knowledge-graph-schema.md](./docs/architecture/knowledge-graph-schema.md).
- **Local embeddings** — Ollama runs locally; only LLM inference and web search leave the machine.

---

## Roadmap — Where It's Heading

EduPrep is under **active, iterative development**. The path from "RAG chat app" to "knowledge-graph-driven adaptive learning system" is broken into focused phases — each shipping working features **and** its own documentation.

| Phase | Scope | Status |
|---|---|---|
| P1–P3 | Tool layer · hybrid RAG · PostgreSQL · course/PDF management · LangFuse observability | ✅ Complete |
| P4–P5 | JWT auth · memory system · personalised quiz · TanStack Router + shadcn/ui redesign | ✅ Complete |
| **P6** | Evaluation baseline (golden dataset + metrics) · docs foundation | 🔜 Next |
| **P7** | **Knowledge graph** construction + visualization (course-level concept network) | 📋 Planned |
| **P8** | **GraphRAG** retrieval + learning-path generation | 📋 Planned |
| **P9** | **Learning-science engine** — knowledge tracing (BKT) + spaced repetition (FSRS) + adaptive quizzing | 📋 Planned |
| **P10** | **Agent + Tools + MCP** — LangGraph orchestration, EduPrep as an MCP server | 📋 Planned |
| P11 | Performance / reliability / security hardening (Redis cache, rate limiting, circuit breaker) | 📋 Planned |
| P12 | Testing · Docker · CI/CD · Prometheus + Grafana + Jaeger | 📋 Planned |

📍 **Full interactive bilingual roadmap:** [`docs/roadmap/eduprep_roadmap.html`](./docs/roadmap/eduprep_roadmap.html)

---

## Documentation

| Area | Location |
|---|---|
| Architecture & schema | [`docs/architecture/`](./docs/architecture) |
| Architecture Decision Records | [`docs/adr/`](./docs/adr) |
| Evaluation & benchmarks | [`docs/evaluation/`](./docs/evaluation) |
| User research | [`docs/research/`](./docs/research) |
| Roadmap | [`docs/roadmap/`](./docs/roadmap) |
| Technical blog | [`docs/blog/`](./docs/blog) |

---

## Contributing

Contributions are welcome. Please report security issues per [`SECURITY.md`](./SECURITY.md).

## License

[MIT](./LICENSE)
