"""page classification (triage): decide whether each page goes through
plain text extraction or multimodal vision transcription."""
from __future__ import annotations
import fitz  # PyMuPDF
import statistics

# --- Threshold config (calibrate with triage_signals.py first) --------------
CHAR_COUNT_MIN      = 40     # effective char count < this -> likely image page
IMAGE_AREA_RATIO    = 0.20   # raster image covers > 20% of page -> has figure
VECTOR_PATH_MIN     = 30     # vector path count > this -> likely vector diagram
FORMULA_SYMBOL_MIN  = 3      # math symbol count >= this -> likely has formula
FORMULA_DENSITY_MIN = 0.01   # or symbols / chars > 1%
VECTOR_MARGIN = 20   # a page must exceed the deck's baseline by this many paths
_MATH_FONT_MARKERS = ("CMMI", "CMSY", "CMEX", "MSAM", "MSBM")
_FORMULA_CHARS = set("∫∑∏√≤≥≈≠±∞∂∇αβγδθλμπσφωΣΩ∈∉⊂⊆∀∃→⇒⇔·×÷")

# findout formula symbols in text, return count and density (count / char_count)
def _formula_signal(text:str)->tuple[int,float]:
    if not text:
        return 0, 0.0
    count = sum(1 for ch in text if ch in _FORMULA_CHARS)
    return count, count/max(len(text),1)

def analyze_page(page: "fitz.Page") -> dict:
    """Collect all triage signals for one page (collect only, no decision)."""
    text = page.get_text("text").strip()
    char_count = len(text.replace(" ", "").replace("\n", ""))

    # Raster image area ratio
    page_area = page.rect.width * page.rect.height
    img_area = 0.0
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        img_area += abs((x1 - x0) * (y1 - y0))
    image_area_ratio = min(img_area / page_area, 1.0) if page_area else 0.0

    # Vector path count (covers the blind spot get_images misses)
    vector_path_count = len(page.get_drawings())

    formula_count, formula_density = _formula_signal(text)
    fonts = {f[3].upper() for f in page.get_fonts()}
    has_math_font = any(m in fn for fn in fonts for m in _MATH_FONT_MARKERS)

    return {
        "char_count": char_count,
        "has_text_layer": char_count > 0,
        "image_area_ratio": round(image_area_ratio, 3),
        "vector_path_count": vector_path_count,
        "formula_count": formula_count,
        "formula_density": round(formula_density, 4),
        "has_math_font": has_math_font
    }

def vector_threshold_for_doc(signals_list: list[dict]) -> int:
    """Per-document vector-path threshold that ignores the template baseline
    (decorative lines/logos repeated on every page)."""
    counts = [s["vector_path_count"] for s in signals_list]
    baseline = statistics.median(counts) if counts else 0
    return max(VECTOR_PATH_MIN, int(baseline) + VECTOR_MARGIN)

def classify_page(sig: dict, vector_threshold: int = VECTOR_PATH_MIN) -> str:
    """Combined decision: return 'vision' (multimodal) or 'text'.
    Priority hard -> soft; when unsure, prefer 'vision'."""
    if not sig["has_text_layer"]:                       # hard signal: scanned/image page
        return "vision"
    if sig["image_area_ratio"] > IMAGE_AREA_RATIO:      # substantial raster image
        return "vision"
    if sig["vector_path_count"] > vector_threshold:      # vector diagram
        return "vision"
    if (sig["formula_count"] >= FORMULA_SYMBOL_MIN      # contains formula
            or sig["formula_density"] > FORMULA_DENSITY_MIN):
        return "vision"
    if sig["char_count"] < CHAR_COUNT_MIN:              # fallback: too few chars
        return "vision"
    if sig["has_math_font"]:                            # math typesetting present
        return "vision"
    return "text"