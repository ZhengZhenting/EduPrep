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

> The features below are shipping today. Each is being upgraded along the [roadmap](#roadmap--where-its-heading) — e.g. the knowledge graph will soon drive GraphRAG retrieval and learning-path generation (P9), and the Agent will gain more tools as knowledge tracing (P10) and MCP (P11) land.

### 📖 Preview
Upload a German lecture PDF and automatically receive a **bilingual summary (German + Chinese)**, a key vocabulary list with translations, and a Mermaid structure diagram of the lecture.

### 🕸️ Knowledge Graph
Every PDF upload automatically triggers **concept + relation extraction** (Claude structured output) into a **course-level** knowledge graph — concepts are canonicalized in German (the source language) to keep entity disambiguation accurate across PDFs. New concepts are merged into the existing graph via a 3-tier match (exact name → embedding-similarity candidates → Claude batch adjudication), and a second pass links each PDF's concepts to concepts from *other* PDFs in the same course (`is_a` / `prerequisite` / `part_of` / `related` edges) — this is what stitches e.g. a "KNN" lecture to an earlier "Nearest Centroid" lecture automatically. The course page has a **文件列表 / 知识图谱** toggle rendering the graph via Mermaid: concepts shared across multiple PDFs are highlighted in purple, `related` edges are dashed and hidden by default. See [`concept-extraction-pipeline.md`](./docs/architecture/concept-extraction-pipeline.md).

### 💬 Learn
Ask questions in natural language, answered by a **LangGraph Agent** (`POST /ask/agent`): a Planner→ToolNode→Reflector loop that decides which tools to call — `search_pdf` (hybrid RAG: BM25 + vector + RRF), `query_knowledge_graph` (P8's course-level concept graph), `get_concept_mastery`, and `search_web` (Tavily) — and self-checks that its draft answer is actually supported by what the tools returned before finalizing (retrying once if not). Source badges (`pdf` / `web` / `pdf+web`) and page numbers / URLs are shown per answer. The earlier single-shot `/ask` (hybrid RAG + one-off LLM-decided web search, ADR-0003) still exists as an independent endpoint. See [`agent-orchestration.md`](./docs/architecture/agent-orchestration.md).

### 📝 Quiz
Generate **personalised** multiple-choice questions from the lecture. The system reads tracked weak concepts from memory and prioritises them. Scores are persisted to PostgreSQL.

---

## Architecture

```
React SPA (Auth → Courses → PDF → Preview / Learn / Quiz / Knowledge Graph)
        |
FastAPI Backend (JWT-protected endpoints)
        |
  ┌─────────────┬───────────────────────┬────────────────────────┬─────────────────┐
  |              |                       |                        |
Hybrid RAG   Knowledge Graph        LangGraph Agent           Memory System
Pipeline     (on upload)            (POST /ask/agent)
  ├─ Vector    ├─ Concept + relation   Planner → ToolNode →      ├─ Conversation (PG)
  │ (ChromaDB) │  extraction (Claude)  Reflector loop, tools:    └─ Quiz Progress (PG)
  ├─ BM25      ├─ 3-tier disambig.     search_pdf ·
  └─ RRF       │  (name→embed→Claude)  query_knowledge_graph ·
               └─ Cross-PDF linking    get_concept_mastery ·
                  (concept/concept_    search_web
                  edge tables)
        |              |                       |
        └──────────────┴───────────────────────┘
                        |
        Claude API (claude-sonnet-4-5) + Ollama (local embeddings, nomic-embed-text)
                        |
              LangFuse v4 (full LLM call tracing)
```

The earlier single-shot `/ask` (hybrid RAG + one-off LLM-decided web search, ADR-0003) still runs as an independent endpoint alongside the Agent.

📐 Detailed design docs live in [`docs/architecture/`](./docs/architecture) — including [knowledge-graph-schema.md](./docs/architecture/knowledge-graph-schema.md), [concept-extraction-pipeline.md](./docs/architecture/concept-extraction-pipeline.md), and [agent-orchestration.md](./docs/architecture/agent-orchestration.md).

---

## Tech Stack

| Layer | Now (shipping) | Planned (roadmap) |
|---|---|---|
| Frontend | React 18, Vite, TanStack Router + Query, Tailwind + shadcn/ui + Mermaid-based knowledge-graph viz | Upgrade to react-flow / cytoscape.js for interactive (draggable/zoomable) graph |
| Backend | FastAPI, Python 3.11 | Celery + Redis async workers |
| LLM | Claude API — `claude-sonnet-4-5` (Planner/Reflector included) | Model tiering — `claude-opus-4-8` main loop / `claude-sonnet-4-6` tools (deferred until cost/quality data justifies it) |
| Embeddings | Ollama — `nomic-embed-text` (local; used for chunk *and* concept vectors) | — |
| RAG | LangChain + ChromaDB + BM25 + RRF; semantic chunking (SemanticChunker) | **GraphRAG** (graph-expanded retrieval, P9) |
| Knowledge graph | Course-level `concept`/`concept_edge` tables; Claude structured extraction + 3-tier disambiguation + cross-PDF linking | Learning-path generation (topological sort over `prerequisite` edges, P9) |
| Agent | **LangGraph** orchestration — Planner→ToolNode→Reflector loop (`POST /ask/agent`), 4 tools | **MCP server** (expose tools to Claude Desktop / Cursor) |
| Learning science | weak-concept tracking (legacy `/ask`) | **Knowledge tracing (BKT)** + **spaced repetition (FSRS)** + adaptive quizzing (P10) |
| Web search | Tavily API | — |
| Database | PostgreSQL + SQLAlchemy + Alembic; **7 original + 4 knowledge-graph tables** | — |
| Auth | JWT (python-jose) + bcrypt | — |
| Observability | LangFuse v4 + Loguru | Prometheus + Grafana + Jaeger |
| Eval | Retrieval/answer harness ([`backend/eval`](./backend/eval), P6 baseline) | Agent-path evaluation (no Recall/Answer comparison vs. plain `/ask` yet) |

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
| POST | `/ask` | Hybrid RAG Q&A with optional web supplement (single-shot, ADR-0003) |
| POST | `/ask/agent` | **LangGraph Agent** Q&A — Planner→ToolNode→Reflector loop over search_pdf/query_knowledge_graph/get_concept_mastery/search_web |
| GET | `/courses/{id}/graph` | Course-level knowledge graph as `{nodes, edges}` (P8) |
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
│   ├── pdf_processor.py    # PyPDFLoader + SemanticChunker (percentile 90) + 1100-char guard split + overlay dedup + header/footer strip
│   ├── page_triage.py      # P7: cheap per-page signals → text vs vision triage
│   ├── vision_transcribe.py # P7: vision transcription (disabled by default — net-negative for retrieval, see ADR-0004)
│   ├── memory.py           # Conversation memory + quiz progress (PostgreSQL)
│   ├── tools.py            # Plain functions: search_web, generate_mermaid_chart
│   ├── concept_extraction.py # P8: concept + relation extraction, disambiguation, cross-PDF linking
│   ├── backfill_emb.py     # P8: one-time script — backfill concept.embedding for pre-existing concepts
│   ├── agent_graph.py      # P11: LangGraph StateGraph — Planner → ToolNode → Reflector
│   ├── agent_tools.py      # P11: agent tools — search_pdf, query_knowledge_graph, get_concept_mastery, search_web
│   ├── models.py           # SQLAlchemy ORM — 7 original + 4 knowledge-graph tables (concept, concept_edge, concept_mastery, learning_path)
│   ├── database.py         # PostgreSQL connection
│   ├── observability.py    # LangFuse + Loguru initialisation
│   ├── eval/               # AI evaluation harness (P6 baseline + ongoing calibration)
│   └── alembic/            # Migration scripts
├── frontend/src/
│   ├── routes/             # login, register, dashboard, courses (incl. 文件列表/知识图谱 toggle), workspace
│   ├── lib/                # api.ts (axios + JWT + GraphAPI), auth.tsx, use-auth.ts
│   └── components/         # ui/ (shadcn) + workspace/ (Preview/Learn/Quiz/Notes/Mermaid)
├── docs/
│   ├── architecture/       # knowledge-graph-schema.md, concept-extraction-pipeline.md, agent-orchestration.md,
│   │                       # multimodal-ingestion.md, model-tiering.md, ER diagram
│   ├── adr/                # Architecture Decision Records (0001–0005, 0009 — see docs/adr)
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
- **Concept names stay in German (source language)** — canonicalizing in German, not translating at storage time, keeps entity disambiguation and cross-PDF matching accurate; translation happens only at output/display time. Relation types are `is_a` / `prerequisite` / `part_of` / `related`, cross-checked against SKOS/ConceptNet/RDFS conventions. See [concept-extraction-pipeline.md](./docs/architecture/concept-extraction-pipeline.md).
- **3-tier entity disambiguation** — exact name match → embedding-similarity candidates → Claude batch adjudication (embedding alone would false-merge related-but-distinct concepts like "Euclidean distance" vs. "Manhattan distance"). Cross-PDF relation linking runs a second pass restricted to *other-PDF-sourced* concepts only (a bug where this wasn't restricted caused a course's first PDF to wrongly link to itself — caught and fixed during calibration).
- **Local embeddings** — Ollama runs locally; only LLM inference and web search leave the machine.
- **Vision transcription reversed for retrieval** — P7 measured that full-page vision transcription *hurts* retrieval (homogenizes the corpus, crowds out the exact relevant page); shipped disabled by default, header/footer stripping kept as the one real win. See [ADR-0004](./docs/adr/0004-multimodal-ingestion-vision-llm.md).
- **Concept embedding storage** — course-level concept vectors are stored as PostgreSQL JSONB with pure-Python cosine similarity rather than pgvector; ChromaDB (chunk vectors) is kept separate for now. See [ADR-0005](./docs/adr/0005-vector-storage-jsonb-vs-pgvector.md).
- **LangGraph for Agent orchestration** — a single Planner→ToolNode→Reflector graph replaces ad-hoc tool-decision code once there were 4+ tools and a need to retry on unsupported answers; the graph's conditional edges *are* the orchestrator. See [ADR-0009](./docs/adr/0009-langgraph-vs-custom-loop.md).

---

## Roadmap — Where It's Heading

EduPrep is under **active, iterative development**. The path from "RAG chat app" to "knowledge-graph-driven adaptive learning system" is broken into focused phases — each shipping working features **and** its own documentation.

| Phase | Scope | Status |
|---|---|---|
| P1–P3 | Tool layer · hybrid RAG · PostgreSQL · course/PDF management · LangFuse observability | ✅ Complete |
| P4–P5 | JWT auth · memory system · personalised quiz · TanStack Router + shadcn/ui redesign | ✅ Complete |
| **P6** | Evaluation baseline ([harness](./backend/eval) + [golden dataset](./backend/eval/datasets/golden_qa.jsonl) + [methodology](./docs/evaluation/methodology.md) + [baseline](./docs/evaluation/baseline.md)) · docs foundation | ✅ Complete |
| **P7** | **Vision-LLM multimodal ingestion** — read formulas / diagrams / images / tables that text-only extraction misses  | ✅ Complete |
| **P8** | **Knowledge graph** construction + visualization (course-level concept network)  | ✅ Complete |
| **P9** | **GraphRAG** retrieval + learning-path generation  | 📋 Planned |
| **P10** | **Learning-science engine** — knowledge tracing (BKT) + spaced repetition (FSRS) + adaptive quizzing | 📋 Planned |
| **P11** | **Agent + Tools + MCP** — LangGraph orchestration ([`agent-orchestration.md`](./docs/architecture/agent-orchestration.md)), EduPrep as an MCP server | 🚧 Agent loop done, MCP planned |
| P12 | Hardening: reliability / security / **governance** (Redis cache, rate limiting, circuit breaker; model/prompt versioning, rollback, GDPR) | 📋 Planned |
| P13 | Testing · Docker · CI/CD (incl. **eval regression gate**) · Prometheus + Grafana + Jaeger | 📋 Planned |

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
