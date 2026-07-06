# Vision-LLM 多模态 Ingestion 设计

> **状态**: **Implemented → Reversed（实测净负，默认关闭）** — 结论见 §8
> **更新**: 2026-06-24 设计 · 2026-07-07 实测并否决
> **关联**: [knowledge-graph-schema.md](./knowledge-graph-schema.md) · [methodology.md](../evaluation/methodology.md)(content_modality)· [ADR-0004](../adr/0004-multimodal-ingestion-vision-llm.md)(Vision-LLM vs Nougat/DeepDoc)
> **代码**: `backend/page_triage.py` · `backend/vision_transcribe.py` · `backend/pdf_processor.py` · `backend/eval/`(量化验证)

> ⚠️ **先读 §8**：下面 §1–§7 是**规划期**的设计与成本预期。P7 实现后的**实测证明该方案在讲义幻灯片上净负**，已默认关闭。§8 记录了实际实现、实测数据与根因。

---

## 1. 背景与问题

现有 ingestion 用 `PyPDFLoader` 只抽取 PDF 的**文字层**,公式、图解、图片、表格大多丢失或损坏(详见 P6 baseline 的 content_modality 拆分预期)。德语理工科讲义恰恰满是这些内容,这是检索质量的**隐形天花板**。

| 内容类型 | 纯文字抽取表现 |
|---|---|
| 普通正文 | ✅ 好 |
| 数学公式 | ❌ 差(渲染成图片则完全丢失;文字层则上下标/符号错乱) |
| 图解/流程图 | ❌ 差(标签或可抽,结构/箭头全丢) |
| 图片/照片 | ❌ 几乎为零 |
| 表格 | ⚠️ 一般(结构被拍平) |

---

## 2. 方案:Vision-LLM 逐页转写

把每页 PDF **渲染成图片**,用 **Claude 视觉能力**把非文本内容转写成文本,与原文一起切块入库。

```
PDF → 逐页渲染图片 → Vision-LLM 转写(公式→LaTeX / 图解→文字描述 / 表格→结构化)
    → 转写文本 ∪ 原文字层 → SemanticChunker 切块 → embed → ChromaDB
```

**转写目标**:
- 公式 → LaTeX(`$E = mc^2$`)
- 图解/流程图 → 文字描述(节点 + 关系)
- 图片 → 内容描述
- 表格 → Markdown 结构化

**为什么选 Vision-LLM 而非 Nougat/DeepDoc**(详见 ADR-0004):已有 Claude 视觉访问、无重依赖、一次预处理即可;Nougat(公式专长)/ RagFlow DeepDoc(版面分析)作为远期备选。

---

## 3. 成本模型(关键)

### 3.1 视觉 token 计算

Anthropic 图片 token 公式:**tokens ≈ (宽 px × 高 px) / 750**。
- **标准分辨率**(≤ ~1.15MP):每页图 **约 1,600 token 封顶** —— 讲义转写用这个即可。
- 高分辨率(2576px,Opus 4.7+):满分辨率可达 ~4,784 token/页(~3×),**本场景不需要**。

### 3.2 单页成本

| 项 | token |
|---|---|
| 页面图(标准分辨率) | ~1,600 |
| 转写 prompt | ~150 |
| **单页输入合计** | **~1,750** |
| 转写输出(文本) | ~300 |

### 3.3 模型定价(每百万 token,2026-06)

| 模型 | 输入 | 输出 |
|---|---|---|
| **Haiku 4.5** | $1.00 | $5.00 |
| Sonnet 4.6 | $3.00 | $15.00 |
| Opus 4.8 | $5.00 | $25.00 |

### 3.4 一份 44 页 PDF 的一次性成本

输入 ≈ 77,000 token · 输出 ≈ 13,200 token:

| 转写模型 | 一次性成本 / 44 页 |
|---|---|
| **Haiku 4.5(推荐)** | **≈ $0.14** |
| Sonnet 4.6 | ≈ $0.43 |

### 3.5 为什么这点成本可接受

1. **一次性**:转写在 **ingestion 阶段**做一次,入库后永久复用。后续问答/预习/出题查的是已转写文本,**查询成本完全不变**。
2. **摊薄趋近于零**:一份 PDF 一学期被查几十上百次,$0.14 摊下来微不足道。
3. **对比代价**:不做则公式/图解内容直接丢失(baseline 中 formula 类低 recall 的根因)。这是"花一两毛钱换回检索不到的内容"。

