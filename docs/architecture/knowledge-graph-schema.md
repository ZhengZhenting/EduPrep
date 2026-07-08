# 知识图谱数据库 Schema 设计

> **状态**: **Implemented（4 张表已迁移、字段已投入使用）**
> **更新**: 2026-06-20 设计 → 2026-07-07 修订 → 2026-07-08 迁移执行 + 实测
> **作者**: EduPrep Team
> **关联文档**: [concept-extraction-pipeline.md](./concept-extraction-pipeline.md)（抽取流程 + 关系/语言/属性决策 + §9 实测校准）· retrieval-flow.md（待写，P9）· [ADR-0005](../adr/0005-vector-storage-jsonb-vs-pgvector.md)（图存储选型：JSONB，已定）· ADR-0006 (GraphRAG，待写，P9)
>
> ⚠️ **P8 设计更新 (2026-07-07)**：关系类型、概念语言、属性字段已修订（本文相关处已更新）；决策依据与标准出处见 [concept-extraction-pipeline.md](./concept-extraction-pipeline.md)。
> ✅ **P8 实现更新 (2026-07-08)**：4 张表已通过 Alembic 迁移建成；`concept.embedding` 已按 [ADR-0005](../adr/0005-vector-storage-jsonb-vs-pgvector.md) 定为 JSONB 并在建概念时即填充；`concept_edge.weight` 已用于存储跨 PDF 边的余弦相似度。

---

## 1. 设计目标与核心判断

EduPrep 的学习单位从 **PDF 级** 上升到 **课程级 (course)**。一个学期内，一门课会持续累积多份 PDF，而真正的"知识"和"学习状态"是贯穿整门课的：

- 同一个概念会在多份 PDF 中反复出现 → 必须是图谱里**一个节点**，回链到多份来源；
- 先修关系往往**跨 PDF**（第 9 周依赖第 3 周）→ 只有课程级才画得出来；
- "对某概念的掌握度"是贯穿整门课的状态，不属于任何单份 PDF。

**核心原则：物理文档层保留 PDF 级，知识层与学习者模型层上升到课程级。**

| 层 | 粒度 | 处理方式 |
|---|---|---|
| 文档层 (`pdf_file`, 切块, ChromaDB) | PDF 级 | **不变** |
| 对话 / 笔记 (`message`, `note`) | PDF 级 | **不变** |
| Preview 预习 | PDF 级 | **不变** |
| 知识图谱 (`concept`, `concept_edge`) | **课程级** | **新增** |
| 学习者模型 (`concept_mastery`) | **课程级** | **新增** |
| 学习路径 (`learning_path`) | **课程级** | **新增** |
| 薄弱概念 (`memory.weak_concepts`) | PDF 级 → 课程级 | **迁移** |

---

## 2. 现有 Schema（保留不变的部分）

来自 `backend/models.py`，7 张表中以下 6 张**完全保留**：

```
user           (id, email UK, name, password_hash, created_at)
course         (id, user_id FK→user, title, created_at)
pdf_file       (id, course_id FK→course, filename, chunk_count, created_at)
message        (id, pdf_file_id FK→pdf_file, role, content, source_type, sources JSONB, created_at)
note           (id, pdf_file_id FK→pdf_file, type, content, created_at)
quiz_progress  (id, pdf_file_id FK→pdf_file, score, total, percentage, wrong_questions JSONB, created_at)
```

`memory` 表保留，但其中的 `weak_concepts` 字段将被迁移（见 §5）：

```
memory  (id, pdf_file_id FK→pdf_file UK, weak_concepts JSONB,  ← 迁移到 concept_mastery
         learning_style, history_summary, last_compressed_at, updated_at)
```

> `memory` 表的 `history_summary` / `learning_style` / `last_compressed_at`（PDF 级对话记忆）继续保留并照常使用，**仅 `weak_concepts` 上升到课程级**。

---

## 3. 新增表（全部挂在 course 上）

### 3.1 `concept` — 课程级概念节点

