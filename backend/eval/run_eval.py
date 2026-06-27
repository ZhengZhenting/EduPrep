"""
run_eval.py — Main evaluation pipeline

Flow:
  load golden_qa.jsonl
    -> (optionally) ingest the eval PDFs into ChromaDB so retrieval works
    -> for each question: run hybrid retrieval, extract the pages it returned
    -> score against relevant_pages via metrics.py
    -> aggregate (skipping 'none'-type questions) and print a scorecard
    -> dump per-question results to JSON for later inspection

LLM-as-judge (answer quality) is added in the NEXT file (judge.py); this file
establishes the retrieval baseline first.

Run from the backend/ dir (so `import rag` etc. resolve):
    python eval/run_eval.py
Requires Ollama running (for embeddings) and the eval PDF present under
eval/datasets/pdfs/.
"""

from __future__ import annotations
import json
import time
from pathlib import Path

import sys, os
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from generate import generate_pdf_answer, answer_with_citation
from judge import judge_answer
from report import write_baseline_md
from rag import search_chunks_with_score, store_chunks
from pdf_processor import process_pdf
import metrics


# --- Config -----------------------------------------------------------------
EVAL_DIR = Path(__file__).parent
DATASET = EVAL_DIR / "datasets" / "golden_qa.jsonl"
PDF_DIR = EVAL_DIR / "datasets" / "pdfs"
RESULTS_DIR = EVAL_DIR / "results"
K = 5   # top-k chunks to retrieve / score at


def load_dataset(path: Path) -> list[dict]:
    """Read the JSONL golden dataset into a list of question dicts."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:                       # skip blank lines
                rows.append(json.loads(line))
    return rows


def ingest_pdfs(rows: list[dict]) -> None:
    """Chunk + embed + store each unique eval PDF into ChromaDB.

    Idempotent: store_chunks() drops and recreates the collection, so this is
    safe to re-run. Makes the baseline reproducible from scratch.
    """
    pdf_names = sorted({r["pdf"] for r in rows})
    for name in pdf_names:
        pdf_path = PDF_DIR / name
        file_bytes = pdf_path.read_bytes()
        chunks = process_pdf(file_bytes, name)   # same pipeline as production upload
        store_chunks(chunks, name)               # collection name derived from `name`
        print(f"[ingest] {name}: {len(chunks)} chunks stored")


def retrieved_pages(results: list, k: int) -> list[int]:
    """Turn retrieval output into a rank-ordered list of 1-indexed page numbers.

    CRITICAL: PyPDFLoader stores `metadata['page']` as 0-INDEXED, but the golden
    dataset's relevant_pages are 1-INDEXED. We add 1 here so both sides match.
    """
    pages = []
    for doc, _score in results[:k]:
        page0 = doc.metadata.get("page")     # 0-indexed, may be missing
        if page0 is not None:
            pages.append(page0 + 1)          # convert to 1-indexed
    return pages

def evaluate(rows: list[dict], k: int) -> dict:
    """For every question: retrieve -> generate answer -> judge it -> collect.

    Retrieval, generation and judging run for ALL questions. Only the retrieval
    *metrics* are skipped for 'none'-type questions (they have no relevant pages),
    but those questions are STILL generated + judged — that's the hallucination
    test (does the system fabricate when the lecture has no answer?).
    """
    per_question = []
    recalls, precisions, rrs = [], [], []

    for row in rows:
        # 1. Retrieval — always run (even 'none' retrieves *some* chunks)
        results, _best_cosine = search_chunks_with_score(row["question"], row["pdf"], k)
        got_pages = retrieved_pages(results, k)

        # 2. Retrieval metrics — only when ground-truth pages exist
        if row["relevant_pages"]:
            recall = metrics.recall_at_k(got_pages, row["relevant_pages"], k)
            precision = metrics.precision_at_k(got_pages, row["relevant_pages"], k)
            rr = metrics.reciprocal_rank(got_pages, row["relevant_pages"])
        else:
            recall = precision = rr = None        # skipped, not zero

        # 3. Generate the PDF-grounded answer (mirrors /ask)
        gen = generate_pdf_answer(row["question"], results)

        # 4. Judge the answer; feed it the page footer + the page-tagged sources
        judged = judge_answer(
            question=row["question"],
            generated_answer=answer_with_citation(gen),
            retrieved_sources=gen["sources_text"],
            relevant_pages=row["relevant_pages"],
            answer_coverage=row["answer_coverage"],
            reference_hint=row.get("reference_answer", ""),   # hint only, not authoritative
        )

        recalls.append(recall)
        precisions.append(precision)
        rrs.append(rr)

        per_question.append({
            "id": row["id"],
            "answer_coverage": row["answer_coverage"],
            "content_modality": row["content_modality"],
            "relevant_pages": row["relevant_pages"],
            "retrieved_pages": got_pages,
            "recall": recall,
            "precision": precision,
            "rr": rr,
            "answer": gen["answer"],
            "pages_used": gen["pages_used"],
            "judge": judged,                       # report.py aggregates these
        })

        # progress line so a 30-question run isn't a silent wait
        print(f"  {row['id']:<12} recall={recall} overall={judged['overall']}")

    summary = {
        "k": k,
        "n_total": len(rows),
        "n_scored": sum(1 for r in recalls if r is not None),
        "recall_at_k": metrics.mean_ignore_none(recalls),
        "precision_at_k": metrics.mean_ignore_none(precisions),
        "mrr": metrics.mean_ignore_none(rrs),
    }
    return {"summary": summary, "per_question": per_question}

def slice_by(per_question: list[dict], field: str) -> dict:
    """Diagnostic: average recall grouped by a field (answer_coverage / content_modality)."""
    groups: dict[str, list] = {}
    for q in per_question:
        groups.setdefault(q[field], []).append(q["recall"])
    return {key: metrics.mean_ignore_none(vals) for key, vals in groups.items()}


def main() -> None:
    rows = load_dataset(DATASET)

    # Optional: run only ONE PDF's questions
    # usage: python eval/run_eval.py --pdf MachineLearning-SimpleClassifiers-NCC.pdf
    pdf_filter = None
    if "--pdf" in sys.argv:
        pdf_filter = sys.argv[sys.argv.index("--pdf") + 1]
        rows = [r for r in rows if r["pdf"] == pdf_filter]
        print(f"Filtered to PDF: {pdf_filter}  ({len(rows)} questions)")

    ingest_pdfs(rows)            # only ingests the PDF(s) present in the (filtered) rows
    report = evaluate(rows, K)

    # Write to a PDF-specific baseline so it doesn't overwrite the existing one
    if pdf_filter:
        slug = Path(pdf_filter).stem.lower()[:24]
        baseline_path = Path(__file__).parents[2] / "docs" / "evaluation" / f"baseline-{slug}.md"
        write_baseline_md(report, baseline_path)
    else:
        write_baseline_md(report)   # combined → docs/evaluation/baseline.md

    RESULTS_DIR.mkdir(exist_ok=True)
    tag = Path(pdf_filter).stem if pdf_filter else "all"
    out = RESULTS_DIR / f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved raw: {out}")

if __name__ == "__main__":
    main()