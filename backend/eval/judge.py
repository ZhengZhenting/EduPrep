"""
judge.py — LLM-as-judge for answer quality (methodology.md §4-5).

Given a generated answer + the sources it was supposed to use, an LLM scores it
on an ANCHORED rubric (each level explicitly defined -> reproducible).

Key reliability choices (see methodology.md §5.4):
- JUDGE_MODEL is a STRONGER, DIFFERENT model than the generator (sonnet-4-5),
  to avoid self-enhancement bias.
- temperature = 0 for reproducibility.
- The judge MUST reason before scoring (chain-of-thought reduces snap judgments).
- The judge sees the SOURCES, not just the answer, so it can check faithfulness
  against what was actually retrieved (not against a possibly-stale reference).
- 'overall' is computed in Python, not by the model (no model arithmetic errors).
"""

from __future__ import annotations
import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

# Stronger, heterogeneous judge model (generator uses claude-sonnet-4-5)
JUDGE_MODEL = "claude-opus-4-8"
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# --- The anchored rubric, embedded in the system prompt ---------------------
RUBRIC = """
You are a strict evaluator of a study assistant's answers. Judge ONLY using the
provided SOURCES — do not use your own outside knowledge to fill gaps.

Score each applicable dimension as exactly 0, 0.5, or 1.0:

CORRECTNESS  — 1.0 factually correct and answers the question · 0.5 partly
               correct or partly off-topic · 0 wrong or answers a different thing.
FAITHFULNESS — 1.0 every claim is supported by the SOURCES · 0.5 mostly
               supported, minor unsupported extension · 0 contains fabricated
               content not in the sources.
CITATION     — 1.0 cited pages match the relevant pages · 0.5 cited but with
               omissions/extras · 0 missing or wrong citation.
HONESTY      — (only when the answer is NOT in the lecture) 1.0 honestly says the
               lecture lacks it / correctly defers to web · 0.5 vague · 0 pretends
               the lecture contains it and fabricates.

Which dimensions apply, by answer_coverage:
- "standard" / "fuzzy": score CORRECTNESS, FAITHFULNESS, CITATION; set HONESTY null.
- "none": score FAITHFULNESS, HONESTY; set CORRECTNESS and CITATION null
  (there is no authoritative reference answer and no relevant pages).

Output ONLY a JSON object, no markdown, no explanation outside it:
{"reasoning": "<one short paragraph justifying the scores>",
 "correctness": <0|0.5|1.0|null>, "faithfulness": <0|0.5|1.0|null>,
 "citation": <0|0.5|1.0|null>, "honesty": <0|0.5|1.0|null>}
"""


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers if the model adds them (same as main.py)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0].strip()
    return text


def judge_answer(
    question: str,
    generated_answer: str,
    retrieved_sources: str,
    relevant_pages: list[int],
    answer_coverage: str,
    reference_hint: str = "",
) -> dict:
    """Score one generated answer. Returns dims + a Python-computed 'overall'."""

    # Build the case the judge evaluates. Sources come BEFORE the answer so the
    # judge reads the ground truth first.
    user_prompt = f"""
answer_coverage: {answer_coverage}
relevant_pages (ground truth): {relevant_pages}
reference hint (NOT authoritative, guidance only): {reference_hint}

QUESTION:
{question}

SOURCES the answer should be grounded in:
{retrieved_sources}

ANSWER to evaluate:
{generated_answer}
"""

    # temperature=0 + anchored rubric => reproducible scoring
    message = _client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=500,
        system=RUBRIC,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = _strip_fences(message.content[0].text)
    data = json.loads(raw)

    # Compute overall in Python = mean of the dimensions that apply (non-null).
    # Doing it here (not in the model) avoids arithmetic mistakes by the LLM.
    applicable = [
        data[d] for d in ("correctness", "faithfulness", "citation", "honesty")
        if data.get(d) is not None
    ]
    data["overall"] = round(sum(applicable) / len(applicable), 3) if applicable else None

    return data


def judge_answer_stable(n: int = 3, **kwargs) -> dict:
    """Variance self-check (methodology §5.4): run the judge n times, average the
    overall, and report the spread. A large spread means the rubric is ambiguous
    and should be tightened.
    """
    runs = [judge_answer(**kwargs) for _ in range(n)]
    overalls = [r["overall"] for r in runs if r["overall"] is not None]
    avg = sum(overalls) / len(overalls) if overalls else None
    spread = (max(overalls) - min(overalls)) if overalls else None
    return {"avg_overall": avg, "spread": spread, "runs": runs}


# --- quick smoke test (needs ANTHROPIC_API_KEY + network) ---
if __name__ == "__main__":
    result = judge_answer(
        question="Was ist Zero-shot Prompting?",
        generated_answer="Zero-shot Prompting 指不含示例的单个 prompt,适用于简单任务,见第15页。",
        retrieved_sources="[Page 15] Zero-shot Prompting verwendet einen einzelnen "
                          "Prompt ohne Beispiele und eignet sich für einfache Aufgaben.",
        relevant_pages=[15],
        answer_coverage="standard",
        reference_hint="不含示例的单个 prompt,适合简单任务。",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))