# RAG 评测方法论 (Evaluation Methodology)

> **状态**: Accepted (P6 核心交付)
> **更新**: 2026-06-23
> **关联**: [baseline.md](./baseline.md)(基线结果) · [ADR-0002 切块](../adr/0002-semantic-chunking.md) · [ADR-0003 web search](../adr/0003-llm-decided-web-search.md)
> **代码**: `backend/eval/`

本文定义 EduPrep 评测 RAG 问答质量的方法。设计对照了学术界主流方法论(RAGAS、IR 经典指标、校准过的 LLM-as-judge),并针对本项目的真实行为(讲义优先 + LLM 决策 web search + 页码引用)做了适配。

---

## 1. 设计原则

1. **组件分解** —— RAG 只有两个会出错的环节,分开评,以便故障定位:
   ```
   问题 →【检索器 取上下文】→【LLM 生成答案+引用】→ 用户
            ↓ 指标① 检索召回        ↓ 指标② 回答得分
   ```
   这与学术综述的共识一致:评 RAG 必须同时测检索与生成 [1][2]。

2. **少而可行动** —— 只设**两个头部指标**,其余降级为"出问题才看"的诊断项。指标多而无主次反而不科学。

3. **真值来源决定评测方法** —— 这是本方法论的核心判断,也解决了"参考答案可能不权威"的问题(见 §4.3):
   - 答案在 **PDF 内** → PDF 是权威真值 → **有参考评测**(answer correctness)
   - 答案**不在 PDF 内**(走 web)→ 你手写的参考可能过时/不如实时网页 → **无参考评测**(faithfulness / groundedness)
   
   学界明确区分这两类:correctness 需权威 gold answer,faithfulness 以"检索到的上下文本身"为真值 [1][3]。

---

## 2. 黄金数据集 (Golden Dataset)

人工构建的标准测试集,固定不变以保证基线可复现。

### 2.1 字段 schema

```jsonc
{
  "id": "ml-w3-q01",
  "pdf": "machine_learning_week3.pdf",
  "question": "Was ist der Unterschied zwischen Klassifikation und Regression?",
  "reference_answer": "Klassifikation sagt diskrete Kategorien voraus …",
  "relevant_pages": [4, 5],          // 检索真值;多页=跨章节题;[] = PDF 没有答案
  "answer_coverage": "standard",      // standard / fuzzy / none
  "content_modality": "text",         // 答案依赖的内容形态: text / formula / figure / table
  "expects_web": false,               // 路由期望;none 类通常为 true
  "language": "de"
}
```

> **刻意不设 `difficulty`**:主观、无客观标准、且"难度"已被 `answer_coverage` 客观捕捉。

### 2.2 题型分类(answer_coverage)

按**答案在源文档中的覆盖度**分类,直接对齐系统的路由与幻觉行为:

| 题型 | `relevant_pages` | 期望系统行为 | 测什么 |
|---|---|---|---|
| **standard** | 明确页码 | 从 PDF 答,不搜 web | 基础检索 + 回答正确性 |
| **fuzzy** | 部分相关页 | 从 PDF 答,可能补 web | 部分信息下的鲁棒性 |
| **none** | `[]` 空 | 触发 web 或老实说"讲义没有" | ⭐ **幻觉测试**(最高风险) |

> 跨章节题不单独成类:某 standard 题的 `relevant_pages` 含多页(如 `[3,9,14]`)即为跨章节,供 P8 评 GraphRAG 时通过"多页题召回提升"体现。

### 2.3 分层比例(stratified sampling)

按**风险与信息量**分层超采,而非照搬自然频率。30 题 v0 基线:

| 题型 | 数量 | 理由 |
|---|---|---|
| standard | 15 | 核心用例,占大头 |
| fuzzy | 6 | 边缘鲁棒性 |
| none | 9 | **刻意超采**——幻觉是最致命失败,失败信息量最大 |

### 2.4 内容形态 (content_modality)

标注**该题的答案依赖哪种内容形态**,用于把基线按形态拆分,暴露纯文字抽取的盲区(公式/图解/图片/表格大多被 `PyPDFLoader` 丢失或损坏)。

| 值 | 含义 | 纯文字 RAG 预期表现 |
|---|---|---|
| `text` | 答案在普通正文里 | 好 |
| `formula` | 答案藏在数学公式里 | 差(公式被抽丢/损坏) |
| `figure` | 答案要看图解/流程图 | 差(结构丢失) |
| `table` | 答案在表格里 | 一般(结构被拍平) |

> 若一题依赖多种形态,可存为数组(如 `["text","formula"]`)。