---

## 4. 三条成本优化(必须实现)

### 4.1 只对含非文本的页做视觉转写
先检测每页**文字层密度**,**纯文字页直接跳过**,只对疑似含公式/图解/表格的页调 vision。
> 例:纯文字讲义(如 LLM-Prompting.pdf)理论上一页都不用走视觉,成本为 0。

### 4.2 转写用 Haiku 4.5
视觉够用、最便宜($1/$5)。把贵的 Sonnet/Opus 留给 Agent 推理,**模型分层**。

### 4.3 标准分辨率,不用高清
1,600 token/页 vs 4,784 token/页。讲义转写不需要 2576px 高清,渲染时控制在 ~1.15MP 内。

---

## 4.5 ⭐ 优先做:幻灯片预处理(零成本快速赢点)

> 来自 [ncc-vs-prompt.md](../evaluation/ncc-vs-prompt.md) 的实验发现:NCC 讲义检索崩到 0.41,**主因不是公式读不到,而是每页相同的导航页眉**让所有 chunk 在向量空间里长得极像、检索分不清页(text recall 仅 0.25)。

**这是比 Vision-LLM 更便宜、更先做的赢点**(几乎零 API 成本):

1. **剥掉重复样板** —— 检测并去除每页相同的导航页眉/页脚("Introduction · Prototypes · …" 这类),避免它淹没每页的真实信号。
2. **合并稀疏短文本页** —— 幻灯片常是几个 bullet,信号弱;切块时合理合并相邻稀疏页,提升 chunk 区分度。
3. **页码/装饰噪声清理** —— "N / 23" 之类的页码标记。

**顺序建议**:**先做幻灯片预处理(剥页眉),再做 Vision-LLM 转写**。前者用近乎零成本把 `text` 类 recall 拉起来;后者专门解决真正需要"看图"的 `formula`/`figure` 内容。两者互补,不是二选一。

> 验证:预处理后用 `--pdf NCC` 重跑,看 `text` 类 recall 从 0.25 提升多少;再上 Vision-LLM,看 `formula`/`figure` 提升多少。两步各自的增益分开量化。

---

## 5. 与评测(P6)的衔接

P7 的价值**用 P6 的 `content_modality` 标签量化**:
1. P6 baseline 已暴露:`formula`/`figure` 类题 recall 远低于 `text` 类(待放入含公式 PDF 后测出具体数字)。
2. P7 完成后**重跑同一批题**,看 `formula` 类 recall 从基线提升多少 —— 这就是 P7 价值的量化证据。

> 当前评测 PDF(LLM-Prompting.pdf)为纯文字,`content_modality` 全 `text`,测不出多模态短板。需放入含公式/图解的理工科讲义(如 pdfs/ 下的 Datenbank-Abfragen、MachineLearning-NCC)并补标 `formula`/`figure` 的 Q&A。

---

## 6. 对现有代码的影响

| 模块 | 影响 |
|---|---|
| `pdf_processor.py` | 新增"逐页渲染 + 文字层密度检测 + Vision 转写"前置步骤;转写文本与原文字层合并后再走现有 SemanticChunker |
| 依赖 | PDF→图片渲染(pdf2image/pymupdf);Anthropic 视觉调用(已有 SDK) |
| 切换需重建 | 改了 ingestion → 存量 PDF 需重新上传重建 ChromaDB collection(同切块策略迁移) |
| 异步 | 转写是重活,接入 P8 引入的 Celery + Redis 异步队列 |

---

## 7. 待决问题 (Open Questions)

- [ ] 文字层密度阈值如何定(每页字符数 / 覆盖率)?需小样本调参。
- [ ] 转写文本与原文如何合并切块——拼接 vs 分开 chunk 各带 `content_modality` 元数据?
- [ ] 渲染分辨率与转写质量的权衡点(DPI 设定)。
- [ ] 是否对表格用专门解析器(而非 vision)以保结构?(ADR-0004 评估)

---

## 8. 实测结果与结论 (Outcome — 2026-07-07)

