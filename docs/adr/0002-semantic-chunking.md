# ADR 0002 — Semantic Chunking for PDF Ingestion

- **Status:** Accepted
- **Date:** 2026-06-22
- **Area:** RAG / ingestion (`backend/pdf_processor.py`)

## Context

PDF ingestion originally used a fixed-size `RecursiveCharacterTextSplitter`
(`chunk_size=800`, `chunk_overlap=300`, separators `["\n\n", "\n", ".", ""]`).
This splits purely by character count, only *preferring* paragraph/sentence
boundaries. Two problems surfaced for our target documents (German university
lecture slides):

- A chunk boundary can land in the middle of a coherent topic, splitting one
  idea across two chunks and weakening retrieval.
- Character count is not a proxy for meaning: a hard 800-char cut can merge two
  unrelated topics or sever one.

We wanted boundaries that follow the *meaning* of the text while still keeping
chunks roughly ~800 characters so embeddings stay representative and retrieval
context stays bounded.

## Decision

Switch ingestion to **semantic chunking with a size guard**:

1. **Primary split — `SemanticChunker`** (`langchain-experimental`):
   - `breakpoint_threshold_type="percentile"`, `breakpoint_threshold_amount=90`
   - `min_chunk_size=400` (merges fragments below the floor)
   - Reuses `get_embedding_function()` from `rag.py` so the *same* embedding model
     (`nomic-embed-text`) drives both chunking and retrieval.
   - Called via `split_documents(pages)` so per-page metadata (page numbers) is
     preserved for source attribution.
2. **Guard split:** any resulting chunk longer than **1100 characters** is
   re-split by a `RecursiveCharacterTextSplitter(chunk_size=800,
   chunk_overlap=150)`. This caps over-long chunks that occur when a topic is
   highly cohesive and never crosses the breakpoint threshold.

Net effect: chunks land in roughly the **400–1100 character** band, breaking on
semantic shifts rather than arbitrary character counts.

### Why these values

- **`percentile` (not `standard_deviation`)** — most robust default; judges
  breakpoints by relative distribution, independent of document length.
- **amount = 90, not the default 95** — lecture slides switch topics frequently;
  a blunter threshold avoids shattering every short bullet into its own chunk.
- **`min_chunk_size=400`** — counters the opposite failure mode (slides with
  short topics producing many tiny chunks) by merging fragments.
- **guard at 1100, split target 800** — leaves ~300 chars of slack so a slightly
  long but clean semantic chunk is kept intact; only clearly oversized chunks are
  cut.

## Consequences

**Positive**

- Chunks are topically coherent; retrieval context is more self-contained.
- Size stays bounded, so embeddings remain representative and prompt context is
  predictable.
- Page metadata is preserved, so `/ask` can still cite page numbers.

**Negative / costs**

- **New dependency:** `langchain-experimental` (`pip install
  langchain-experimental`).
- **Slower uploads:** semantic chunking embeds each sentence to find breakpoints,
  adding latency proportional to document size. Mitigated for now by the
  background-thread upload + frontend polling (`PdfAPI.uploadAndWait`); a future
  Celery worker (roadmap) would offload it entirely.
- **Re-ingestion required:** existing ChromaDB collections were built with the
  old splitter. Switching requires re-uploading existing PDFs so collections are
  rebuilt with the new chunk boundaries (`store_chunks` deletes and recreates the
  collection on re-upload).

## Notes / alternatives considered

- **Keep character splitting, only improve separators** (add CJK punctuation,
  `". "` to dodge German abbreviations like `z.B.`). Cheaper, zero embedding
  cost, but does not deliver true semantic boundaries.
- **Proposition-based chunking** (LLM rewrites text into atomic propositions):
  highest quality but one Claude call per document — too slow/expensive.
- **`standard_deviation` threshold type** — potentially more adaptive across
  different professors' slide densities; can be revisited if a single percentile
  proves too rigid across courses.
