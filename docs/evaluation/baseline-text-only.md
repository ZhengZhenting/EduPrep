# RAG 评测基线 (Baseline v0)

> 自动生成于 2026-06-23 23:47:10 · 方法见 [methodology.md](./methodology.md)
> 数据集 30 题 · k=5 · 生成模型 sonnet-4-5 / judge opus-4-8 · temperature=0

## 头部指标

| 指标 | 分数 | 样本数 |
|---|---|---|
| 检索 Recall@5 | **0.810** | 21 |
| 回答得分 Answer Score | **0.850** | 30 |

## 检索诊断

- Precision@5: 0.190
- MRR: 0.515

**按 answer_coverage 拆分 (Recall):** standard=0.800 · fuzzy=0.833 · none=--

**按 content_modality 拆分 (Recall):** text=0.810

## 回答质量诊断

- 正确性 correctness: 0.881
- 忠实度 faithfulness: 0.983
- 引用准确 citation: 0.500
- 诚实性 honesty (仅 none 题): 1.000

**按 answer_coverage 拆分 (Answer Score):** standard=0.789 · fuzzy=0.778 · none=1.000

## 局限

- 样本量小 (每层 6–15 题)，层内均值有噪声，仅看大方向。
- 评测 PDF 为纯文字课件，content_modality 全为 text，测不出多模态短板。
- judge 存在已知偏差，结果需人工校准 (methodology §5.5)。
