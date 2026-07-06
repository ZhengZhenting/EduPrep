from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain_core.documents import Document
from rag import get_embedding_function   # 复用检索同款 embedding 模型
from page_triage import analyze_page, classify_page, vector_threshold_for_doc
from vision_transcribe import render_page_to_png, transcribe_page
from collections import Counter
import fitz
import re
import tempfile
import os

# --- Feature flags ---
# Measured on NCC + CGG (see docs/architecture/multimodal-ingestion.md §8):
#   - Header/footer stripping is a real win (NCC text Recall@5 0.25 -> 0.42).
#   - Full vision transcription is NET-NEGATIVE on lecture slides: it homogenizes
#     the corpus (every page looks alike -> exact page crowded out of top-k) and
#     actually erodes the header-strip gain (NCC text recall 0.42 -> 0.29).
# So VISION defaults OFF. A page with NO text layer (true scan) is still
# transcribed as a safety net (see process_pdf Pass 1) — there the transcription
# is the ONLY content source, so it cannot homogenize against existing text.
# Env overrides (EDUPREP_VISION / EDUPREP_HEADER_STRIP = 0/1) let eval runs toggle.
ENABLE_VISION       = os.getenv("EDUPREP_VISION", "0") != "0"        # default OFF (net-negative)
ENABLE_HEADER_STRIP = os.getenv("EDUPREP_HEADER_STRIP", "1") != "0"  # default ON (real win)

# detect header/footer
def _detect_repeated_lines(page_texts: list[str], threshold: float = 0.6) -> set[str]:
    """Count each line's cross-page frequency; return lines appearing on more
    than `threshold` of pages (headers/footers)."""
    n = len(page_texts)
    if n < 3:
        return set() #页数太少(<3 页)时,"跨页重复"这个统计不可靠
    counter = Counter()
    for text in page_texts:
        # Dedup per page first so repeated lines within a page aren't over-counted
        lines = {ln.strip() for ln in text.splitlines() if ln.strip()}
        counter.update(lines)
    return {line for line, c in counter.items() if c / n > threshold}

#delete repeated lines from text
def _strip_lines(text: str, repeated: set[str]) -> str:
    return "\n".join(ln for ln in text.splitlines() if ln.strip() not in repeated)

# extract beamer-style frame number ('N / total') from each page's footer
def _frame_numbers(page_texts: list[str]) -> list[int | None]:
    """The slide total = the most common denominator across all pages; for each
    page take the last 'N / total' match (the footer). None where not found."""
    all_pairs = [re.findall(r'(\d+)\s*/\s*(\d+)', t) for t in page_texts]
    denoms = Counter(int(d) for pairs in all_pairs for _, d in pairs)
    if not denoms:
        return [None] * len(page_texts)
    total = denoms.most_common(1)[0][0]
    nums: list[int | None] = []
    for pairs in all_pairs:
        frame = None
        for num, den in pairs:
            if int(den) == total:
                frame = int(num)          # last match with the slide-total denominator
        nums.append(frame)
    return nums

# overlay dedup: keep only the last (fullest) physical page of each overlay run
def _dedup_overlay_pages(page_texts: list[str]) -> list[int]:
    """Beamer overlay frames emit one physical page per incremental reveal. Group
    consecutive pages sharing the same frame number and keep only the last one.
    Fallback for pages without a frame number: drop a page whose text is a strict
    subset of the next page's."""
    n = len(page_texts)
    frames = _frame_numbers(page_texts)
    keep = []
    for i in range(n):
        if i + 1 < n:
            if frames[i] is not None and frames[i] == frames[i + 1]:
                continue                  # same frame as next -> earlier reveal, drop
            if frames[i] is None:
                cur = {l.strip() for l in page_texts[i].splitlines() if l.strip()}
                nxt = {l.strip() for l in page_texts[i + 1].splitlines() if l.strip()}
                if cur and cur.issubset(nxt):
                    continue
        keep.append(i)
    return keep