### 8.1 实际实现

| 模块 | 做了什么 |
|---|---|
| `page_triage.py` | 逐页 PyMuPDF 廉价信号：字符数、图片面积占比、**矢量路径数（相对本文档基线，避开模板噪声）**、**数学字体（`CMMI/CMSY/CMEX`，比数 unicode 符号可靠得多）**。组合判定 text / vision，拿不准偏 vision |
| `vision_transcribe.py` | 页面渲染成图（150 DPI）→ `claude-sonnet-4-5` 转写：公式→LaTeX、图解→描述、表格→结构化，prompt 明确忽略页眉/页脚 |
| `pdf_processor.py` | **overlay 去重**（beamer 帧号，同帧只留最后一张）+ **双分支取文字** + **页眉/页脚剥离**（跨页重复行）+ 按页码合并 → 统一 SemanticChunker |
| 开关 | 环境变量 `EDUPREP_VISION` / `EDUPREP_HEADER_STRIP`（0/1），支持消融实验 |

转写质量本身**很好**（满页公式还原成干净可读 LaTeX，见冒烟测试）。问题不在转写质量，而在**检索架构**。

### 8.2 三组干净消融（vision 与 header-strip 分别隔离）

**A. 页眉/页脚剥离 —— 真实的赢点**（NCC，vision 全关，只切换 header-strip）

| 类别 | Recall@5 关→开 | Judge overall 关→开 |
|---|---|---|
| **text** | **0.250 → 0.417 (+0.167)** | 0.722 → 0.755 |
| formula | 0.615 → 0.692 (+0.077) | 0.756 → 0.807 |
| figure | 0.556 → 0.667 (+0.111) | 0.611 → 0.666 |
| **overall** | **0.471 → 0.588 (+0.117)** | 全线 +0.03~0.05 |

全线上升，`text` 涨最多（+0.167）——印证 [ncc-vs-prompt.md](../evaluation/ncc-vs-prompt.md) 的诊断：每页重复的导航条主要毒害 `text` 题。

**B. Vision 转写 —— 净负，且会侵蚀 A 的收益**（NCC `text` recall 的三配置）

| 配置 | text Recall@5 |
|---|---|
| 纯文字，不剥页眉 | 0.250 |
| 纯文字，**剥页眉** | **0.417** ✅ |
| 剥页眉 + **开 vision** | 0.292 ⬇️ |

开 vision 不仅没帮忙，还把页眉剥离挣来的 0.417 **同质化拉回 0.292**——净伤害。

**C. Vision 在图像型 deck 上同样崩**（CGG-Phong，both 剥页眉，只切换 vision）

| 类别 | Recall@5 text→多模态 | Judge text→多模态 |
|---|---|---|
| figure | **1.000 → 0.400** | 0.77 → 0.63 |
| formula | 0.667 → 0.667 | 0.83 → 0.83 |

即便是图像密集的图形学讲义，text-only 的 figure recall 也是满分 1.0（靠标题/图注），多模态反而把它干到 0.4。

### 8.3 与纯文字讲义（Prompting）的对照

| 指标 | Prompting（散文，无导航页眉） | NCC 修复前 | **NCC 剥页眉后** |
|---|---|---|---|
| Recall@5 | 0.81 | 0.41 | **0.588** |
| 与 Prompting 差距 | — | −0.40 | **−0.22** |

页眉剥离把 NCC 与纯文字讲义的差距**砍了一半**。剩余的 −0.22 来自幻灯片的结构性难点（每页文字稀疏、信号弱），不是一个小改动能补平的——而多模态本想补它，却因同质化帮了倒忙。

### 8.4 根因：为什么转写会"同质化"

检索靠**向量相似度**：不同页的向量必须"长得不一样"，查询才能挑出正确的那一页。

- **导航页眉问题**：每页加了「同一行样板文字」→ 所有 chunk 向量被拉到一起 → 检索分不清页。剥掉它 = 恢复区分度（+0.167）。
- **多模态转写问题**：转写把每一页的公式/图都写成同一套语言（`μ`、`距离`、`‖·‖`、`Σ`、"红球高光"…）→ 一堆页又变得**彼此相似** → 精确相关页被同质化的兄弟页挤出 top-k。