知识图谱的节点。一个概念归属一门课程，并通过 `source_refs` 回链到**多份 PDF 的多个 chunk**——这是把零散 PDF 缝成网络的关键字段。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `course_id` | Integer FK→course (CASCADE) | 课程级归属 |
| `name` | String(200) | 概念规范名 = **德语（源语言）**，唯一标识 + 消歧匹配键（见下方语言决策） |
| `description` | Text, nullable | 概念简述（Claude 抽取生成，德语） |
| `attributes` | JSONB, nullable | **灵活属性扩展口**：静态学科属性（定义/公式/考点…）按需填；动态属性（难点/易错点）不存此处，由 P10 学习者模型算。**当前尚未填充**（P8 垂直切片未用到，留待具体功能需要时再抽） |
| `embedding` | **JSONB**（已定，见 [ADR-0005](../adr/0005-vector-storage-jsonb-vs-pgvector.md)），nullable | 概念向量（`"name: description"` 文本算，Ollama `nomic-embed-text`，768 维），**建概念时即计算填充**；消歧/跨PDF 用 Python 原生余弦比对（无需 pgvector，规模小） |
| `source_refs` | JSONB | 来源列表 `[{pdf_file_id, chunk_ids:[...]}]`，**支持跨 PDF** |
| `created_at` | DateTime | |
| `updated_at` | DateTime | 增量合并时更新 |

唯一约束建议：`(course_id, name)` 软唯一（消歧后保证课程内概念名不重复）。

> **语言决策（2026-07-07）**：概念名**统一存德语（材料源语言）**，删除原 `name_de` 列（name 已是德语，冗余）。中文/英文在**输出时翻译**，不入库。理由：实体消歧需在同一语言空间比对（存翻译会导致假合并/假分裂），且德语术语本身是考试所需。遵循 SKOS `prefLabel`（源语言）+ 输出层 `altLabel` 模式。详见 [concept-extraction-pipeline.md §3](./concept-extraction-pipeline.md)。

### 3.2 `concept_edge` — 概念间关系边

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `course_id` | Integer FK→course (CASCADE) | 冗余存课程，便于按课程整图查询 |
| `from_concept_id` | Integer FK→concept (CASCADE) | |
| `to_concept_id` | Integer FK→concept (CASCADE) | |
| `relation_type` | String(20) | `is_a` / `prerequisite` / `part_of` / `related` |
| `weight` | Float, default 1.0 | 关系强度。**PDF 内部抽取的边**：默认 1.0；**跨 PDF 推理的边**（§6.5）：存该概念对的**余弦相似度**（用于以后按权重过滤弱 `related`，见 concept-extraction-pipeline.md §8） |
| `created_at` | DateTime | |

唯一约束：`(from_concept_id, to_concept_id, relation_type)` 防重复边。

**关系类型语义**（4 条，标准对照与决策依据见 [concept-extraction-pipeline.md §2](./concept-extraction-pipeline.md)）：

| relation_type | 含义 | 标准出处 | 用途 |
|---|---|---|---|
| `is_a` | from 是 to 的子类/下位概念 | `rdfs:subClassOf` / ConceptNet `IsA` / WordNet 上下位 | 分层聚类、知识脉络 |
| `prerequisite` | from 是 to 的先修 | ConceptNet `HasPrerequisite` | 学习路径拓扑排序 |
| `part_of` | from 是 to 的组成部分 | SKOS `broader`/`narrower` / ConceptNet `PartOf` | 整体-部分（知识点→小考点） |
| `related` | 一般相关/共现 | SKOS `related` / ConceptNet `RelatedTo` | GraphRAG 检索扩展 |

> **变更（2026-07-07）**：**新增 `is_a`**（教育概念脉络主要靠上下位，且与 `part_of` 语义不同）；**删除 `equivalent_de`**（它不是概念间关系，而是同一概念的德语名 = SKOS `altLabel`，已随"概念名统一存德语"消解）；学科特殊关系（`互斥`/`因果`）需领域专家精修，暂缓入 backlog。

### 3.3 `concept_mastery` — 课程级学习者模型

记录学习者对每个概念的掌握度 + FSRS 复习状态。**替代** `memory.weak_concepts`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `course_id` | Integer FK→course (CASCADE) | |
| `concept_id` | Integer FK→concept (CASCADE) | |
| `mastery_prob` | Float, default 0.0 | 掌握概率 [0,1]，知识追踪 (BKT) 更新 |
| `last_review` | DateTime, nullable | 上次复习时间 |
| `next_review` | DateTime, nullable | FSRS 计算的下次复习时间 |
| `fsrs_state` | JSONB, nullable | FSRS 内部状态 (stability, difficulty 等) |
| `updated_at` | DateTime | |

