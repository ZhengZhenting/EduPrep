# ADR 0003 — LLM-Decided Web Search (replacing the cosine-distance threshold)

- **Status:** Accepted
- **Date:** 2026-06-22
- **Area:** `/ask` flow (`backend/main.py`), tools (`backend/tools.py`)
- **Supersedes:** the previous "score-based routing" decision

## Context

`/ask` originally decided whether to supplement the PDF answer with a Tavily web
search using a **fixed cosine-distance threshold**:

```
best_cosine_score >= 0.9  →  run search_web() and add a web supplement
best_cosine_score <  0.9  →  PDF answer only
```

This was deterministic and cheap (no extra LLM call), but had two weaknesses:

- **0.9 is arbitrary** and brittle across subjects and embedding behaviour.
- It only inspects *vector distance*, not whether the retrieved chunks actually
  answer the question. A chunk at distance 0.85 may be off-topic yet still
  suppress a needed web search; a chunk at 0.92 may answer fully yet trigger an
  unnecessary one.

We also wanted the user-facing answer to keep **PDF and web content clearly and
separately sourced** (page numbers vs. URLs), not merged into one blob.

## Decision

Replace the threshold with an **LLM-made decision via Anthropic tool use**, while
keeping the rest of the flow intact.

1. **Always** generate the PDF answer from the retrieved chunks first
   (guarantees a lecture-grounded "part 1" with page numbers).
2. **Decision step:** call Claude with `search_web` registered as an Anthropic
   tool (manual `input_schema`) and `tool_choice={"type": "auto"}`. The model
   either answers from the lecture (no tool call) or emits a `tool_use` block
   with a search query.
3. **If the tool is requested:** run Tavily once and generate the web supplement
   as a *separate*, constrained generation (web "part 2" with source URLs).

### Preventing over-calling the tool

Tool use's main failure mode is the model searching when it shouldn't. Three
guards, stacked:

- `tool_choice={"type": "auto"}` — never forced.
- A decision system prompt that **defaults to trusting the lecture** and only
  searches when the lecture clearly cannot answer or the question needs current /
  external information.
- A **hard cap of one `search_web` execution** per request (no loop).

### Two-part, separately-sourced answer

- Response returns `pdf_answer` and `web_supplement` as **separate fields**
  (`answer` is kept as an alias of `pdf_answer` for backward compatibility).
- `sources` is `{pages, urls, web_supplement}`. The assistant `message.content`
  stores `pdf_answer` only; the web part lives in `sources.web_supplement` so
  reloaded history can also render both parts (no DB migration needed).
- The frontend `LearnTab` renders two distinct blocks: PDF answer + page numbers,
  and (when present) web supplement + URLs.

## Consequences

**Positive**

- The decision is semantic (does the retrieved content answer the question?)
  rather than a single distance number — more accurate routing.
- Source reliability is explicit: lecture vs. web content are visually and
  structurally separated, each with its own provenance.
- Aligns with the roadmap's "Learn → Agent" direction (real tool-use decisioning
  instead of hand-coded routing).

**Negative / costs**

- **One extra Claude call:** no-web path is now 2 calls (PDF answer + decision),
  web path is 3 (PDF answer + decision + supplement), vs. 1–2 before. Accepted in
  exchange for reliability and a guaranteed lecture-grounded part.
- **Slightly less deterministic:** the model may occasionally over- or
  under-search. Mitigated by the prompt + hard cap.
- `best_cosine_score` is still computed and logged in the LangFuse
  `rag-retrieval` span, but no longer routes the flow; a new `web-decision`
  generation span records whether the tool fired and the chosen query.

## Alternatives considered

- **Keep the threshold, just tune 0.9** — still a single brittle number; doesn't
  inspect content relevance.
- **Single agentic tool-use loop that merges PDF + web into one final answer** —
  fewer calls, but fights the requirement to keep the two parts separately
  sourced; rejected (see "Option A vs B" trade-off; Option A chosen for
  reliability and guaranteed PDF part).
