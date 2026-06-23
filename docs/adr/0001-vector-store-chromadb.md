# ADR-0001: 选择 ChromaDB 作为向量存储

- **状态 (Status)**: Accepted
- **日期 (Date)**: 2026-06-23
- **关联 (Related)**: [knowledge-graph-schema.md](../architecture/knowledge-graph-schema.md) · [ADR-0002 切块策略](./0002-semantic-chunking.md)

---

## 背景 (Context)

EduPrep 的 RAG 流程需要一个向量数据库，用来存储 PDF 切块的 embedding 并支持相似度检索。选型时项目处于以下约束下：

- **单人开发 / 本地优先**：开发与演示主要在单机进行，不希望为一个向量库额外维护一套服务端基础设施。
- **嵌入在本地算**：embedding 由本地 Ollama (`nomic-embed-text`) 生成，向量库只需负责存储与检索。
- **按 PDF 隔离**：每份 PDF 需要独立的检索空间（当前用 collection 名 = 文件名实现，见 `rag.py:store_chunks`）。
- **持久化**：重启后向量数据不能丢，需要落盘。
- **与 LangChain 集成**：检索流水线基于 LangChain，向量库最好有一等公民的 LangChain 封装。

## 决策 (Decision)

采用 **ChromaDB**（通过 `langchain_chroma.Chroma`），以 `persist_directory="./chroma_db"` 本地持久化，每份 PDF 用 `sanitize_collection_name(filename)` 作为独立 collection。

## 理由 (Rationale)

- **零额外基础设施**：ChromaDB 以嵌入式 / 进程内方式运行，无需单独的数据库服务，契合单机开发与演示。
- **LangChain 原生支持**：`Chroma.from_documents()` 一行完成"计算 embedding + 入库"，开发摩擦最小。
- **持久化开箱即用**：`persist_directory` 直接落盘。
- **Collection 模型天然契合"按 PDF 隔离"**：每个 PDF 一个 collection，删除 PDF 即 `delete_collection()`，干净利落。

## 备选方案 (Alternatives Considered)

| 方案 | 不选的原因 |
|---|---|
| **pgvector**（PostgreSQL 扩展） | 项目已有 PostgreSQL，长期看很有吸引力（可与业务数据同库、同事务）。但初期需要安装扩展、自己管理索引（IVFFlat/HNSW）与维度，开发成本高于 Chroma。**列为未来迁移候选**（见"后果"）。 |
| **FAISS** | 高性能，但本身只是索引库，不带持久化/元数据管理/collection 概念，需自己封装，不如 Chroma 省事。 |
| **Qdrant / Weaviate** | 功能强、可扩展，但需要独立服务端（Docker），与"本地优先、零基础设施"目标冲突。 |
| **Pinecone（托管）** | 托管 SaaS，引入外部依赖与成本，且把向量数据送出本机，与"嵌入本地算、数据留本机"的取向不符。 |

## 后果 (Consequences)

**正面**
- 开发/演示零运维负担，上手快。
- 删除 PDF 的清理逻辑简单（drop collection）。

**负面 / 需注意**
- **不是分布式**：单节点，无法横向扩展；面向大规模多用户生产时是瓶颈。
- **跨 PDF / 课程级检索需要应用层协调**：collection 按 PDF 隔离，意味着"全课程检索"需在应用层跨 collection 取数据（见 knowledge-graph-schema.md 的 `source_refs` 设计）。
- **与业务库分离**：向量在 Chroma、业务数据在 PostgreSQL，无法跨库事务。

## 未来迁移路径 (Future Path)

当出现以下信号时，重新评估迁移到 **pgvector**：
- 需要把向量与课程级知识图谱（`concept.embedding`）放在同库做联合查询；
- 多用户生产部署需要统一的备份/运维；
- 跨 collection 检索成为性能瓶颈。

迁移成本可控：embedding 由本地 Ollama 生成，与存储解耦，更换向量库只需重建索引（重新上传 PDF）。该取舍记录在 [knowledge-graph-schema.md](../architecture/knowledge-graph-schema.md) 的 Open Questions 中。
