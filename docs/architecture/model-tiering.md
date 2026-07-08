# 模型分层策略 (Model Tiering Strategy)

> **状态**: Living doc（随功能演进更新）
> **更新**: 2026-07-07
> **关联**: [concept-extraction-pipeline.md](./concept-extraction-pipeline.md)（消歧/跨PDF 的本地+云端混用）· [multimodal-ingestion.md](./multimodal-ingestion.md)（§3 成本模型）
> **代码**: `rag.py` `get_embedding_function()` · `main.py`（各 Claude 端点）· `concept_extraction.py` · `vision_transcribe.py`

---

## 1. 为什么要分层（工程动机）

最省事的做法是"所有任务都用最强的模型"。但这在工程上是**反模式**:又贵、又慢、还浪费。

核心工程思想:**把「任务真正需要的能力」和「模型的成本/能力」匹配起来**,而不是无脑上最强。一个 768 维向量的相似度计算,不需要 GPT/Claude 级别的推理;而一段多步骤的答案生成,小的本地模型又做不了。**分层 = 让每个任务用"刚好够用、且最便宜"的那一档。**

一个反面直觉:用最强模型 `opus` 去算 embedding,等于把最贵、最需要智力的资源,用在了最不需要智力、却调用最频繁的地方——成本爆炸,收益为零。

---

## 2. 定级的四个判断维度

给任何一个任务定"用哪档模型",看四点:

| 维度 | 问什么 | 越"高"越该往低档压 |
|---|---|---|
| **能力需求** | 是数值化 / 抽取 / 还是多步推理? | 数值化、简单抽取 → 低档 |
| **调用量** | 每次请求调几次?ingestion 时调几百次? | 高频 → 低档(否则成本随量爆炸) |
| **成本** | 本地免费,还是云端按 token 收费? | 能压到本地就本地 |
| **延迟 / 隐私** | 要不要网络往返?数据能不能出本机? | 要快、要隐私 → 本地 |

**一句话启发式**:**高频 + 简单 → 越便宜/本地越好;低频 + 需要智力 → 才上强模型。**

---

## 3. 本项目的分层现状

| Tier | 模型 | 性质 | 用在哪 | 为什么这一档 |
|---|---|---|---|---|
| **T0 本地嵌入** | Ollama `nomic-embed-text` | **本地 / 免费 / 高频** | ① chunk 向量(RAG 检索,每次检索算 query 向量、ingestion 每个 chunk 算一次)② 概念向量(消歧、跨PDF 候选选择) | 调用量极大 + 任务是"数值化"不需推理 + 数据不出本机 |
| **T1 云端生成/抽取** | Claude `sonnet-4-5` | **云端 / 付费** | `/ask` 答案、web 决策、web 补充、Preview、Quiz、概念抽取、消歧裁决、跨PDF 关系推理、视觉转写(默认关) | 需要真正的语言理解 / 生成 / 结构化输出,本地小模型做不了 |
| **T2 强推理** | Claude `opus-4-8` | **云端 / 更贵** | 现状:**评测的 LLM-judge**(打分要更严谨、少偏差) | 需要最高质量的判断;低频(只在评测时) |

> 外部服务:**Tavily**(web 搜索,付费 API,`/ask` 里 LLM 决策后才调)。

**当前实质是"两档为主"**:T0 本地嵌入 + T1 sonnet 干几乎所有云端活;T2 opus 只在评测当裁判。T2 在业务侧的铺开留到 P11(见 §6)。

---

## 4. 免费 vs 花钱(实操速查)

开发时想知道"这行代码花不花钱",看它调的是谁:

| 操作 | 走哪 | 花钱? |
|---|---|---|
| `get_embedding_function()` / `OllamaEmbeddings` / `.embed_query()` | 本地 Ollama | **免费** |
| chunk 检索的向量部分、BM25、RRF | 本地 | **免费** |
| `anthropic.Anthropic(...).messages.create(...)` / `claude.messages.create` | Claude 云端 | **花钱**(按 token) |
| `search_web` / Tavily | 外部 API | **花钱** |

**记忆法**:`Ollama` = 免费本地;`anthropic` / `Tavily` = 花钱云端。

---

## 5. 已经在用的分层实践(举例)

分层不是空谈,项目里已经这么做:

- **概念消歧**([concept-extraction-pipeline.md §6.4](./concept-extraction-pipeline.md)):**本地 embedding(免费)先缩小候选** → **Claude(付费)只裁决少数候选对**。典型的"便宜的多做、贵的少做"。
- **跨 PDF 关系**(§6.5):embedding 选 top-K 邻近概念 → Claude 只判这些邻近对,不把整门课丢给它。
- **P7 视觉转写默认关**([multimodal-ingestion.md §8](./multimodal-ingestion.md)):不是能力不够,是**实测 ROI 不划算**——"不该花的钱不花"同样是分层思想的一部分。

---

## 6. 演进方向 (P11 — Agent)

roadmap P11 会把分层做成真正的三档:

- **T2 `opus` 作为 Agent 主循环**(Planner / Reflector,负责决策);
- **工具内部的抽取 / 分类降到 `sonnet` 或 `haiku`**(负责执行);
- 原则:**贵模型管决策,便宜模型管执行**。

> 这也呼应 roadmap 里 "主循环 opus,工具抽取 sonnet" 的模型分层设计。

---

## 7. 一条铁律

**把模型能力当成"预算"来分配:默认不是"上最强",而是"够用就好,能本地就本地"。**

- 高频 / 简单 → 往 T0 本地压(embedding、相似度);
- 低频 / 需要智力 → 才上 T1/T2 云端(生成、裁决、最终答案);
- 每加一个新功能,先问自己:**这活儿真需要最强模型吗?能不能用便宜的先筛、贵的只收尾?**

成本细算见 [multimodal-ingestion.md §3](./multimodal-ingestion.md)。
