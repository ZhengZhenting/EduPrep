"""
triage_signals.py — Print per-page triage signals to calibrate thresholds
(inspect the distribution, no right/wrong judgment).
Usage (from backend/): python eval/triage_signals.py
"""
from __future__ import annotations
import sys, os
from pathlib import Path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import fitz
from page_triage import analyze_page, classify_page,  vector_threshold_for_doc

PDF_DIR = Path(__file__).parent / "datasets" / "pdfs"

def main(): 
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")): 
        doc = fitz.open(pdf_path)
        signals = [analyze_page(doc[i]) for i in range(len(doc))] 
        vthr = vector_threshold_for_doc(signals)
        print(f"\n=== {pdf_path.name} ({len(doc)} pages)  vthr={vthr} ===")
        print(f"{'pg':>3} {'chars':>6} {'img%':>6} {'vec':>5} {'fml':>4} {'dens':>6}  decision")
        for i, s in enumerate(signals):
            print(f"{i+1:>3} {s['char_count']:>6} {s['image_area_ratio']:>6} "
                  f"{s['vector_path_count']:>5} {s['formula_count']:>4} "
                  f"{str(s['has_math_font']):>5}  {classify_page(s, vthr)}")
        doc.close()


if __name__ == "__main__":
    main()