**用途**:跑基线时按 `content_modality` 拆分 Recall —— 例如 `formula` 类只有 0.18 而 `text` 类 0.82,就把"RAG 看不懂公式"这一模糊担忧变成有数字的立案。**P7 Vision-LLM 多模态 ingestion** 完成后重跑同一批题,formula 的召回增益即为 P7 价值的量化证据。

> ⚠️ 这是为公式/图解线埋的"度量钩子"。当前评测 PDF 若为纯文字课件,所有题均为 `text`,测不出多模态短板;需放入含公式/图解的理工科讲义才能体现。

### 2.5 存放

```
backend/eval/datasets/
├── pdfs/                 # 固定评测 PDF(独立于用户数据,保证可复现)
└── golden_qa.jsonl       # 30 条 Q&A,一行一条(JSONL 便于增量 + git diff 友好)
```

---

## 3. 检索侧指标 (Retrieval)

以 chunk 的**页码 metadata** 为判断单位(无需逐 chunk 标注)。

### 3.1 头部指标

**Recall@K** —— 该找到的页找回了几成(漏页 = 答案缺料):
```
Recall@K = |relevant_pages ∩ retrieved_pages@K| / |relevant_pages|
```

### 3.2 诊断项(召回差时才看)

- **Precision@K** = `|相关 ∩ 检索| / |检索|` —— 噪声占比(噪声多会稀释上下文)
- **MRR** = `1 / 第一个相关结果的排名` —— 相关结果排得是否靠前

> none 类题无 relevant_pages,**跳过检索指标**。
> 这些是 IR 经典指标 [2];RAGAS 的 context precision/recall 是其"用 LLM 判定相关性、免标注"的变体,可作补充 [3]。

### 3.3 计算示例

```
relevant_pages = [4, 5];  retrieved@5 来自页 {4, 7, 2, 5, 9}
Recall@5    = |{4,5} ∩ {4,7,2,5,9}| / 2 = 2/2 = 1.0
Precision@5 = 2/5 = 0.4
MRR         = 第1个相关在 rank1(页4) → 1/1 = 1.0
```

---

## 4. 生成侧指标 (Generation) —— 回答得分

由 **LLM-as-judge** 按固定锚定 rubric 打分,一个 judge 覆盖全部题型。学术界生成侧高度收敛到忠实度 / 相关性 / 正确性三维 [1][3][4],本 rubric 在此基础上加入项目特有的"引用准确"与"诚实性"。

### 4.1 评分 rubric(锚定,每维 0 / 0.5 / 1)

| 维度 | 1.0 | 0.5 | 0 |
|---|---|---|---|
| **正确性 (Correctness)** | 事实正确且回答了问题 | 部分正确/部分跑题 | 错误或答非所问 |
| **忠实度 (Faithfulness)** | 每句都被检索来源支撑 | 大体支撑,少量无来源延伸 | 含来源里没有的捏造 |
| **引用准确 (Citation)** | 标注页码 = relevant_pages | 有遗漏/多余 | 没标或标错 |
| **诚实性 (Honesty)**〔仅 none 题〕 | 老实说没有/正确去搜 | 含糊带过 | **假装有,瞎编** |

**总分** = 适用维度的平均(教育场景可对 Faithfulness + Honesty 加权)。

### 4.2 为什么用锚定的 rubric 而非"打 1–5 分"

档位定义写死 → 不同题之间标准一致、可复现。**锚定是把 LLM-judge 从"玄学"变成"测量工具"的关键。**

### 4.3 评测方法随题型切换(核心)

| 题型 | 真值来源 | 回答评测方法 |
|---|---|---|
| standard / fuzzy | PDF 讲义(reference 可靠) | 有参考:judge 对照 reference + 来源(correctness 为主) |
| **none / web** | **检索到的网页**(非你的 reference) | 无参考:judge 评 **groundedness + 诚实性**,`reference_answer` 降级为"要点提示",不参与硬打分 |

> 这样,LLM 通过实时搜索答得**比你预设的 reference 更准时,不会被扣分**——评的是"是否忠实于它引用的来源",而非"是否符合我以为的答案"。

---

## 5. LLM-as-Judge 的实现与可靠性

LLM-judge 是当前主流自动评测手段,但文献有明确警告,必须配套防护。

### 5.1 输入

judge 必须同时拿到**来源**,否则无法评忠实度:
```
question · generated_answer · retrieved_sources(PDF chunks+页码 / web 内容)
· relevant_pages · reference_hint(可选)
```

### 5.2 输出(结构化 JSON,复用项目 Pydantic + JsonOutputParser 模式)