唯一约束：`(course_id, concept_id)` —— 每门课每个概念一行。

### 3.4 `learning_path` — 课程级学习路径

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer PK | |
| `course_id` | Integer FK→course (CASCADE) | |
| `ordered_concept_ids` | JSONB | 拓扑排序后的概念 id 列表 |
| `generated_at` | DateTime | 生成时间（PDF 增量后可重新生成） |

### 3.5 `quiz_progress` 的小幅扩展

为支持"按概念追踪掌握度"，每道错题关联到概念。最小改动：保持 `wrong_questions` JSONB，但其中每个元素增加 `concept_id` 字段；如需强关联可新增中间表（P9 再定）。

---

## 4. ER 图改动（Mermaid）

新增部分以 `%% NEW` 标注。完整图后续导出为 `docs/architecture/er_diagram.svg`。

```mermaid
erDiagram
    user        ||--o{ course        : owns
    course      ||--o{ pdf_file      : contains
    pdf_file    ||--o{ message       : has
    pdf_file    ||--o{ note          : has
    pdf_file    ||--|| memory        : has
    pdf_file    ||--o{ quiz_progress : has

    %% NEW: 课程级知识层
    course      ||--o{ concept         : "has (course-level)"
    course      ||--o{ concept_edge    : "has"
    course      ||--o{ concept_mastery : "has"
    course      ||--o{ learning_path   : "has"
    concept     ||--o{ concept_edge    : "from/to"
    concept     ||--o{ concept_mastery : "tracked by"
    concept     ||..o{ pdf_file        : "source_refs (JSONB, cross-PDF)"

    concept {
        integer id PK
        integer course_id FK
        varchar name "德语规范名"
        text description
        jsonb attributes
        jsonb embedding
        jsonb source_refs
        timestamp created_at
        timestamp updated_at
    }
    concept_edge {
        integer id PK
        integer course_id FK
        integer from_concept_id FK
        integer to_concept_id FK
        varchar relation_type
        float8 weight
        timestamp created_at
    }
    concept_mastery {
        integer id PK
        integer course_id FK
        integer concept_id FK
        float8 mastery_prob
        timestamp last_review
        timestamp next_review
        jsonb fsrs_state
        timestamp updated_at
    }
    learning_path {
        integer id PK
        integer course_id FK
        jsonb ordered_concept_ids
        timestamp generated_at
    }
```

**级联删除**：删除 course → 级联删除 concept / concept_edge / concept_mastery / learning_path，与现有 `cascade="all, delete-orphan"` 风格一致。`concept` 与 `pdf_file` 之间是 JSONB 软引用（`source_refs`），不设外键，避免删除单份 PDF 时破坏图谱完整性（改为在删除 PDF 时清理对应 source_refs 条目）。

---

## 5. 迁移方案 (Alembic)

> ✅ **Step 1（建表）已执行**（2026-07-08）：`alembic revision --autogenerate` + `alembic upgrade head`，4 张表迁移成功，与现有 7 张表共存无冲突。**Step 2（`weak_concepts` 数据迁移脚本）尚未执行**——当前概念数据完全来自 P8 抽取流水线（§6），不是从旧 `weak_concepts` 迁移而来；`memory.weak_concepts` 仍保留、未标记生效的 deprecated 迁移。

### 5.1 迁移目标

1. 新建 4 张表：`concept`、`concept_edge`、`concept_mastery`、`learning_path`；
2. 把 `memory.weak_concepts`（PDF 级 JSON 字符串数组）升级为课程级 `concept_mastery` 行；
3. `memory.weak_concepts` 字段**暂时保留**（标记 deprecated），确认稳定后再在后续迁移中删除——避免一步到位的风险。

### 5.2 迁移步骤

**Step 1 — 建表**（纯 additive，零风险）

```bash
cd backend
alembic revision -m "add knowledge graph tables (concept, concept_edge, concept_mastery, learning_path)"
# 在生成的迁移脚本 upgrade() 中 create_table 四张新表
alembic upgrade head
```

**Step 2 — 数据迁移**（一次性脚本 `migrate_weak_concepts.py`）

旧的 `weak_concepts` 是自由文本字符串数组，没有结构，因此迁移是"尽力而为"：

