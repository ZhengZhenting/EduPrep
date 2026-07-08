# 概念抽取流水线设计 (Concept Extraction Pipeline)

> **状态**: **Implemented（垂直切片跑通）** — 建表→抽取→消歧→跨PDF→endpoint→前端可视化全链路已实现，用 NCC+KNN 真实校准
> **更新**: 2026-07-07（设计）→ 2026-07-08（实现 + 校准）
> **关联**: [knowledge-graph-schema.md](./knowledge-graph-schema.md)（表结构）· [multimodal-ingestion.md](./multimodal-ingestion.md)（P7 视觉转写复用）· [ADR-0005](../adr/0005-vector-storage-jsonb-vs-pgvector.md)（图存储选型）
> **代码**: `backend/models.py`（4 张新表）· `backend/concept_extraction.py`（抽取 + 消歧 + 跨PDF）· `backend/main.py`（上传自动 hook + `GET /courses/{id}/graph`）· `frontend/.../courses.$courseId.tsx`（图谱可视化，复用 `Mermaid` 组件）

---

## 1. 背景：知识图谱 / 构建 / GraphRAG（带出处）

### 1.1 什么是知识图谱 (Knowledge Graph)

术语由 **Google 2012** 推广（[Singhal, "Introducing the Knowledge Graph: things, not strings", Google Blog](https://blog.google/products-and-platforms/products/search/introducing-knowledge-graph-things-not/)）：从"字符串匹配"转向"实体理解"。

权威定义（[Hogan et al., *Knowledge Graphs*, ACM Computing Surveys 54(4), 2021, DOI 10.1145/3447772](https://doi.org/10.1145/3447772)）：
> 知识图谱是一种旨在积累并传达现实世界知识的数据图，其**节点表示实体**，**边表示实体间的关系**。

本质是 **(实体, 关系, 实体)** 三元组。对应本项目：节点 = `concept`，边 = `concept_edge`。

### 1.2 如何构建（标准流水线）

综述（[A Comprehensive Survey on Automatic KG Construction, ACM CSUR 2023, DOI 10.1145/3618295](https://dl.acm.org/doi/10.1145/3618295)；[LLM-empowered KG Construction: A Survey, arXiv:2510.20345](https://arxiv.org/html/2510.20345v1)）把构建归纳为：

| 步骤 | 说明 | 传统 → LLM |
|---|---|---|
| ① 本体/Schema 设计 | 定义实体类型、关系类型 | 人工定义 |
| ② 实体抽取 (NER) | 从文本识别实体/概念 | BiLSTM-CRF → **LLM 结构化输出** |
| ③ 关系抽取 (RE) | 识别实体间关系 | CNN/BERT → **LLM** |
| ④ 实体链接/消歧 | 把同一实体的不同说法合并成一个节点 | embedding + **LLM 裁决** |
| ⑤ 知识融合/增量合并 | 并入已有图谱，不重复建节点 | 增量对齐 |

### 1.3 GraphRAG（两种流派）

[Edge et al., *From Local to Global: A Graph RAG Approach*, Microsoft 2024, arXiv:2404.16130](https://arxiv.org/abs/2404.16130) 提出：普通 RAG 擅长局部检索，但在**全局问题**（"整门课讲了什么"）上失败，需要图谱综合。两种流派：

| 流派 | 做法 | 本项目 |
|---|---|---|
| **局部/遍历式** | 命中概念 → 沿边扩展 1–2 跳 → 邻域喂给 LLM | **P9 采用**（更轻，适合单人项目） |
| **全局/社区式**（微软） | 社区检测(Leiden) + 层次摘要 + map-reduce | 进阶方向，暂不做 |

### 1.4 本项目用的是"精简版"构建

完整工业流水线包含：基于本体 · 众包标注 · 结构化数据本体映射 · 非结构化抽取 · 多方法知识融合。**我们只用其中一个子集**（数据源单一=PDF、方法单一=LLM、单人无众包）：

| 工业步骤 | 我们 | 原因 |
|---|---|---|
| 基于本体 | ✅ | 已定义 concept + 4 关系 |
| 众包标注 | ❌ | 单人；**LLM 代替人工标注** |
| 结构化数据→三元组（本体映射） | ❌ | 无结构化数据源，只有 PDF |
| 非结构化→抽取三元组 | ✅ | Claude 从 PDF 文本抽（单一方法） |
| 实体对齐（知识融合） | ✅ | = 我们的增量消歧合并 |
| 属性对齐 | ⏸️ | 单一来源，暂不需要 |

---

## 2. 关系类型（本项目采用 + 标准对照）

**采用四条纯概念关系**：`is_a` · `prerequisite` · `part_of` · `related`

| relation_type | 含义 | 标准出处 | 用途 |
|---|---|---|---|
| `is_a` | from 是 to 的子类/下位概念 | `rdfs:subClassOf`；[ConceptNet `IsA`](https://github.com/commonsense/conceptnet5/wiki/relations)；WordNet 上下位 | 分层聚类、知识脉络 |
| `prerequisite` | from 是 to 的先修 | ConceptNet `HasPrerequisite`；教育 KG 先修关系研究 | 学习路径拓扑排序 |
| `part_of` | from 是 to 的组成部分 | [SKOS `broader`/`narrower`](https://www.w3.org/TR/skos-reference/)；ConceptNet `PartOf` | 整体-部分（知识点→小考点） |
| `related` | 一般相关/共现 | SKOS `related`；ConceptNet `RelatedTo` | GraphRAG 检索扩展 |

**决策说明**：

- **新增 `is_a`**：教育概念脉络主要靠上下位关系，且它与 `part_of` 语义不同（"NCC **is_a** 线性分类器" ≠ "NCC **part_of** …"）。
- **删除 `equivalent_de`**：它不是概念间关系，而是"同一概念的德语名"，属于 SKOS 的 `altLabel`（标签），不是边。见 §3。
- **暂缓 `互斥`/`因果` 等学科特殊关系**：需领域专家人工精修（盲目 LLM 抽噪声大），留作 backlog。

---

## 3. 概念的语言：统一存德语（源语言）

**决策：概念规范名 `concept.name` 统一存德语（材料源语言），删除 `name_de`，中文/英文在输出时翻译。**

遵循 [SKOS](https://www.w3.org/TR/skos-primer/) 的 `prefLabel`（源语言规范名）+ `altLabel`（其它语言展示）模式——**翻译是展示层的事，不是存储层的事**。理由（从关键到次要）：

1. **实体消歧保真**（硬理由）：概念抽自德语 chunk、靠 `embedding` 相似度去重。存德语 = 消歧全程在**同一语言空间**比对。若存翻译，会出**假合并**（两个德语词翻成同一中文）或**假分裂**（同一词翻得不一致）。
2. **考试相关性**：学生在德国上课，要认/写的是德语术语。
3. **只存"真相"**：翻译有损，别把有损结果当数据存。

落地：`name` = 德语规范术语；`embedding` 基于德语 name 计算；`name_de` 删除；显示用中文由输出层按需翻译（LLM 本就用中文回答）。若图谱可视化节点多、翻译慢，可选加 `display_zh` 缓存列（性能优化，非 schema 必需）。

---

## 4. 概念属性：灵活 JSONB 扩展口

给 `concept` 加 `attributes JSONB nullable`，**不为每种属性建列**。教育图谱的属性分两类：

- **动态属性（难点、易错点）**：不静态存，由 **P10 学习者模型算出**——易错点来自 `quiz_progress` 错题，难点来自 `concept_mastery` 低掌握度。
- **静态学科属性（定义、公式、考点、考纲）**：学科差异大，用 `attributes` 的键值对按需填，避免硬编码锁死 schema。起步可留空，有具体功能需要时再抽。

---

## 5. 抽取方法：LLM 结构化输出（为何不用 pipeline / joint model）

传统监督式深度学习抽取有两条路，**核心权衡是标注数据量**：

| 方式 | 做法 | 数据需求 |
|---|---|---|
| **Pipeline** | 先 NER 抽实体 → 再关系分类，两个独立 DL 模型 | 误差传递；标注数据需求较少 |
| **JointModel** | 实体+关系一个模型同时抽 | 无误差传递；**需大量标注数据** |

两者都要**训练深度学习模型**（BiLSTM-CRF / BERT…），依赖大量人工标注训练集。

**本项目两种都不用**：用 **Claude + 结构化输出 prompt** 一次性抽实体+关系——**不训练、不需要任何标注数据**，效果上等于"joint"却无其数据要求（[综述](https://arxiv.org/html/2510.20345v1)：GPT-3 在开放关系抽取上已接近专家水平）。这是 LLM 抽取适合单人项目的根本原因：我们**根本没有**标注数据去训练传统模型。

---

## 6. 抽取流水线（步骤）

### 6.1 输入
一份 PDF 的切块（`rag.py` 已有的 chunk），带 `pdf_file_id` / `chunk_ids` / `course_id`。

### 6.2 抽取（Claude 结构化输出）
对（一批）chunk 调 Claude，要求输出规范 JSON：

```json
{
  "concepts": [
    {"name": "<德语术语>", "description": "<简述>", "attributes": {}}
  ],
  "relations": [
    {"from": "<德语术语>", "to": "<德语术语>", "type": "is_a|prerequisite|part_of|related"}
  ]
}
```

用 Pydantic + JsonOutputParser 校验（沿用现有 Preview/Quiz 的结构化输出风格）。

### 6.3 概念 embedding（消歧与跨 PDF 的共同基础）
建概念时即算并存 embedding：`get_embedding_function().embed_query(f"{name}: {description}")`（复用 rag.py 的 Ollama nomic-embed-text，768 维，本地免费）→ 存入 `concept.embedding`（JSONB）。§6.4 消歧、§6.5 跨 PDF 关系都读它、用 `numpy` 算余弦（几十~几百概念暴力算毫秒级）。**嵌入用"名+简述"而非仅名字**（短名区分度差）。

### 6.4 实体消歧 + 增量合并（同义词自动合并）
纯 embedding 相似度会**误合并**（`Euklidische Distanz` vs `Manhattan Distanz` 向量也相近；`Batch-Modus` vs `Streaming-Modus` 同理）。所以 **embedding 只负责"缩小候选范围"，Claude 拍板**，三级：

```
对每个抽出的概念：
  ① 精确名匹配（course_id + name）        → 命中已有节点（最快路径）
  ② 否则 embedding 找最相似的已有概念（余弦相似度，越高越像；不是距离）
       ├─ 相似度 ≥ 阈值(SIM_THRESHOLD = 0.70，见 §9 校准) → 收集为"待裁决对"
       └─ 否则                                          → 暂定新建
  ③ 批量问 Claude："这些 (A,B) 概念对，哪些是同一概念?"（一份 PDF 一次调用）
       ├─ 判为同一 → 合并：仅向已有节点 source_refs 追加来源，不建新节点
       └─ 判为不同 → 建新节点（并存其 embedding）
关系的 from/to 都解析到最终 concept_id 后写 concept_edge（去重）。
```

效果：`Euklidische Distanz` / `euklidischer Abstand`（同义、异形）被 Claude 判为同一 → 合并；`Batch/Streaming-Modus` 虽相似但判为不同 → 保留两个节点。图谱随一学期**增量生长**，不全量重建。**批量裁决**（一份 PDF 只 1 次 Claude 调用）控制成本。

### 6.5 跨 PDF 关系推理（让不同讲义的概念连起来）
问题：抽 KNN 时 Claude 看不到 NCC 的概念 → 提不出 NCC↔KNN 的边（现状只能靠"共享概念节点"间接连通）。做法：抽完并合并本 PDF 概念后，加一个**跨 PDF 链接 pass**——不把整门课概念全塞给 Claude，而是**用 embedding 先选邻近的已有概念**，再让 Claude 判关系：

```
本 PDF 的每个概念：
  候选只从【别的 PDF 来源】的已有概念里选（否则单份 PDF 会连自己）
  用 embedding 找 top-K = 5 个最相近的候选
       ↓
把这些"新概念 × 邻近老概念"配对，批量问 Claude（一次调用）:
  "这些概念对之间有关系吗?是哪种(is_a/prerequisite/part_of/related)?
   强关系 (is_a/prerequisite/part_of) 优先；related 仅用于确有强关联的情形，避免宽泛滥用"
       ↓
Claude 返回的边 → 建 concept_edge（跨 PDF），weight = 该对的余弦相似度，去重
```

embedding 选候选的双重作用：① 限制 Claude 上下文（只看相近的，不看全部）② 提高关系质量（相近才可能有关系，减少乱连）。产出如 `K-Nearest Neighbor Klassifikator --related--> Euklidische Distanz`、`Nearest Centroid Klassifikator --is_a--> Linearer Klassifikator` 等跨讲义边。

> **实现细节（易踩的坑）**：候选池必须**排除"本 PDF 自己的概念"**，只从 `source_refs` 不含当前 `pdf_file_id` 的概念里选——首次实现时漏了这条，导致"第一份 PDF"就产出了"跨 PDF 边"（其实是同一份 PDF 内部漏抽的边，被误标记）。修复后首份 PDF 的跨 PDF 新增边应为 0（无候选）。见 §9.2。

> **成本小结**：每份 PDF 现在约 **+2 次 Claude 调用**（§6.4 消歧批量 + §6.5 跨 PDF 批量）+ 若干本地 embedding。可控。

### 6.6 与 P7 视觉的衔接 ⭐
P7 的 `vision_transcribe.py` 在这里**名正言顺复用**：对含公式/图的页，先转写再抽概念（从图/公式里抽"高光""决策边界"等）。**这里没有 P7 的同质化问题**——抽取是"提取实体"，不是"检索排序"（详见 [multimodal-ingestion.md §8.7](./multimodal-ingestion.md)）。

### 6.7 工程落地（已实现）

| 部件 | 实现 |
|---|---|
| **自动化** | `main.py` 的 `process_pdf_background`（chunk 入库后）自动调用 `extract_concepts` → `merge_into_graph` → `link_cross_pdf`，单独 `try/except` 包裹，抽取失败不影响上传本身 |
| **对外接口** | `GET /courses/{course_id}/graph`：鉴权 + 课程归属校验，返回 `{course_id, nodes:[{id,name,description,sources}], edges:[{from,to,type,weight}]}` |
| **前端可视化** | 课程页加「📄 文件列表 / 🕸️ 知识图谱」切换；`GraphAPI.get(courseId)` 取数据，`toMermaid()` 转成 `graph TD` 字符串，复用现成的 `<Mermaid>` 组件渲染；跨 PDF 共享概念（`sources.length>1`）用 `classDef` 标紫色；强关系（is_a/prerequisite/part_of）实线，`related` 虚线且默认隐藏（勾选开关显示） |
| **一次性回填** | `backfill_emb.py`：给建表初期未存 embedding 的历史概念补算向量（`Concept.embedding IS NULL` 幂等） |

---

## 7. 异步化

概念抽取是重活（多次 LLM 调用），接入 **Celery + Redis**（P8 引入），在 PDF 上传后台跑，不阻塞上传响应（沿用现有 `ThreadPoolExecutor` 的异步上传思路）。**当前**：仍跑在 `ThreadPoolExecutor` 后台线程里（同上传处理复用同一线程），尚未接 Celery——量小时够用，PDF/概念量上来后再迁。

---

## 8. 已定决策（最终参数）

- **实体消歧**：三级 = 精确名 → embedding 找候选 → **Claude 批量裁决**（§6.4）。**`SIM_THRESHOLD = 0.70`**（余弦相似度，越高越像；从 0.80 下调，见 §9.1 校准依据）。
- **跨 PDF 关系**：候选**只从别的 PDF 来源**的概念里选、**`top_k = 5`**（从 10 下调，见 §9.2）→ Claude 批量判关系，`weight` 存该对的余弦相似度。
- **`related` 处理**：不删除、不设独立数值阈值，而是①跨 PDF prompt 强化措辞（"优先强关系，related 仅用于确有强关联"）②`top_k` 收紧到 5 从源头减少候选量③前端可视化默认隐藏（弱化为"副分支"，见 §6.7）——多管齐下而非单一硬阈值。
- **embedding**：建概念时算 `"name: description"` 存入 `concept.embedding`（JSONB），Python 原生实现余弦（`_cosine`，不引入 numpy 依赖，规模上毫秒级足够）。
- **存储**：`concept.embedding` 存 **JSONB**（不上 pgvector）；ChromaDB 保留、不合并进 PostgreSQL；详见 [ADR-0005](../adr/0005-vector-storage-jsonb-vs-pgvector.md)。

## 9. 实测与校准结果（NCC + KNN，2026-07-08）

### 9.1 消歧阈值：0.80 → 0.70

初次以 `SIM_THRESHOLD=0.80` 跑 NCC+KNN，抽样检查发现英德跨语言同义词未合并：

```
Nearest Centroid Classifier    (NCC 讲义，英文)   src=[15]
Nearest Centroid Klassifikator (KNN 讲义，德文)   src=[19]   ← 同一概念，未合并
cosine(二者 embedding) = 0.717   < 0.80 → 根本没进入 Claude 裁决环节
```
诊断：不是 Claude 判断错误，是候选筛选阈值把它挡在了裁决门外。下调到 **0.70** 后应能进入裁决（由 Claude 兜底防误合并，而非放宽阈值本身导致误合并）。

### 9.2 跨 PDF 边质量：top-K 10 → 5，候选限定"别的 PDF"

首次实现 `link_cross_pdf` 未限定候选来源，**清空重建后第一份 PDF（NCC，课程里唯一一份）也产出了 16 条"跨 PDF 边"**——诊断为 bug：候选池对全课程概念找最近邻，单 PDF 时最近邻只能是自己，被误标为"跨 PDF"。

修复（候选只从 `source_refs` 不含当前 `pdf_file_id` 的概念里选）后重新验证：

| PDF | 跨 PDF 新增边（修复前） | 跨 PDF 新增边（修复后） |
|---|---|---|
| NCC（课程首份，理论应为 0） | 16 ❌ | **0** ✅ |
| KNN（课程第二份） | 19 | **29** |

同时观察到 `related` 边占比偏高（清空重建、top-K=10 时 55/109 ≈ 50%），是跨 PDF pass 对模糊关联过于宽松。收紧 `top_k=5` + 强化 prompt 措辞后，同一批数据 `related` 占比降至 34/86 ≈ 40%（§8 记录的最终配置）。

### 9.3 消歧合并效果（定性抽查）

清空 course 后用最终参数（0.70 / top-5）重抽 NCC + KNN，概念清单抽查：**多组同义/跨语言概念被正确合并为单节点**（`Euklidische Distanz`、`Linearer Klassifikator`、`Support Vector Machine`、`Machine Learning`、`Perceptron`、`Ridge Regression`、`Logistische Regression`、`Distanzmetrik`、`Entscheidungsgrenze` 等，`source_refs` 含两份 PDF 的 `pdf_file_id`），验证了消歧 + 跨 PDF 流水线端到端可用。

### 9.4 已知局限（待改进，非本轮阻塞项）

- **`prerequisite` 边偏薄**（重抽后仅个位数）——它是 P9 学习路径拓扑排序的骨架，抽取 prompt 后续需针对性加强"先修关系"的挖掘力度。
- **消歧非完全幂等**：同一份 PDF 重复抽取，Claude 的概念命名/关系判定有轻微非确定性（即使 `temperature=0`），重跑不保证 0 新增。
- **关系方向偶尔颠倒**：`prerequisite`/`is_a` 的方向由 LLM 单次判断给出，未做二次校验，留作 backlog。
- **准确性监测尚未系统化**：目前靠人工抽查（如本节案例）。计划：①持续遥测——LangFuse 记录每次抽取/消歧/跨PDF pass 的候选对、裁决结果、汇总统计（概念数/边数/`related`占比/合并数），零标注成本、随时可观察异常；②准确率抽检——参考 P6 评测的 LLM-as-judge 模式，随机采样消歧决策与关系边，让 `opus` 裁判打分，估算误合并率/关系准确率（误合并是最隐蔽、危害最大的失败模式，应优先覆盖）。尚未实现，记入 backlog。

---

## Sources（出处）

- [Singhal, A. (2012). *Introducing the Knowledge Graph: things, not strings.* Google Blog](https://blog.google/products-and-platforms/products/search/introducing-knowledge-graph-things-not/)
- [Hogan, A. et al. (2021). *Knowledge Graphs.* ACM Computing Surveys 54(4). DOI 10.1145/3447772](https://doi.org/10.1145/3447772)
- [*A Comprehensive Survey on Automatic Knowledge Graph Construction.* ACM CSUR (2023). DOI 10.1145/3618295](https://dl.acm.org/doi/10.1145/3618295)
- [*LLM-empowered Knowledge Graph Construction: A Survey.* arXiv:2510.20345](https://arxiv.org/html/2510.20345v1)
- [Edge, D. et al. (2024). *From Local to Global: A Graph RAG Approach to Query-Focused Summarization.* Microsoft. arXiv:2404.16130](https://arxiv.org/abs/2404.16130)
- [ConceptNet 5 Relations](https://github.com/commonsense/conceptnet5/wiki/relations)（关系词表）
- [SKOS Reference, W3C](https://www.w3.org/TR/skos-reference/) · [SKOS Primer](https://www.w3.org/TR/skos-primer/)（多语言标签 prefLabel/altLabel）
