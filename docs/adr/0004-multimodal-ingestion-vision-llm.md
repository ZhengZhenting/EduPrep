# ADR-0004: 多模态 Ingestion 选用 Vision-LLM

- **状态 (Status)**: **Reversed（实现并度量后否决为默认）** — 详见 §实测结果与最终决策
- **日期 (Date)**: 2026-06-24 提出 · 2026-07-07 度量并否决
- **关联 (Related)**: [multimodal-ingestion.md](../architecture/multimodal-ingestion.md)(设计、成本与实测)· [ADR-0002 切块](./0002-semantic-chunking.md) · [baseline.md](../evaluation/baseline.md)

> **一句话结论**：Vision-LLM 逐页转写在讲义幻灯片上**净负**——讲义标题/图注本就足以检索到正确页，而把整页转写塞进同一检索库会**同质化语料、把精确相关页挤出 top-k**，导致 recall 与 citation 双降。已在两份不同 deck 上复现。默认关闭（`EDUPREP_VISION=0`），仅保留几乎零成本的页眉/页脚剥离。

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

## 实测结果与最终决策 (Outcome — measured, 2026-07-07)

P7 实现后用 P6 的 `content_modality` 标签，在**两份不同的 deck** 上做了 text-only（`EDUPREP_VISION=0`）vs 多模态的对照实验（同一批 golden 题）。

**实现**：`page_triage.py`（PyMuPDF 廉价信号：字符数 / 图片面积占比 / 矢量路径数 / 数学字体）判定每页走文字还是视觉；`vision_transcribe.py`（`claude-sonnet-4-5`，150 DPI）转写；`pdf_processor.py` 增加 overlay 去重 + 双分支取文字 + 页眉/页脚剥离。转写质量本身很好（满页公式还原成干净 LaTeX）。

**结果（text-only → 多模态）**：

| Deck | 类别 | Recall@5 | Judge overall |
|---|---|---|---|
| NCC（公式型 LaTeX，原始题） | formula | 0.556 → 0.556 | 0.85 → 0.77 |
| | figure | 0.500 → 0.500 | 0.53 → 0.44 |
| CGG-Phong（图像型 PPT，12 题） | figure | **1.000 → 0.400** | 0.77 → 0.63 |

多模态在两份 deck 上都**没有提升检索、且答案质量下降**（CGG figure recall 直接从满分崩到 0.4）。

**根因（两条）**：

1. **讲义幻灯片"自带文字说明"**：标题 + 图注让 text-only 已能检索到正确页（CGG figure recall = 1.0）。图片不是**检索**的必需品——即便是只有 36 字符的纯图页，也靠标题被检索到。
2. **转写同质化语料**：所有页转写后都是相似的"公式/球体"描述，向量空间里彼此更像，**真正相关的页被同质化的转写兄弟页挤出 top-k** → recall 与 citation 双降。CGG-q08 讽刺地：转写把页23 挤掉后连标题都丢了，答案反而更差（judge 0.83→0.33）。

**页眉剥离的干净消融**（vision 全关，只切换 header-strip）证明它是**唯一真实的赢点**：

| NCC，vision 全关 | text | overall |
|---|---|---|
| 不剥页眉 → 剥页眉 | **0.250 → 0.417 (+0.167)** | 0.471 → 0.588 (+0.117) |

且 **vision 会侵蚀这个收益**：剥页眉的 `text` recall 0.417，一旦开 vision 又被同质化拉回 0.292。与纯文字讲义 Prompting（Recall 0.81）相比，NCC 剥页眉后从 0.41 追到 0.588，差距砍半。

**最终决策**：

- **默认关闭 Vision-LLM**（`EDUPREP_VISION=0`），**保留页眉/页脚剥离**（`ENABLE_HEADER_STRIP=1`，NCC `text` recall 0.25→0.42）。
- **仅扫描件保底**：只对 `has_text_layer=False` 的页转写（已在 `pdf_processor.py` Pass 1 实现）——这类页文字层为空，转写是唯一内容来源，不与文字竞争 → 不同质化。普通讲义 0 页触发，永不变差。

**视觉的正确用法（未来，铁律：不进检索排序）**：

- **P8 知识图谱**：`vision_transcribe.py` 的转写喂给概念抽取（从图/公式抽概念）——抽实体不是排序找页，无同质化。视觉的价值从 RAG 迁到 KG 层 ⭐
- **P11 Agent**：`look_at_page` 按需工具，只在某题需要看图时临时调用，ingestion 不转写。
- **两段式检索**（若 RAG 视觉答题成瓶颈）：先用文字层检索到页，再**仅用该页转写**答题，转写不参与排序。
- `page_triage.py` / `vision_transcribe.py` **不删**，是上述方向的现成零件。

**元结论**：这次否决**正是 P6 评测基线的价值**——它拦下了一个"我们以为更好、实测更差"的改动，用数据而非直觉做决策。备选方案里的 Nougat / DeepDoc / ColPali 仍作为「真扫描件 + 架构重做」方向的远期候选，不删除。详细数据与同质化机制见 [multimodal-ingestion.md §8](../architecture/multimodal-ingestion.md)。