def process_pdf(file_bytes: bytes, filename:str) -> list:
    """ Take PDF bytes, return chunked docs (with page / source / ingest_mode metadata)."""

    # PyPDFLoader需要读取文件路径，不能直接读二进制,所以先把上传的文件临时保存到磁盘
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(file_bytes)
        temp_path = temp_file.name

    try:
        # 用LangChain的PyPDFLoader加载PDF,自动保留每页的页码信息
        text_pages = PyPDFLoader(temp_path).load()
        doc = fitz.open(stream=file_bytes, filetype="pdf") # fitz: used only for signal analysis + rendering

        # ---- Overlay dedup: keep only the last (fullest) page of each overlay run ----
        keep = _dedup_overlay_pages([tp.page_content for tp in text_pages])
        dropped = [i + 1 for i in range(len(doc)) if i not in keep]
        if dropped:
            print(f"[overlay] dropped {len(dropped)} overlay pages (1-idx): {dropped}")

        # ---- Pass 1: per-page triage (kept pages only) ----每一页分类：提取文字还是视觉识别
        signals = {i: analyze_page(doc[i]) for i in keep}
        vthr = vector_threshold_for_doc(list(signals.values()))
        print(f"[triage] per-doc vector threshold = {vthr}")
        modalities = {}
        for i in keep:
            if ENABLE_VISION:
                mode = classify_page(signals[i], vthr)          # full multimodal triage
            elif not signals[i]["has_text_layer"]:
                mode = "vision"                                 # scanned-page safety net
            else:
                mode = "text"                                   # default: trust the text layer
            modalities[i] = mode
            print(f"[triage] page {i+1}: {mode} {signals[i]}")

        # ---- Header/footer detection (text pages only) ----
        repeated = set()
        if ENABLE_HEADER_STRIP:
            text_page_texts = [text_pages[i].page_content
                               for i in keep if modalities[i] == "text"]
            repeated = _detect_repeated_lines(text_page_texts)
            if repeated:
                print(f"[header/footer] stripped {len(repeated)} repeated lines")

        # ---- Pass 2: get clean text per kept page -> per-page Document (in page order) ----
        page_docs = []
        for i in keep:
            if modalities[i] == "vision":
                content = transcribe_page(render_page_to_png(doc[i]))
                print(f"[vision] page {i+1}: transcribed {len(content)} chars")
            else:
                content = text_pages[i].page_content
                if ENABLE_HEADER_STRIP:
                    content = _strip_lines(content, repeated)
            page_docs.append(Document(
                page_content=content,
                metadata={"page": i,               # 0-indexed physical page, keep old convention
                          "source": filename,
                          "ingest_mode": modalities[i]},
            ))
        doc.close()
        
        # ---- Unified chunking (identical to current pipeline) ----
        # sementic chunker 
        semantic_splitter = SemanticChunker(
            get_embedding_function(),
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=90,
            min_chunk_size=400   
        )
        # chunking page to page (preseve page information)
        semantic_chunks = semantic_splitter.split_documents(page_docs)
        # for chunk over 1100 tokens, further split it to avoid exceeding vector database limits
        guard_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150,
            separators=["\n\n", "\n", "。", "!", "?", ". ", "! ", "? ", " ", ""]
        )
        chunks = []
        for ch in semantic_chunks:
            if len(ch.page_content) > 1100:
                chunks.extend(guard_splitter.split_documents([ch]))
            else:
                chunks.append(ch)
        # save metadata source information for each chunk
        for chunk in chunks: 
            chunk.metadata["source"] =filename

        print(f"PDF processed: {len(page_docs)} kept pages -> "
              f"{len(semantic_chunks)} semantic chunks -> {len(chunks)} final chunks.")
        return chunks
    
    finally:
        # Clean up the temporary file
        os.unlink(temp_path)