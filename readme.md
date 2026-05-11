# EduPrep 📚

An AI-powered learning platform for international students in Germany, designed to reduce language barriers and support structured learning through a **Preview → Learn → Review** cycle.

---

## Features

### 📋 Preview Mode
- Upload a lecture PDF and automatically generate a **bilingual summary** (German + Chinese)
- Extract and display the **10 most important technical terms** from the lecture

### 💬 Learn Mode (Q&A)
- Ask questions about the lecture content in natural language
- **RAG-based answers**: semantically retrieves the most relevant chunks from the PDF
- Displays the **source page number** for every answer
- Maintains **conversation history** so follow-up questions are understood in context
- **Automatic web search fallback** via Tavily when the answer is not found in the PDF, with clear source labeling

### 🧪 Review Mode (Quiz)
- Generates **5 multiple-choice questions** based on the lecture content
- One question at a time with immediate feedback (correct/incorrect)
- Shows **Chinese explanation** for every answer
- Displays **score and mastery percentage** upon completion
- Saves quiz progress to **localStorage** for persistence across sessions

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React + Vite | Component-based SPA |
| Backend | FastAPI | Async API server |
| LLM | Ollama (qwen2.5:3b / qwen3:4b) | Local, offline-capable language model |
| Embeddings | Ollama (embeddinggemma) | Local vector embeddings |
| RAG Framework | LangChain | Retrieval-augmented generation pipeline |
| Vector Database | ChromaDB | Persistent local vector storage |
| PDF Processing | LangChain PyPDFLoader | Text extraction with page number metadata |
| Web Search | Tavily API | Fallback search when PDF content is insufficient |
| Progress Storage | localStorage | No login required |

---

## Architecture

```
Frontend (React)
    ↓
FastAPI Backend
    ↓
┌─────────────────────────────────────────┐
│              API Router                 │
│   /upload   /preview   /ask   /quiz     │
└─────────────────────────────────────────┘
    ↓                        ↓
RAG Pipeline              Tavily Search
(LangChain)               (web fallback)
    ↓
┌──────────────────────┐
│  PDF Processor       │  PyPDFLoader → chunk (800 chars, 150 overlap)
│  Embedding Model     │  Ollama embeddinggemma
│  ChromaDB            │  Persistent vector storage
│  LLM                 │  Ollama qwen2.5:3b
└──────────────────────┘
```

---

## Project Structure

```
eduprep/
├── backend/
│   ├── main.py              # FastAPI app, all API endpoints
│   ├── pdf_processor.py     # PDF parsing and chunking
│   ├── rag.py               # ChromaDB storage and semantic search
│   ├── chroma_db/           # Persistent vector database (auto-generated)
│   └── .env                 # API keys (not committed to git)
├── frontend/
│   └── src/
│       └── App.jsx          # React frontend (single page)
└── README.md
```

---

## Current Status

| Feature | Status |
|---|---|
| PDF upload and chunking | ✅ Complete |
| ChromaDB vector storage | ✅ Complete |
| RAG semantic search | ✅ Complete |
| Source page citation | ✅ Complete |
| Conversation history | ✅ Complete |
| Preview mode (bilingual summary) | ✅ Complete |
| Preview mode (vocabulary list) | ✅ Complete |
| Learn mode (Q&A) | ✅ Complete |
| Tavily web search fallback | ✅ Complete |
| Review mode (quiz generation) | ✅ Complete |
| Quiz scoring and progress bar | ✅ Complete |
| localStorage progress saving | ✅ Complete |
| UI redesign (Tailwind) | 🔲 Planned (Day 10) |
| Multi-file management | 🔲 Planned |
| User authentication | 🔲 Optional |

---

## Design Principles

- **Offline-first**: All AI components run locally via Ollama, no API costs during normal use
- **No login required**: Learning progress stored in browser localStorage
- **Language accessible**: Bilingual output (German + Chinese) for international students
- **Privacy-friendly**: PDFs and conversation data never leave the local machine

---

## Known Limitations

- RAG relevance threshold (currently `1.1`) may misclassify edge cases; an LLM-based confidence detection approach is planned
- Local LLM response time is 15–60 seconds depending on hardware
- PDF pages that are scanned images cannot be parsed (text-based PDFs only)
- Conversation history and uploaded file references are lost on page refresh

---

*Built as a personal project — EduPrep is currently in active development.*