```
对每个 course:
    收集该课程下所有 pdf_file 的 memory.weak_concepts（去重）
    for 每个薄弱概念字符串:
        在 concept 表中查找/创建对应 concept（按 name 匹配，未来由抽取流水线规范化）
        在 concept_mastery 写入一行 (course_id, concept_id, mastery_prob=偏低初值如 0.3)
```

> 注意：旧 `weak_concepts` 是非结构化文本，迁移后的概念质量有限。**正式的高质量概念由 P7 的概念抽取流水线生成**，本次迁移只为不丢失历史薄弱信号、平滑过渡。

**Step 3 — 回填来源（可选，P7 抽取流水线上线后）**

概念抽取流水线跑完后，`concept.source_refs` 由抽取结果填充，迁移产生的"裸概念"会被合并/补全。

### 5.3 回滚

- `downgrade()` 删除 4 张新表；
- `memory.weak_concepts` 全程未删，回滚后旧逻辑仍可用。

---

## 6. 增量图谱构建（与本 schema 的关系）

图谱不是每次全量重建，而是随 PDF 上传**增量演进**（详见 [concept-extraction-pipeline.md](./concept-extraction-pipeline.md)）。本 schema 对增量的支持点：

1. **新 PDF 抽取概念** → 与课程已有 `concept` 做实体消歧（用 `concept.embedding` 相似度 + Claude 裁决）；
2. 命中已存在概念 → 仅向其 `source_refs` 追加一条 `{pdf_file_id, chunk_ids}`，**不新建节点**；
3. 新概念 → 插入 `concept` + 必要的 `concept_edge`；
4. `learning_path` 在显著变化后重新生成（不必每次）。

`source_refs` 为 JSONB 而非外键中间表，正是为支持这种"一个课程级概念回链多份 PDF、随时间增长"的场景，避免频繁的 schema 级写放大。

---

## 7. 对现有代码的影响清单

| 模块 | 影响 |
|---|---|
| `models.py` | 新增 4 个 ORM 类；`Course` 增加 4 个 relationship；`Memory.weak_concepts` 标记 deprecated |
| `memory.py` | 读取薄弱概念的逻辑从 `memory.weak_concepts` 改为查询 `concept_mastery`（课程级） |
| `main.py /quiz` | 出题时按 `course_id` 读 `concept_mastery` 而非按 filename 读 weak_concepts |
| `rag.py` | 新增 GraphRAG 检索分支（P9）：命中概念后按 `concept_edge` 扩展取 chunk |
| ChromaDB | **不变**（仍按 filename 分 collection），跨 PDF 检索通过 `source_refs` 协调 |
| Alembic | 新增 2 个迁移（建表 ✅已执行 + 数据迁移脚本，后者未执行） |
| `concept_extraction.py`（新，已实现） | 抽取（§6.2）+ embedding（§6.3）+ 消歧（§6.4）+ 跨PDF（§6.5），供 `main.py` 调用 |
| `main.py`（已实现） | 上传后台处理（`process_pdf_background`）里自动调用概念抽取；新增 `GET /courses/{course_id}/graph` 端点 |
| 前端（已实现） | 课程页新增「文件列表 / 知识图谱」切换，复用 `Mermaid` 组件渲染 `graph TD`，按来源/关系类型着色分层 |

---

## 8. 待决问题 (Open Questions)

- [x] `concept.embedding` 用 JSONB 还是引入 **pgvector**？→ **已定：JSONB**，Python 原生余弦，暂不合并 ChromaDB，推迟到 P13 容器化。见 [ADR-0005](../adr/0005-vector-storage-jsonb-vs-pgvector.md)。
- [ ] 图存储长期是否迁移到 Neo4j？多跳查询成为瓶颈时再评估（ADR-0005 触发信号之一）
- [ ] `quiz_progress` 的概念关联用 JSONB 内嵌还是中间表？（P9 定）
- [ ] 跨课程的概念复用（同一概念出现在多门课）是否需要全局概念库？（暂不做，保持课程隔离）
- [ ] `concept.attributes` 尚未填充——待具体功能（如展示定义/公式）需要时再设计抽取方式。
- [ ] 图谱准确性监测尚未系统化（LangFuse 埋点 + LLM-judge 抽检，计划见 [concept-extraction-pipeline.md §9.4](./concept-extraction-pipeline.md)）。
```
