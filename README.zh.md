<div align="center">

# EduPrep

[English](./README.md) · **中文**

**为在德国的国际学生打造的 AI 学习系统。**
不只是一个"能聊 PDF 的工具" —— 它为你的每门课构建**知识图谱**，**追踪你对每个概念的掌握度**，并按遗忘曲线安排你的**预习 → 学习 → 复习**。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Claude](https://img.shields.io/badge/LLM-Claude-D97757)
![Status](https://img.shields.io/badge/status-active%20development-brightgreen)

[演示](#演示) · [产品特色](#产品特色) · [架构](#架构) · [技术栈](#技术栈) · [Roadmap](#roadmap--后续迭代方向) · [文档](./docs)

</div>

---

## 演示

[![Demo Video](https://img.youtube.com/vi/EDPW8Nq5G64/0.jpg)](https://youtu.be/EDPW8Nq5G64)

---

## 产品特色

大多数"AI 学习工具"止步于*对单份文档做检索增强问答*。EduPrep 围绕三个理念，把零散的 PDF 变成**学习者所学知识的动态模型**：

| 理念 | 含义 |
|---|---|
| 🕸️ **知识图谱驱动** | 从每份 PDF 抽取概念，缝合成**课程级知识图谱** —— 带先修、相关、德语术语等价等关系边。第 3 周和第 9 周出现的同一概念是*同一个节点*，而非两个。 |
| 🎯 **自适应与个性化** | 概念级的**学习者模型**根据测验结果追踪你的掌握度。测验优先考你的薄弱点，难度因人而异。 |
| 🔁 **真正闭环的学习循环** | 预习 → 学习 → 复习 不是三个孤立的 tab。每次学习都更新知识图谱与掌握度模型，于是*下一轮*的预习、出题、复习随之改变。 |

> **学习的单位是一门课，而不是一份 PDF。** 一学期下来，EduPrep 把每门课长成一张完整的、标注了你掌握程度的知识地图。

---

## 功能

> 以下功能均已上线。每一项都在按 [roadmap](#roadmap--后续迭代方向) 持续升级 —— 例如知识图谱即将驱动 GraphRAG 检索与学习路径生成（P9），Agent 会随知识追踪（P10）与 MCP（P11）落地而获得更多工具。

### 📖 预习 Preview
上传德语讲义 PDF，自动获得**双语摘要（德语 + 中文）**、带翻译的核心词汇表，以及讲义的 Mermaid 结构图。

### 🕸️ 知识图谱 Knowledge Graph
每次上传 PDF 都会自动触发**概念+关系抽取**（Claude 结构化输出），并入**课程级**知识图谱——概念名统一规范为**德语**（材料源语言），以保证跨 PDF 的实体消歧准确。新概念通过三级匹配并入已有图谱（精确名匹配 → embedding 相似度候选 → Claude 批量裁决），并有第二遍处理把本份 PDF 的概念与**同课程其它 PDF**的概念连起来（`is_a` / `prerequisite` / `part_of` / `related` 边）——这正是让"KNN"讲义自动和更早的"最近质心分类器"讲义连通的机制。课程页有"**文件列表 / 知识图谱**"切换，用 Mermaid 渲染图谱：跨多份 PDF 共享的概念高亮紫色，`related` 边为虚线且默认隐藏。详见 [`concept-extraction-pipeline.md`](./docs/architecture/concept-extraction-pipeline.md)。

### 💬 学习 Learn
用自然语言提问，由 **LangGraph Agent** 回答（`POST /ask/agent`）：一个 Planner→ToolNode→Reflector 循环，自主决定调用哪些工具——`search_pdf`（混合检索：BM25+向量+RRF）、`query_knowledge_graph`（P8 的课程级概念图谱）、`get_concept_mastery`、`search_web`（Tavily）——并在最终确定答案前**自我校验**答案是否真的被工具返回的内容支撑（不通过则重试一次）。每条回答都带来源徽章（`pdf` / `web` / `pdf+web`）及页码/网址。此前的单次决策版 `/ask`（混合 RAG + 一次性 LLM 联网决策，ADR-0003）仍作为独立端点保留。详见 [`agent-orchestration.md`](./docs/architecture/agent-orchestration.md)。

### 📝 测验 Quiz
从讲义生成**个性化**选择题。系统从记忆中读取追踪到的薄弱概念并优先出题。成绩持久化到 PostgreSQL。

---

## 架构

```
React SPA（认证 → 课程 → PDF → 预习 / 学习 / 测验 / 知识图谱）
        |
FastAPI 后端（JWT 保护的端点）
        |
  ┌─────────────┬───────────────────────┬────────────────────────┬─────────────────┐
  |              |                       |                        |
混合 RAG      知识图谱                 LangGraph Agent          记忆系统
流水线        （上传时触发）            （POST /ask/agent）
  ├─ 向量        ├─ 概念+关系抽取         Planner → ToolNode →     ├─ 对话记忆 (PG)
  │ (ChromaDB)   │  (Claude 结构化输出)   Reflector 循环，工具:    └─ 测验进度 (PG)
  ├─ BM25        ├─ 三级消歧             search_pdf ·
  └─ RRF         │  (名称→embedding→     query_knowledge_graph ·
                 │   Claude 裁决)        get_concept_mastery ·
                 └─ 跨 PDF 关系链接      search_web
                    (concept/concept_
                    edge 表)
        |              |                       |
        └──────────────┴───────────────────────┘
                        |
        Claude API (claude-sonnet-4-5) + Ollama（本地嵌入，nomic-embed-text）
                        |
              LangFuse v4（全链路 LLM 调用追踪）
```

此前的单次决策版 `/ask`（混合 RAG + 一次性 LLM 联网决策，ADR-0003）仍作为独立端点与 Agent 并存运行。

📐 详细设计文档见 [`docs/architecture/`](./docs/architecture)，包括 [knowledge-graph-schema.md](./docs/architecture/knowledge-graph-schema.md)、[concept-extraction-pipeline.md](./docs/architecture/concept-extraction-pipeline.md) 和 [agent-orchestration.md](./docs/architecture/agent-orchestration.md)。

---

## 技术栈

| 层 | 当前（已上线） | 规划中（roadmap） |
|---|---|---|
| 前端 | React 18、Vite、TanStack Router + Query、Tailwind + shadcn/ui + 基于 Mermaid 的知识图谱可视化 | 升级为 react-flow / cytoscape.js（可拖拽/缩放的交互式图谱） |
| 后端 | FastAPI、Python 3.11 | Celery + Redis 异步任务 |
| LLM | Claude API — `claude-sonnet-4-5`（Planner/Reflector 也用它） | 模型分层 — `claude-opus-4-8` 主循环 / `claude-sonnet-4-6` 工具（待成本/质量数据支持后再评估） |
| 嵌入 | Ollama — `nomic-embed-text`（本地；chunk 向量和概念向量都用它） | — |
| RAG | LangChain + ChromaDB + BM25 + RRF；语义切割（SemanticChunker） | **GraphRAG**（图谱扩展检索，P9） |
| 知识图谱 | 课程级 `concept`/`concept_edge` 表；Claude 结构化抽取 + 三级消歧 + 跨 PDF 关系链接 | 学习路径生成（按 `prerequisite` 边拓扑排序，P9） |
| Agent | **LangGraph** 编排 — Planner→ToolNode→Reflector 循环（`POST /ask/agent`），4 个工具 | **MCP server**（把工具暴露给 Claude Desktop / Cursor） |
| 学习科学 | 薄弱概念追踪（旧版 `/ask`） | **知识追踪 (BKT)** + **间隔重复 (FSRS)** + 自适应出题（P10） |
| 联网搜索 | Tavily API | — |
| 数据库 | PostgreSQL + SQLAlchemy + Alembic；**7 张原有表 + 4 张知识图谱表** | — |
| 认证 | JWT (python-jose) + bcrypt | — |
| 可观测性 | LangFuse v4 + Loguru | Prometheus + Grafana + Jaeger |
| 评测 | 检索/回答评测套件（[`backend/eval`](./backend/eval)，P6 基线） | Agent 路径的评测（尚无与旧版 `/ask` 的 Recall/Answer 对比数据） |

---

## 快速开始

### 前置依赖
- Python 3.10+ · Node.js 18+ · PostgreSQL · [Ollama](https://ollama.com)

### 1. 拉取嵌入模型
```bash
ollama pull nomic-embed-text
```

### 2. 后端
```bash
cd backend
python -m venv venv
venv\Scripts\activate         # Windows  ·  macOS/Linux 用 source venv/bin/activate
pip install -r requirements.txt
```

创建 `backend/.env`：
```env
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
POSTGRESQL_PASSWORD=your-password
JWT_SECRET_KEY=your-64-char-random-hex
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

初始化数据库（运行一次）并启动服务：
```bash
python init_db.py
uvicorn main:app --reload      # API 文档: http://localhost:8000/docs
```

### 3. 前端
```bash
cd frontend
npm install
npm run dev                    # 应用: http://localhost:5173
```

---

## API 参考

除 `/auth/*` 外所有端点都需要 `Authorization: Bearer <token>` 请求头。

| 方法 | 端点 | 说明 |
|---|---|---|
| POST | `/auth/register` · `/auth/login` · `/auth/refresh` | 账号 + JWT 令牌生命周期 |
| POST/GET/PATCH/DELETE | `/courses` · `/courses/{id}` | 课程 CRUD（按用户隔离 + 所有权校验） |
| POST/DELETE | `/upload` · `/pdfs/{id}` | PDF → 切块 → 嵌入 → ChromaDB；删除 + 清理 |
| POST | `/preview` | 双语摘要 + 词汇 + Mermaid 图 |
| POST | `/ask` | 混合 RAG 问答 + 可选联网补充（单次决策版，ADR-0003） |
| POST | `/ask/agent` | **LangGraph Agent** 问答 —— Planner→ToolNode→Reflector 循环，工具含 search_pdf/query_knowledge_graph/get_concept_mastery/search_web |
| GET | `/courses/{id}/graph` | 课程级知识图谱，返回 `{nodes, edges}`（P8） |
| GET | `/message/{filename}` | 加载对话历史 |
| POST | `/quiz` · `/quiz/result` | 生成个性化测验 · 保存成绩 |
| POST/GET/DELETE | `/notes` · `/notes/{filename}` · `/notes/{id}` | 笔记 CRUD |
| GET | `/me/stats` | 游戏化数据（活跃天数、等级、经验值），从现有数据现算 |

---

## 项目结构

```
eduprep/
├── backend/
│   ├── main.py             # FastAPI 应用 — 所有端点
│   ├── auth.py             # JWT 认证 — 哈希、校验、令牌生成
│   ├── rag.py              # ChromaDB + BM25 混合检索 + RRF
│   ├── pdf_processor.py    # PyPDFLoader + SemanticChunker (percentile 90) + 1100 字符兜底拆分 + overlay 去重 + 页眉页脚剥离
│   ├── page_triage.py      # P7: 廉价逐页信号 → 文字/视觉分诊
│   ├── vision_transcribe.py # P7: 视觉转写（默认关闭 —— 实测对检索净负，见 ADR-0004）
│   ├── memory.py           # 对话记忆 + 测验进度 (PostgreSQL)
│   ├── tools.py            # 普通函数: search_web, generate_mermaid_chart
│   ├── concept_extraction.py # P8: 概念+关系抽取、实体消歧、跨 PDF 关系链接
│   ├── backfill_emb.py     # P8: 一次性脚本 —— 给历史概念补算 embedding
│   ├── agent_graph.py      # P11: LangGraph StateGraph —— Planner → ToolNode → Reflector
│   ├── agent_tools.py      # P11: agent 工具 —— search_pdf, query_knowledge_graph, get_concept_mastery, search_web
│   ├── models.py           # SQLAlchemy ORM — 7 张原有表 + 4 张知识图谱表 (concept, concept_edge, concept_mastery, learning_path)
│   ├── database.py         # PostgreSQL 连接
│   ├── observability.py    # LangFuse + Loguru 初始化
│   ├── eval/               # AI 评测套件（P6 基线 + 持续校准）
│   └── alembic/            # 数据库迁移脚本
├── frontend/src/
│   ├── routes/             # login, register, dashboard, courses（含 文件列表/知识图谱 切换）, workspace
│   ├── lib/                # api.ts (axios + JWT + GraphAPI), auth.tsx, use-auth.ts
│   └── components/         # ui/ (shadcn) + workspace/ (Preview/Learn/Quiz/Notes/Mermaid)
├── docs/
│   ├── architecture/       # knowledge-graph-schema.md、concept-extraction-pipeline.md、agent-orchestration.md、
│   │                       # multimodal-ingestion.md、model-tiering.md、ER 图
│   ├── adr/                # 架构决策记录（0001–0005、0009 —— 详见 docs/adr）
│   ├── evaluation/         # 评测基线 + 基准报告
│   ├── research/           # 用户画像、旅程图、竞品分析
│   ├── roadmap/            # eduprep_roadmap.html（双语交互式路线图）
│   └── blog/               # 技术博客
├── CLAUDE.md
└── README.md
```

---

## 关键设计决策

完整推理记录在 [ADR](./docs/adr) 中。要点：

- **混合检索优于纯向量** —— BM25 能命中语义检索漏掉的德语专业术语；RRF 融合（`Σ 1/(60+rank)`）无需分数归一化即可合并排名。
- **语义切割** —— 切块按 embedding 相似度的转折点断开（SemanticChunker），而非固定字符数，让每块主题更完整；并用 1100 字符兜底拆分限制超长块。
- **LLM 决定是否联网** —— 不再用固定 cosine 阈值，而是让模型通过 Anthropic 工具调用自行判断讲义是否足够、是否需要 Tavily（默认信任讲义，每次最多一次调用）。PDF 与联网回答各自独立标注来源（页码 vs. 网址）。
- **两步式 Preview prompting** —— 摘要 JSON 与 Mermaid 图分开生成，避免格式冲突。
- **课程级知识层** —— 概念/掌握度建模在课程级（而非单份 PDF），因为学习的真实单位跨越多份文档。详见 [knowledge-graph-schema.md](./docs/architecture/knowledge-graph-schema.md)。
- **概念名统一存德语（源语言）** —— 建库时规范为德语、不做翻译，翻译只在输出/展示时进行，这样才能保证实体消歧和跨 PDF 匹配的准确性。关系类型为 `is_a` / `prerequisite` / `part_of` / `related`，对照了 SKOS/ConceptNet/RDFS 的标准约定。详见 [concept-extraction-pipeline.md](./docs/architecture/concept-extraction-pipeline.md)。
- **三级实体消歧** —— 精确名匹配 → embedding 相似度候选 → Claude 批量裁决（单靠 embedding 会把"欧氏距离" vs "曼哈顿距离"这类相关但不同的概念误合并）。跨 PDF 关系链接的第二遍处理只从**其它 PDF 来源**的概念里选候选（曾有个 bug 没做这个限制，导致课程首份 PDF 错误地和自己建立"跨 PDF"链接——已在校准阶段发现并修复）。
- **本地嵌入** —— Ollama 本地运行；只有 LLM 推理和联网搜索会离开本机。
- **视觉转写在检索上被否决** —— P7 实测发现整页视觉转写反而*伤害*检索（让语料同质化，把真正相关的页挤出结果），默认关闭上线，页眉/页脚剥离是唯一真实见效的部分。详见 [ADR-0004](./docs/adr/0004-multimodal-ingestion-vision-llm.md)。
- **概念 embedding 存储** —— 课程级概念向量存 PostgreSQL 的 JSONB、用纯 Python 算余弦相似度，而非 pgvector；ChromaDB（chunk 向量）暂时独立保留。详见 [ADR-0005](./docs/adr/0005-vector-storage-jsonb-vs-pgvector.md)。
- **用 LangGraph 编排 Agent** —— 当工具数达到 4+ 个、且需要"答案不合格就重试"时，一张 Planner→ToolNode→Reflector 的图取代了零散的工具决策代码；图的条件边本身就是 orchestrator。详见 [ADR-0009](./docs/adr/0009-langgraph-vs-custom-loop.md)。

---

## Roadmap — 后续迭代方向

EduPrep 处于**持续、迭代式开发**中。从"RAG 聊天应用"到"知识图谱驱动的自适应学习系统"，这条路被拆成若干聚焦的阶段 —— 每个阶段都交付可用功能**和**对应文档。

| 阶段 | 范围 | 状态 |
|---|---|---|
| P1–P3 | 工具层 · 混合 RAG · PostgreSQL · 课程/PDF 管理 · LangFuse 可观测性 | ✅ 完成 |
| P4–P5 | JWT 认证 · 记忆系统 · 个性化测验 · TanStack Router + shadcn/ui 重构 | ✅ 完成 |
| **P6** | 评测基线（[评测套件](./backend/eval) + [黄金数据集](./backend/eval/datasets/golden_qa.jsonl) + [方法论](./docs/evaluation/methodology.md) + [基线](./docs/evaluation/baseline.md)）· 文档地基 | ✅ 完成 |
| **P7** | **Vision-LLM 多模态 ingestion** —— 读懂纯文字抽取丢失的公式 / 图解 / 图片 / 表格 | ✅ 完成 |
| **P8** | **知识图谱**构建 + 可视化（课程级概念网络） | ✅ 完成 |
| **P9** | **GraphRAG** 检索 + 学习路径生成 | 📋 规划 |
| **P10** | **学习科学引擎** —— 知识追踪 (BKT) + 间隔重复 (FSRS) + 自适应出题 | 📋 规划 |
| **P11** | **Agent + Tools + MCP** —— LangGraph 编排（[`agent-orchestration.md`](./docs/architecture/agent-orchestration.md)），EduPrep 作为 MCP server | 🚧 Agent 循环已完成，MCP 待做 |
| P12 | 加固：可靠性 / 安全 / **治理**（Redis 缓存、限流、熔断器；模型/prompt 版本管理、回滚、GDPR） | 📋 规划 |
| P13 | 测试 · Docker · CI/CD（含 **eval 回归门禁**）· Prometheus + Grafana + Jaeger | 📋 规划 |

📍 **完整的双语交互式路线图：** [`docs/roadmap/eduprep_roadmap.html`](./docs/roadmap/eduprep_roadmap.html)

---

## 文档

| 领域 | 位置 |
|---|---|
| 架构与 Schema | [`docs/architecture/`](./docs/architecture) |
| 架构决策记录 | [`docs/adr/`](./docs/adr) |
| 评测与基准 | [`docs/evaluation/`](./docs/evaluation) |
| 用户研究 | [`docs/research/`](./docs/research) |
| 路线图 | [`docs/roadmap/`](./docs/roadmap) |
| 技术博客 | [`docs/blog/`](./docs/blog) |

---

## 贡献

欢迎贡献。安全问题请按 [`SECURITY.md`](./SECURITY.md) 报告。

## 许可证

[MIT](./LICENSE)
