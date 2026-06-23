"""
generate.py — Reproduce the /ask PDF-answer step for offline evaluation.

This mirrors the PDF-answer generation in main.py's /ask, but stripped of
per-user state (memory, weak concepts, history) so the eval is clean and
self-contained — no HTTP, no DB, no user context.

It returns three things the rest of the eval needs:
  - answer      : the model's Chinese answer (what the user would read)
  - pages_used  : pages the answer is grounded on (the frontend's PagesFooter;
                  used as the 'cited pages' for the citation metric)
  - sources_text: the retrieved chunks, page-tagged, fed to the judge so it can
                  check faithfulness against what was actually available
"""

from __future__ import annotations
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

GEN_MODEL = "claude-sonnet-4-5"          # SAME model the product uses to answer
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def build_context(results: list, max_chars: int = 2000) -> tuple[str, str, list[int]]:
    """From retrieval output build: the raw context, a page-tagged source block,
    and the sorted list of pages used.

    `results` is [(Document, score), ...] from search_chunks_with_score.
    Note the 0-indexed -> 1-indexed page conversion (same as run_eval).
    """
    context_parts = []
    tagged_parts = []
    pages_used = set()

    for chunk, _score in results:
        page = chunk.metadata.get("page", 0) + 1     # 0-indexed -> 1-indexed
        context_parts.append(chunk.page_content)
        tagged_parts.append(f"[Page {page}] {chunk.page_content}")
        pages_used.add(page)

    context = "\n\n---\n\n".join(context_parts)[:max_chars]   # cap like main.py
    sources_text = "\n\n".join(tagged_parts)[:max_chars]
    return context, sources_text, sorted(pages_used)


def generate_pdf_answer(question: str, results: list) -> dict:
    """Generate the PDF-grounded answer for one question (mirrors /ask)."""
    context, sources_text, pages_used = build_context(results)

    # Same instructions as main.py's /ask, minus personalization
    system_prompt = """You are a learning assistant helping international students understand German lecture materials.
        Your task is to answer the student's question based on the provided lecture content.

        Rules:
        - Answer in Chinese
        - Be concise and direct, only address what the question asks
        - Do not proactively add diagrams, formulas, or code blocks
        - If the lecture content is relevant, answer strictly from it
        - If the lecture content is not relevant to the question, say "讲义中未找到直接相关内容。"
        - Keep the answer under 200 characters"""

    user_prompt = f"""Lecture content:
        {context}

        Student question: {question}"""

    # temperature=0 for a REPRODUCIBLE baseline. Production uses the default
    # (non-deterministic); we trade a little realism for stable, comparable runs.
    response = _client.messages.create(
        model=GEN_MODEL,
        max_tokens=400,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    answer = response.content[0].text.strip()

    return {
        "answer": answer,
        "pages_used": pages_used,
        "sources_text": sources_text,
    }


def answer_with_citation(gen: dict) -> str:
    """Append the page footer to the answer, the way the UI shows PagesFooter.

    This is what we hand to the judge as the 'generated_answer', so its CITATION
    dimension has concrete cited pages to compare against relevant_pages.
    """
    if gen["pages_used"]:
        pages = ", ".join(str(p) for p in gen["pages_used"])
        return f"{gen['answer']}\n[Cited pages: {pages}]"
    return gen["answer"]


# --- smoke test: needs Ollama (retrieval) + ANTHROPIC_API_KEY + ingested PDF ---
if __name__ == "__main__":
    from rag import search_chunks_with_score

    q = "Was ist Zero-shot Prompting?"
    results, _ = search_chunks_with_score(q, "LLM-Prompting.pdf", k=5)
    gen = generate_pdf_answer(q, results)
    print("PAGES:", gen["pages_used"])
    print("ANSWER:", gen["answer"])
    print("FOR JUDGE:\n", answer_with_citation(gen))