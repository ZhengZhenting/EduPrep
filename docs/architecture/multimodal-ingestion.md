# Vision-LLM 多模态 Ingestion 设计

> **状态**: Draft (P7 设计文档)
> **更新**: 2026-06-24
> **关联**: [knowledge-graph-schema.md](./knowledge-graph-schema.md) · [methodology.md](../evaluation/methodology.md)(content_modality)· [ADR-0004](../adr/0004-multimodal-ingestion-vision-llm.md)(Vision-LLM vs Nougat/DeepDoc)
> **代码**: `backend/pdf_processor.py`(改造)· `backend/eval/`(量化验证)

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