> **同一种病，两个来源**：页眉是"同一行文字"，转写是"同一套领域词汇"。我们刚用剥页眉治好，多模态又把病带了回来。原 §7 那个"拼接 vs 分开 chunk"的待决问题**两种都救不了**，因为病根是"转写内容参与了主检索排序"本身。

### 8.5 转写实例：同质化的第一手证据（CGG 真实输出）

下面是 `vision_transcribe.py` 对 CGG 三张不同图的**真实转写输出**（即会被切块入库的文字）：

**图14「Einfluss der Lichtrichtung」（三球，不同光照方向）**
> The image shows three rendered **red spheres**... **Left sphere:** shadow on the lower right portion, Lichtrichtung (1,-1,-1)... **Middle sphere:** uniform lighting with minimal shadow, Lichtrichtung (0,0,-1)... **Right sphere:** shadow on the lower left portion, Lichtrichtung (-1,-1,-1)...

**图20「cos(α)^γ 曲线」（chart）**
> The graph shows multiple curves plotting $\cos(\alpha)^{\gamma}$... exponents 1, 2, 4, 8, 32, and 256... As the exponent γ increases, the curves become progressively narrower... **larger exponents produce sharper, more focused highlights.**

**图23「Addition diffus+spekular」（纯图片等式，文字层仅 36 字符）**
> The slide shows a visual equation with three rendered **spheres**... Left: diffuse (matte) **shading**... Middle: a small white **specular highlight** point... Right: combining both diffuse and specular... `[diffuse sphere] + [specular highlight] = [combined sphere]`

**质量**：三段都准确读懂了纯文字层拿不到的视觉信息（暗部位置、曲线随指数变窄、图片等式的构成）。**问题不在转写质量。**

**同质化的直观证据**：把三段并排读，反复出现的共同词汇——

> `red sphere · diffuse · specular · highlight · shading · sphere · ...`

三张**内容完全不同**的图，转写出来却**共享大量相同的图形学词汇**。入库后这三个 chunk 的向量因共同词汇而彼此靠近；问"高光如何随光照变化"时，三页都含 `highlight / specular / sphere` → 检索器**分不清该给哪一页** → 精确相关页被挤出 top-k。**这就是 §8.4 同质化机制在文字层面的第一手证据**：转写写得又准又全，却让不同的图"读起来都像同一类东西"，稀释了检索赖以区分页面的独特性。

### 8.6 结论

- **默认关闭 vision（`EDUPREP_VISION=0`）；保留页眉剥离**——唯一真实、可量化的赢点。
- **保底**：只对 `has_text_layer=False` 的页（真扫描件）转写。这类页文字层为空，转写是唯一内容来源，不与文字竞争 → 不会同质化。已在 `pdf_processor.py` Pass 1 实现。
- 这次否决**是 P6 评测基线的价值体现**：用数据拦下"以为更好、实测更差"的改动。原 §5 预期的"formula/figure recall 会显著提升"被证伪。

### 8.7 视觉的正确用法（未来方向）

**铁律：视觉永远不参与"检索排序"**。守住这条，它就从净负变净赚。

| 用法 | 何时 | 为什么不同质化 |
|---|---|---|
| **仅扫描件保底** | 现在（已实现） | 无文字层，转写是唯一内容，不和文字竞争 |
| **喂给知识图谱概念抽取** | P8 | 抽取实体，不是"排序找页"，无同质化问题；`vision_transcribe.py` 直接复用 ⭐ |
| **按需 `look_at_page` 工具** | P11 Agent | ingestion 不转写，只在某题需要看图时临时调用，零同质化 |
| **两段式检索** | 若 RAG 视觉答题成为瓶颈 | 先用文字层检索到页，再**仅用该页转写**答题——转写不进排序 |

`page_triage.py` / `vision_transcribe.py` **不删**：它们是 P8 概念抽取与 P11 工具的现成零件。

> 原始结果 JSON 在 `backend/eval/results/`：NCC 消融 `_002015`(不剥页眉) / `_002630`(剥页眉)、NCC 多模态 `_233051`、CGG text-only `_235328` / 多模态 `_235906`。详细决策见 [ADR-0004](../adr/0004-multimodal-ingestion-vision-llm.md)。