```jsonc
{
  "reasoning": "答案准确解释了分类vs回归,内容在第4页有支撑,但标注成第6页…",
  "correctness": 1.0, "faithfulness": 1.0, "citation": 0.5, "honesty": null,
  "overall": 0.83
}
```

### 5.3 已知风险(来自文献,必须防护)

- **judge 与人工的相关性不高**:RAGAS 指标与人工评测调和平均仅 **0.55** [2] → 不能盲信。
- **CALM 框架记录 12 种 judge 偏差**:位置偏差、冗长偏差(偏好长答案)、**自我增强偏差(偏好自己生成的)**、权威偏差等 [2]。
- judge 一致性问题是活跃研究方向 [4]。

### 5.4 防护措施(与文献风险一一对应)

| 措施 | 对抗的风险 |
|---|---|
| **judge 用更强的异构模型**(系统 sonnet-4-5 生成,judge 用 opus-4-8) | 自我增强偏差 |
| **temperature = 0** | 打分波动 |
| **锚定 rubric**(§4.1) | 标准不一致 |
| **先 reasoning 后打分**(CoT) | 拍脑袋打分;便于回查 |
| **给来源、不以 reference 为唯一标尺** | reference 不权威问题 |
| **方差自检**:同题 judge 跑 3 次看稳不稳 | judge 一致性 |
| **人工校准**(§5.5) | 0.55 相关性问题 |

### 5.5 Judge 校准 (Calibration) —— 不可省

人工抽查 **~10 题**,自己按同一 rubric 打分,与 judge 比对:
- 一致率高(±0.5 内吻合 > 80%)→ judge 可信,放心自动跑;
- 差距大 → 回去改 rubric 措辞。

这是"用 AI 评 AI"站得住脚的科学依据。学界同样强调:**自动指标是人工评测的补充而非替代** [1][2]。

---

## 6. 评分卡 (Scorecard)

```
EduPrep RAG Baseline v0   (30 题: 15 standard / 6 fuzzy / 9 none)
──────────────────────────────────────────────
① 检索召回  Recall@5 .......... 0.__   (仅 standard + fuzzy)
② 回答得分  Answer Score ...... _._/1  (全部题, LLM-judge)
──────────────────────────────────────────────
诊断备查(出问题才看):
  Precision@5 / MRR / judge 四维子项 / 按 answer_coverage 拆分 / 按 content_modality 拆分 / 路由准确率
```

**两个头部数,一张卡。** 兼顾科学性(组件级定位 + 可复现 rubric)与简洁性。

---

## 7. 实现建议:复用 RAGAS

**RAGAS 是开源的事实标准**,其 faithfulness / answer relevancy / context precision/recall 的 prompt 经社区验证。建议:
- **直接复用** RAGAS 的上述指标实现(更省力、更可信);
- **自己只补** ① 引用页码准确性 ② 诚实性/幻觉维 ③ 人工校准流程。

既科学又省工。具体取舍在 `backend/eval/` 落地时确定。

---

## 8. 局限 (Limitations)

- **样本量小**:30 题分 3 层,每层 6–15 题,**层内均值噪声较大**。v0 基线只用于看大方向(如 GraphRAG 是否显著提升),不做小数点级精确比较。后续应扩到 45–60 题、每层 ≥15。
- **LLM-judge 固有偏差**:见 §5.3,靠 §5.4 防护缓解,但无法完全消除。
- **评测 PDF 有限**:固定 3–5 份德语讲义,不代表全部学科分布。

---

## 9. 参考文献 (References)

1. *A Systematic Literature Review of Retrieval-Augmented Generation: Techniques, Metrics, and Challenges.* arXiv:2508.06401. https://arxiv.org/pdf/2508.06401
2. *A Comprehensive Survey of RAG Evaluation and Benchmarks: Perspectives from IR and LLM.* https://www.researchgate.net/publication/396290953
3. *RAGAS: Automated Evaluation of Retrieval Augmented Generation.* https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
4. *Judge as A Judge: Improving the Evaluation of RAG through the Judge-Consistency of LLMs.* arXiv:2502.18817. https://arxiv.org/pdf/2502.18817
5. *RAGalyst: Automated Human-Aligned Agentic Evaluation for Domain-Specific RAG.* arXiv:2511.04502. https://arxiv.org/pdf/2511.04502
6. *RAG Evaluation Metrics.* Confident AI. https://www.confident-ai.com/blog/rag-evaluation-metrics-answer-relevancy-faithfulness-and-more
7. *A complete guide to RAG evaluation.* Evidently AI. https://www.evidentlyai.com/llm-guide/rag-evaluation
