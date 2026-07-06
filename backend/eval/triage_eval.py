"""
triage_eval.py — Evaluate triage-threshold accuracy against manual labels
(confusion matrix + precision/recall). Unlabeled pages default to "text".
page is 1-indexed.
Usage (from backend/): python eval/triage_eval.py
"""
from __future__ import annotations
import sys, os, json
from pathlib import Path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import fitz
from page_triage import analyze_page, classify_page

EVAL_DIR = Path(__file__).parent
PDF_DIR = EVAL_DIR / "datasets" / "pdfs"
LABELS = EVAL_DIR / "datasets" / "page_labels.jsonl"


def load_labels() -> dict:
    labels = {}
    if LABELS.exists():
        with open(LABELS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    labels[(r["pdf"], r["page"])] = r["true_mode"]
    return labels


def main():
    labels = load_labels()
    tp = fp = fn = tn = 0
    mistakes = []
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        doc = fitz.open(pdf_path)
        for i in range(len(doc)):
            pred = classify_page(analyze_page(doc[i]))
            true = labels.get((pdf_path.name, i + 1), "text")
            if pred == "vision" and true == "vision":
                tp += 1
            elif pred == "vision" and true == "text":
                fp += 1; mistakes.append((pdf_path.name, i + 1, "FP wasted cost"))
            elif pred == "text" and true == "vision":
                fn += 1; mistakes.append((pdf_path.name, i + 1, "FN lost content!"))
            else:
                tn += 1
        doc.close()

    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    print(f"vision precision = {prec:.2f}  (of predicted-vision, how many truly need vision)")
    print(f"vision recall    = {rec:.2f}   (of truly-vision pages, how many were caught; MOST important)")
    print(f"TP={tp} FP={fp} FN={fn} TN={tn}")
    print("\nMisclassifications (watch FN — losing content is irreversible):")
    for m in mistakes:
        print("  ", *m)


if __name__ == "__main__":
    main()