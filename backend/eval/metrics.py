"""
metrics.py — Retrieval-side evaluation metrics for the RAG golden-dataset eval.

Pure functions only: they take page-number lists and return scores.
No DB, no LLM, no I/O — so they are trivial to unit-test.

Convention:
- `retrieved_pages`: page number of each retrieved chunk, in RANK ORDER
   (rank 1 = best match first). May contain duplicates, since several
   chunks can come from the same page.
- `relevant_pages`:  ground-truth pages from the golden dataset.
- A `None` return means "not applicable" (e.g. 'none'-type questions that
   have no relevant pages — retrieval metrics are skipped for them).
"""

from __future__ import annotations
from typing import Iterable, Sequence, Optional

# 该检索到的页里,有几成出现在了前 k 个结果中(测"有没有漏掉该找的页")
def recall_at_k(
    retrieved_pages: Sequence[int],
    relevant_pages: Iterable[int],
    k: int = 5,
) -> Optional[float]:
    """Fraction of the ground-truth pages that appear in the top-k results.

    recall@k = |relevant ∩ retrieved_top_k| / |relevant|
    Answers the question: 'did we miss any page we needed?'
    """
    relevant = set(relevant_pages)
    #'none'-type questions have no relevant pages -> metric not applicable
    if not relevant:
        return None

    # Dedup by page: recall cares about page COVERAGE, not how many chunks hit it
    top_k_pages = set(retrieved_pages[:k])

    # Intersection size over total relevant
    return len(top_k_pages & relevant) / len(relevant)

#前 k 个检索结果里,有几成命中了相关页,捞回来的有多少是有用的
def precision_at_k(
    retrieved_pages: Sequence[int],
    relevant_pages: Iterable[int],
    k: int = 5,
) -> Optional[float]:
    """Fraction of the top-k retrieved chunks that are on a relevant page.

    precision@k = (# of top-k chunks whose page is relevant) / k
    Answers the question: 'how much junk did we pull in?'
    """
    relevant = set(relevant_pages)
    if not relevant:
        return None

    top_k = retrieved_pages[:k] # keep POSITIONS (duplicates matter here)
    if not top_k:
        return 0.0

    # Count positional hits, not unique pages (a page hit twice counts twice)
    hits = sum(1 for page in top_k if page in relevant)

    return hits / len(top_k)

#第一个相关结果排在第几位,取其倒数(测"有用结果排得够不够靠前");整批求平均就是 MRR
def reciprocal_rank(
    retrieved_pages: Sequence[int],
    relevant_pages: Iterable[int],
) -> Optional[float]:
    """Reciprocal of the rank of the FIRST relevant result. (Per-question RR.)

    RR = 1 / rank_of_first_hit  (0.0 if no relevant page is retrieved at all)
    Answers the question: 'is the first useful hit near the top?'
    The mean of RR over all questions is the MRR.
    """
    relevant = set(relevant_pages)
    if not relevant:
        return None

    # Walk results from rank 1; return on the first relevant page
    for rank, page in enumerate(retrieved_pages, start=1):
        if page in relevant:
            return 1.0 / rank

    # No relevant page found anywhere in the results
    return 0.0

#对一批分数求平均,自动跳过 None(不适用的题),用来聚合各指标和把单题 RR 汇成 MRR
def mean_ignore_none(values: Iterable[Optional[float]]) -> Optional[float]:
    """Average a list of per-question scores, skipping None (N/A) entries.

    Used to turn per-question RR into MRR, and to aggregate recall/precision
    across the dataset while ignoring 'none'-type questions.
    """
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)