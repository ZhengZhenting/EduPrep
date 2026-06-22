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

> 以下功能均已上线。每一项都在按 [roadmap](#roadmap--后续迭代方向) 持续升级 —— 例如 Preview 的思维导图正在演进为完整的知识图谱，Learn 正在升级为 Agent。

### 📖 预习 Preview
上传德语讲义 PDF，自动获得**双语摘要（德语 + 中文）**、带翻译的核心词汇表，以及讲义的 Mermaid 结构图。

### 💬 学习 Learn
用自然语言提问。回答通过**混合 RAG 检索**（BM25 + 向量 + RRF 融合）锚定在 PDF 内容上。**由 LLM 自己判断**（通过 Anthropic 工具调用）讲义是否足够、是否需要 **Tavily 实时联网搜索** —— 一旦联网，PDF 回答（带页码）与联网补充（带来源网址）会**分成两部分、各自标注来源**（`pdf` / `pdf+web`）。对话历史按 PDF 压缩并持久化。

### 📝 测验 Quiz
从讲义生成**个性化**选择题。系统从记忆中读取追踪到的薄弱概念并优先出题。成绩持久化到 PostgreSQL。

---

## 架构

```
React SPA（认证 → 课程 → PDF → 预习 / 学习 / 测验）
        |
FastAPI 后端（JWT 保护的端点）
        |
  ┌─────┴──────────────────────┐
  |                            |
混合 RAG 流水线              记忆系统
  ├─ 向量检索 (ChromaDB)       ├─ 对话记忆 (PostgreSQL)
  ├─ BM25 关键词检索           └─ 测验进度 (PostgreSQL)
  └─ RRF 融合
        |
  Claude API（始终生成 PDF 回答）
        |
  LLM 工具调用决策（Anthropic tool_choice=auto）
  ├─ 讲义足够 → 仅 PDF 回答
  └─ 不足 → Tavily 搜索 → Claude API（独立的联网补充）
        |
  LangFuse v4（全链路 LLM 调用追踪）
```

📐 详细设计文档见 [`docs/architecture/`](./docs/architecture)，含即将落地的[知识图谱 Schema](./docs/architecture/knowledge-graph-schema.md)。

---

## 技术栈

| 层 | 当前（已上线） | 规划中（roadmap） |
|---|---|---|
| 前端 | React 18、Vite、TanStack Router + Query、Tailwind + shadcn/ui | 知识图谱可视化（react-flow / cytoscape.js） |
| 后端 | FastAPI、Python 3.11 | Celery + Redis 异步任务 |
| LLM | Claude API — `claude-sonnet-4-5` | 模型分层 — `claude-opus-4-8`（Agent）/ `claude-sonnet-4-6`（工具） |
| 嵌入 | Ollama — `nomic-embed-text`（本地） | — |
| RAG | LangChain + ChromaDB + BM25 + RRF；语义切割（SemanticChunker） | **GraphRAG**（图谱扩展检索） |
| Agent | 普通工具函数 | **LangGraph** 编排 + **MCP server** |
| 学习科学 | 薄弱概念追踪 | **知识追踪 (BKT)** + **间隔重复 (FSRS)** + 自适应出题 |
| 联网搜索 | Tavily API | — |
| 数据库 | PostgreSQL + SQLAlchemy + Alembic | 课程级概念图谱表 |
| 认证 | JWT (python-jose) + bcrypt | — |
| 可观测性 | LangFuse v4 + Loguru | Prometheus + Grafana + Jaeger |
| 评测 | — | 黄金数据集 + 检索/回答指标 |

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
| POST | `/ask` | 混合 RAG 问答 + 可选联网补充 |
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
│   ├── pdf_processor.py    # PyPDFLoader + SemanticChunker (percentile 90) + 1100 字符兜底拆分
│   ├── memory.py           # 对话记忆 + 测验进度 (PostgreSQL)
│   ├── tools.py            # 普通函数: search_web, generate_mermaid_chart
│   ├── models.py           # SQLAlchemy ORM — 7 张表（+ 规划中的知识图谱表）
│   ├── database.py         # PostgreSQL 连接
│   ├── observability.py    # LangFuse + Loguru 初始化
│   ├── eval/               # AI 评测套件（规划 P6）
│   └── alembic/            # 数据库迁移脚本
├── frontend/src/
│   ├── routes/             # login, register, dashboard, courses, workspace
│   ├── lib/                # api.ts (axios + JWT), auth.tsx, use-auth.ts
│   └── components/         # ui/ (shadcn) + workspace/ (Preview/Learn/Quiz/Notes/Mermaid)
├── docs/
│   ├── architecture/       # knowledge-graph-schema.md、ER 图、设计文档
│   ├── adr/                # 架构决策记录 (Architecture Decision Records)
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
- **本地嵌入** —— Ollama 本地运行；只有 LLM 推理和联网搜索会离开本机。

---

## Roadmap — 后续迭代方向

EduPrep 处于**持续、迭代式开发**中。从"RAG 聊天应用"到"知识图谱驱动的自适应学习系统"，这条路被拆成若干聚焦的阶段 —— 每个阶段都交付可用功能**和**对应文档。

| 阶段 | 范围 | 状态 |
|---|---|---|
| P1–P3 | 工具层 · 混合 RAG · PostgreSQL · 课程/PDF 管理 · LangFuse 可观测性 | ✅ 完成 |
| P4–P5 | JWT 认证 · 记忆系统 · 个性化测验 · TanStack Router + shadcn/ui 重构 | ✅ 完成 |
| **P6** | 评测基线（黄金数据集 + 指标）· 文档地基 | 🔜 下一步 |
| **P7** | **知识图谱**构建 + 可视化（课程级概念网络） | 📋 规划 |
| **P8** | **GraphRAG** 检索 + 学习路径生成 | 📋 规划 |
| **P9** | **学习科学引擎** —— 知识追踪 (BKT) + 间隔重复 (FSRS) + 自适应出题 | 📋 规划 |
| **P10** | **Agent + Tools + MCP** —— LangGraph 编排，EduPrep 作为 MCP server | 📋 规划 |
| P11 | 性能 / 可靠性 / 安全加固（Redis 缓存、限流、熔断器） | 📋 规划 |
| P12 | 测试 · Docker · CI/CD · Prometheus + Grafana + Jaeger | 📋 规划 |

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
