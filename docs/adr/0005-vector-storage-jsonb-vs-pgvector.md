# ADR-0005: 概念向量存储用 JSONB，暂不引入 pgvector / 暂不合并 ChromaDB

- **状态 (Status)**: Accepted
- **日期 (Date)**: 2026-07-07
- **关联 (Related)**: [knowledge-graph-schema.md](../architecture/knowledge-graph-schema.md)（`concept.embedding` 字段）· [concept-extraction-pipeline.md](../architecture/concept-extraction-pipeline.md)（§6.3/§8 消歧与跨PDF依赖 embedding）· [ADR-0001 ChromaDB](./0001-vector-store-chromadb.md)（未来迁移路径的前情）

---

## 背景 (Context)

P8 知识图谱需要给每个 `concept` 存一个 embedding 向量，供**实体消歧**（§6.4）和**跨 PDF 关系推理**（§6.5）计算余弦相似度。项目现状：

- **chunk 向量已经在 ChromaDB**（本地嵌入式，ADR-0001 决策），检索管线跑得很好；
- **PostgreSQL 是业务数据库**（7 张原有表 + P8 新增 4 张知识图谱表），本身不带向量能力；
- **PostgreSQL 版本是 18.4（Windows 本地）**，实测 `pg_available_extensions` 中**没有 `vector` 扩展**——pgvector 在 Windows 上没有官方预编译包，要用只能本地编译（MSVC）或改用 Docker 镜像（`pgvector/pgvector`）；
- **规模很小**：一门课的概念数量是几十到几百个，不是几十万级。

需要决定两件事：① `concept.embedding` 用什么存、怎么算相似度；② 要不要趁 P8 把 ChromaDB 也合并进 PostgreSQL（一个库了事）。

## 决策 (Decision)

1. **`concept.embedding` 存 PostgreSQL 的 `JSONB`**（一个 float 数组），**不引入 pgvector**。
2. **消歧 / 跨 PDF 的相似度计算用纯 Python 实现的余弦相似度**（`_cosine`，见 `concept_extraction.py`），不依赖 numpy、不依赖数据库端向量运算。
3. **暂不合并 ChromaDB 进 PostgreSQL**（chunk 向量继续留在 ChromaDB）。合并推迟到 **P13 容器化**阶段，那时 Docker 环境下 `pgvector/pgvector` 镜像可以零成本获得。

## 理由 (Rationale)

- **规模决定不需要索引**：概念数量是几十~几百量级，暴力遍历算余弦相似度是毫秒级操作。pgvector 的核心价值（HNSW/IVFFlat 近似最近邻索引）在这个规模下**完全用不上**，引入它只是增加复杂度而无实际收益。
- **环境摩擦 vs 收益不对等**：本地 Windows PostgreSQL 18.4 没有 pgvector，要用只能：①手动用 MSVC 编译扩展（脆弱、耗时，且要确认 pgvector 是否已支持 PG18）；②切换到 Docker Postgres。这两条路对"几十个向量算余弦"这个需求来说，投入产出比很低。
- **JSONB 已经是项目的既定模式**：`sources`、`weak_concepts`、`source_refs`、`fsrs_state` 等字段都用 JSONB，`embedding` 用同样的方式技术栈一致，零新增依赖。
- **ChromaDB 合并同理不划算**：合并需要重写 `rag.py` 的存储/检索逻辑（改用 pgvector 的 SQL `<=>` 距离操作符）、重新 ingest 所有 PDF、装 pgvector 扩展——而 ChromaDB **现在运行良好**，纯粹为了"数据库统一"的洁癖去重构一个没有问题的模块，不是当前投入的最佳去处。
- **P13 是天然的重估时机**：roadmap P13 本就要做 Docker + docker-compose 全栈容器化。届时 `pgvector/pgvector:pgXX` 官方镜像可以直接拿来用，pgvector 环境的获取成本降到几乎为零，那时再合并 ChromaDB 是顺水推舟，而不是现在额外造一个环境。

## 备选方案 (Alternatives Considered)

| 方案 | 不选的原因 |
|---|---|
| **本地编译 pgvector（在当前 Windows PG18 上）** | 需要 Visual Studio Build Tools + 手动 `Makefile.win` 编译，且需先确认 pgvector 版本对 PG18 的支持情况；对"几十个向量"这个规模而言纯属过度工程。 |
| **现在就切换到 Docker Postgres + pgvector，合并 ChromaDB** | 技术上可行、也更"干净"，但需要立即重写 `rag.py` 检索层 + 重新 ingest 所有 PDF + 改变本地开发工作流（需要常驻 Docker）。收益（一致性、SQL 联合查询）在当前规模下不紧迫，且与 P13 的既定容器化工作重复。**列为 P13 的既定路径，不提前**。 |
| **概念 embedding 也放 ChromaDB（新建一个 concept collection）** | 会让"一次实体消歧"需要跨两个存储系统（查 Postgres 拿候选 id，再查 Chroma 拿向量），徒增复杂度；概念数据本就该和 `concept` 表的其它字段（`name`/`source_refs`）放在一起，便于单次查询、单一事务。 |
| **NumPy 加速余弦计算** | 当前 Python 原生实现（`_cosine`）在几十~几百概念规模下已经是毫秒级，NumPy 收益不明显，暂不引入这个额外依赖；概念数量大幅增长时可重新评估。 |

## 后果 (Consequences)

**正面**
- 零新增依赖、零新增基础设施，P8 消歧/跨 PDF 功能可以立即在现有环境上跑通（已验证：NCC + KNN 端到端跑通）。
- 概念数据、图谱结构、embedding 全部在同一个 PostgreSQL 库、同一张 `concept` 表，查询/事务简单。
- 与 ADR-0001 的"未来迁移路径"完全兼容——两个决策（chunk 向量、concept 向量）指向同一个未来终点（P13 pgvector 合并），不产生技术债分叉。

**负面 / 需注意**
- **规模上限**：JSONB + 暴力余弦只适合"几十~几千"量级；如果未来出现"全局概念库"（§8 待决问题：跨课程概念复用）这种量级跃升的场景，需要重新评估索引方案。
- **暂时两个存储系统并存**：chunk 向量在 ChromaDB、概念向量在 PostgreSQL JSONB，短期内是两套机制，需要开发者记住"两处都是向量，但存法不同"（已在 [model-tiering.md](./../architecture/model-tiering.md) 记录本地 embedding 的统一入口 `get_embedding_function()`，两处都复用它，只是落盘位置不同）。
- **一致性问题依旧存在**：删除 PDF 时仍需应用层同时处理 ChromaDB collection 和 PostgreSQL 记录（这个问题在 ADR-0001 中已识别，P13 合并后可根治）。

## 触发重新评估的信号 (When to Revisit)

- 单门课程概念数量增长到需要索引才能保证消歧响应速度（数千级以上）；
- P13 容器化启动，Docker + pgvector 镜像唾手可得；
- 出现"课程级边过滤 + 向量检索联合查询"的真实产品需求（当前 P9 GraphRAG 的 1–2 跳扩展查询用不到这个）；
- 手动维护 ChromaDB/PostgreSQL 两处删除导致过一致性 bug。

到时按 ADR-0001 的 Future Path 一并把 chunk 向量 + 概念向量迁移到 pgvector。
