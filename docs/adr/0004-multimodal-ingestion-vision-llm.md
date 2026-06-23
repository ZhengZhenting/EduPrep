# ADR-0004: 多模态 Ingestion 选用 Vision-LLM

- **状态 (Status)**: Proposed (P7 规划)
- **日期 (Date)**: 2026-06-24
- **关联 (Related)**: [multimodal-ingestion.md](../architecture/multimodal-ingestion.md)(设计与成本)· [ADR-0002 切块](./0002-semantic-chunking.md)

---

## 背景 (Context)

现有 ingestion 用 `PyPDFLoader` 只抽取 PDF 的**文字层**,公式、图解、图片、表格大多丢失或损坏。德语理工科讲义恰恰满是这些内容,这是检索质量的隐形天花板——P6 baseline 预期会显示 `formula`/`figure` 类题的 recall 远低于 `text` 类。

P7 要让 ingestion "看懂"非文本内容。需要决定**用什么手段把公式/图解/表格转成可检索的文本**。约束:

- 已有 Anthropic Claude(含视觉)访问,不想引入重型新依赖;
- 单人开发,工程预算有限,优先一次预处理即可见效的方案;
- 转写质量要足够支撑后续 P8 的概念抽取(知识图谱);
- 成本可控(详见 multimodal-ingestion.md §3 成本模型)。

## 决策 (Decision)

采用 **Vision-LLM 逐页转写**:把每页 PDF 渲染成图片,用 **Claude 视觉能力**把公式转成 LaTeX、图解转成文字描述、表格转成 Markdown、图片转成内容描述,与原文字层一起切块入库。

转写模型用 **Haiku 4.5**(视觉够用且最便宜),标准分辨率(~1,600 token/页),并只对**含非文本的页**做转写(纯文字页跳过)。

## 理由 (Rationale)

- **零重型新依赖**:复用已有的 Claude 访问,只需加一个 PDF→图片渲染库;一次预处理即可。
- **通用性最强**:同一个 vision 调用同时处理公式、图解、图片、表格四类内容,不必为每类内容接一个专用解析器。
- **质量满足下游**:转写出的 LaTeX/结构化文本既能提升检索,也能直接喂给 P8 的概念抽取——两者协同。
- **成本一次性且很小**:一份 44 页 PDF 约 $0.14(Haiku),且只在 ingestion 付一次,查询成本不变(详见设计文档 §3）。

## 备选方案 (Alternatives Considered)

| 方案 | 是什么 | 不选的原因 |
|---|---|---|
| **Nougat**(Meta) | 专为学术 PDF 设计,把公式转 LaTeX/Markdown 的开源模型 | 公式转写质量很高,但**只解决公式**(图解/照片/复杂表格弱),且引入重型模型依赖(GPU 友好、本地部署成本高)。**列为公式密集场景的远期备选**。 |
| **Marker** | 开源 PDF→Markdown,带版面与公式处理 | 比 PyPDF 强很多,但同样是重依赖、需自建管线,通用性不如 vision-LLM,且对图解语义理解有限。 |
| **RagFlow DeepDoc** | 版面分析 + 表格结构识别 + OCR(你对标的 RagFlow 的核心) | 质量天花板高、是真正的"深度"方向,但工程量大、依赖重,**超出 P7 当前投入**。**列为远期方向**。 |
| **纯 OCR**(如 Tesseract/PaddleOCR) | 把页面图 OCR 成文字 | 能拿回图片里的文字,但**不理解公式结构**(OCR 后的公式仍是乱码),也不描述图解语义。 |
| **多模态 embedding / 视觉检索**(如 ColPali) | 存页面图,用视觉模型直接检索,绕过文字抽取 | 最前沿,但改动最大、与现有文本 RAG 管线不兼容,工程风险高。**远期可探索**。 |

## 后果 (Consequences)

**正面**
- 公式/图解/表格内容首次进入可检索范围,预期显著提升 `formula`/`figure` 类 recall。
- 转写文本同时服务检索与 P8 概念抽取。
- 用现有 Claude 视觉,落地成本低。

**负面 / 需注意**
- **处理更慢 + 一次性 API 成本**:逐页渲染 + vision 调用增加上传处理时间和约 $0.14/PDF 的一次性花费(靠"只转非文字页 + Haiku + 标准分辨率"压低,见设计文档 §4)。
- **切换需重建**:改了 ingestion → 存量 PDF 需重新上传重建 ChromaDB collection(同 ADR-0002 的迁移代价)。
- **新依赖**:PDF→图片渲染库(pymupdf / pdf2image)。
- **质量非完美**:vision 转写偶有错误,公式复杂时不如 Nougat 精确——若公式场景成为主要瓶颈,再评估引入 Nougat。

## 待验证 (Open / To Measure)

本决策的"显著提升"目前是预期。**P7 完成后用 P6 的 `content_modality` 标签重跑评测**,量化 `formula`/`figure` 类 recall 相对基线的增益,结果回填 `docs/evaluation/baseline.md`。若 Vision-LLM 在公式上的质量不达标,重新评估 Nougat(本 ADR 标记为待取代的候选,不删除)。
