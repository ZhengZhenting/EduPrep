# Architecture Decision Records

Each ADR captures one significant decision: its context, the decision, and the
consequences. Numbered chronologically; superseded ADRs are marked in their
**Status**.

ADRs are numbered to follow the **logical build order** of the system: pick the
vector store first (the foundation), then how documents are chunked into it, then
how retrieval is augmented.

| # | Title | Status | Date |
|---|---|---|---|
| [0001](./0001-vector-store-chromadb.md) | Vector store — ChromaDB | Accepted | 2026-06-23 |
| [0002](./0002-semantic-chunking.md) | Semantic chunking for PDF ingestion | Accepted | 2026-06-22 |
| [0003](./0003-llm-decided-web-search.md) | LLM-decided web search (replaces cosine-distance threshold) | Accepted | 2026-06-22 |
