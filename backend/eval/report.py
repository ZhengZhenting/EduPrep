"""
report.py — Aggregate eval results into a scorecard and write baseline.md.

Consumes the report produced by run_eval (per-question records that carry both
retrieval metrics and the judge's answer-quality dims), then:
  - aggregates answer quality (overall + per-dimension, ignoring N/A)
  - prints a console scorecard
  - writes a human-readable docs/evaluation/baseline.md (a P6 deliverable)

Kept separate from run_eval so reporting can be re-run on a saved results JSON
without re-hitting the LLM.
"""

from __future__ import annotations
import json
import time
from pathlib import Path

from metrics import mean_ignore_none   # reuse the None-skipping averager

BASELINE_MD = Path(__file__).parents[2] / "docs" / "evaluation" / "baseline.md"


def aggregate_answer_quality(per_question: list[dict]) -> dict:
    """Average the judge's overall + each dimension across all judged questions.

    Each per_question item is expected to have a 'judge' dict with keys
    correctness / faithfulness / citation / honesty / overall (any may be None).
    """
    dims = ("correctness", "faithfulness", "citation", "honesty", "overall")
    out = {}
    for d in dims:
        # pull this dim from every question that has a judge result
        values = [q["judge"][d] for q in per_question if q.get("judge")]
        out[d] = mean_ignore_none(values)      # None-safe mean
    out["n_judged"] = sum(1 for q in per_question if q.get("judge"))
    return out


def slice_mean(per_question: list[dict], group_field: str, value_path: tuple) -> dict:
    """Group rows by `group_field` and average a nested value (e.g. recall, or
    judge.overall). value_path is a tuple of keys, e.g. ('recall',) or
    ('judge', 'overall'). Used for the per-coverage / per-modality diagnostics.
    """
    groups: dict[str, list] = {}
    for q in per_question:
        # walk the nested path; missing -> None
        val = q
        for key in value_path:
            val = val.get(key) if isinstance(val, dict) else None
        groups.setdefault(q[group_field], []).append(val)
    return {key: mean_ignore_none(vals) for key, vals in groups.items()}


def _fmt(x) -> str:
    """Format a metric for display ('--' when N/A)."""
    return f"{x:.3f}" if isinstance(x, (int, float)) else "--"


def print_scorecard(report: dict) -> None:
    """Print the two-headline scorecard to the console."""
    s = report["summary"]
    aq = report["answer_quality"]
    k = s["k"]
    print("\n" + "=" * 52)
    print("  EduPrep RAG Baseline v0")
    print(f"  questions: {s['n_total']}  |  k={k}")
    print("-" * 52)
    print(f"  [1] Retrieval Recall@{k} ...... {_fmt(s['recall_at_k'])}   (n={s['n_scored']})")
    print(f"  [2] Answer Score (judge) ..... {_fmt(aq['overall'])}   (n={aq['n_judged']})")
    print("-" * 52)
    print(f"  diagnostics:")
    print(f"    Precision@{k}={_fmt(s['precision_at_k'])}  MRR={_fmt(s['mrr'])}")
    print(f"    judge dims: correctness={_fmt(aq['correctness'])} "
          f"faithfulness={_fmt(aq['faithfulness'])} "
          f"citation={_fmt(aq['citation'])} honesty={_fmt(aq['honesty'])}")
    print("=" * 52)


def render_baseline_md(report: dict) -> str:
    """Build the markdown body for baseline.md."""
    s = report["summary"]
    aq = report["answer_quality"]
    k = s["k"]
    pq = report["per_question"]

    recall_by_cov = slice_mean(pq, "answer_coverage", ("recall",))
    recall_by_mod = slice_mean(pq, "content_modality", ("recall",))
    score_by_cov = slice_mean(pq, "answer_coverage", ("judge", "overall"))

    lines = [
        "# RAG 评测基线 (Baseline v0)",
        "",
        f"> 自动生成于 {time.strftime('%Y-%m-%d %H:%M:%S')} · 方法见 [methodology.md](./methodology.md)",
        f"> 数据集 {s['n_total']} 题 · k={k} · 生成模型 sonnet-4-5 / judge opus-4-8 · temperature=0",
        "",
        "## 头部指标",
        "",
        "| 指标 | 分数 | 样本数 |",
        "|---|---|---|",
        f"| 检索 Recall@{k} | **{_fmt(s['recall_at_k'])}** | {s['n_scored']} |",
        f"| 回答得分 Answer Score | **{_fmt(aq['overall'])}** | {aq['n_judged']} |",
        "",
        "## 检索诊断",
        "",
        f"- Precision@{k}: {_fmt(s['precision_at_k'])}",
        f"- MRR: {_fmt(s['mrr'])}",
        "",
        "**按 answer_coverage 拆分 (Recall):** "
        + " · ".join(f"{kk}={_fmt(vv)}" for kk, vv in recall_by_cov.items()),
        "",
        "**按 content_modality 拆分 (Recall):** "
        + " · ".join(f"{kk}={_fmt(vv)}" for kk, vv in recall_by_mod.items()),
        "",
        "## 回答质量诊断",
        "",
        f"- 正确性 correctness: {_fmt(aq['correctness'])}",
        f"- 忠实度 faithfulness: {_fmt(aq['faithfulness'])}",
        f"- 引用准确 citation: {_fmt(aq['citation'])}",
        f"- 诚实性 honesty (仅 none 题): {_fmt(aq['honesty'])}",
        "",
        "**按 answer_coverage 拆分 (Answer Score):** "
        + " · ".join(f"{kk}={_fmt(vv)}" for kk, vv in score_by_cov.items()),
        "",
        "## 局限",
        "",
        "- 样本量小 (每层 6–15 题)，层内均值有噪声，仅看大方向。",
        "- 评测 PDF 为纯文字课件，content_modality 全为 text，测不出多模态短板。",
        "- judge 存在已知偏差，结果需人工校准 (methodology §5.5)。",
        "",
    ]
    return "\n".join(lines)


def write_baseline_md(report: dict, path: Path = BASELINE_MD) -> None:
    """Attach answer-quality aggregates, then write baseline.md."""
    report["answer_quality"] = aggregate_answer_quality(report["per_question"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_baseline_md(report), encoding="utf-8")
    print_scorecard(report)
    print(f"\nWrote: {path}")


# --- regenerate the report from a saved results JSON (no LLM calls) ---
if __name__ == "__main__":
    import sys
    results_path = Path(sys.argv[1])      # e.g. eval/results/full_20260623_xxxx.json
    report = json.loads(results_path.read_text(encoding="utf-8"))
    write_baseline_md(report)