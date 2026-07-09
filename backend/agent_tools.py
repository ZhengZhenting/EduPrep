"""
agent_tools.py — P11: LangGraph agent 用的工具函数。

三个工具，每个都是"绑定了本次请求上下文(filename/course_id)"的闭包，
用 @tool 装饰后交给 LLM 做工具调用决策：
  - search_pdf: 复用现有 hybrid 检索(rag.py)
  - query_knowledge_graph: 查 P8 已建的概念图谱(1 跳关系)
  - get_concept_mastery: 查 P10 的掌握度(现阶段大概率为空，P10 未实现)

工具本身是普通函数，不是 agent —— 由 LangGraph 的 ToolNode 统一执行。
"""
from __future__ import annotations
import threading
from langchain_core.tools import tool
from database import SessionLocal
from models import Concept, ConceptEdge, ConceptMastery
from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# LangGraph 的 ToolNode 会并发执行同一条 AI 消息里的多个工具调用（线程池）。
# rag.py 每次调用都新建一个 Chroma(...) 客户端，而 ChromaDB 底层的 SharedSystemClient
# 并发初始化同一路径时有线程安全 bug（会报 KeyError: './chroma_db'）。
# 用锁把"同一进程内对 Chroma 的访问"串行化，避免并发初始化竞态。
_chroma_lock = threading.Lock()
from rag import get_embedding_function, search_chunks_with_score
from concept_extraction import _cosine


def _find_concept(course_id: int, term: str):
    """按名字/embedding 在课程图谱里找最相关的一个概念。找不到返回 None。"""
    db = SessionLocal()
    try:
        concepts = db.query(Concept).filter(Concept.course_id == course_id).all()
        if not concepts:
            return None, db
        # ① 精确/包含名匹配（最快、最可靠）
        for c in concepts:
            if term.strip().lower() in c.name.lower() or c.name.lower() in term.strip().lower():
                return c, db
        # ② 否则用 embedding 找最相似的
        emb = get_embedding_function()
        vec = emb.embed_query(term)
        best, best_sim = None, -1.0
        for c in concepts:
            if not c.embedding:
                continue
            sim = _cosine(vec, c.embedding)
            if sim > best_sim:
                best, best_sim = c, sim
        print(f"[agent_tools] concept lookup '{term}' -> best match "
              f"{'(none)' if not best else best.name} sim={best_sim:.3f}")
        return (best if best_sim >= 0.6 else None), db
    except Exception as e:
        print(f"[agent_tools] _find_concept error: {e}")
        db.close()
        raise


def build_tools(filename: str, course_id: int) -> list:
    """工厂函数：绑定本次请求的 filename/course_id，返回该请求专属的工具列表。"""

    @tool
    def search_pdf(query: str) -> str:
        """Search the current lecture PDF for content relevant to the query.
        Use this to find lecture text that can ground your answer. Returns
        page-tagged excerpts like '[Page 4] ...'."""
        print(f"[tool:search_pdf] query={query!r} filename={filename}")
        with _chroma_lock:  # 串行化 Chroma 访问，避免并发工具调用触发底层竞态 KeyError
            results, best_score = search_chunks_with_score(query, filename, k=5)
        if not results:
            print("[tool:search_pdf] no chunks found")
            return "No relevant content found in this PDF."
        parts = []
        for chunk, _score in results:
            page = chunk.metadata.get("page", 0) + 1  # 0-indexed -> 1-indexed
            parts.append(f"[Page {page}] {chunk.page_content}")
        out = "\n\n---\n\n".join(parts)[:2000]
        print(f"[tool:search_pdf] returned {len(results)} chunks, best_score={best_score:.4f}")
        return out

    @tool
    def search_web(query: str) -> str:
        """
    Search reliable external sources.

    Use when the lecture does not sufficiently explain a concept,
    when current information is needed,
    or when search_pdf only returns a passing mention.

    Input:
        English or German search query.

    Returns:
        Top search results with URLs.
    """
        print(f"[tool:search_web] query={query!r}")
        try:
            client = TavilyClient(api_key=TAVILY_API_KEY)

            results = client.search(
            query=query,
            max_results=3,
            search_depth="basic",
            )

            output = []
            
            for r in results.get("results", []):
                output.append(
                f"""from: {r['url']}\ncontent: {r['content']}"""
            )
            print(f"[tool:search_web] returned {len(output)} results")
            if not output:
                return "No useful web results found."
            return "\n\n---\n\n".join(output)
        except Exception as e:
                print("[tool:search_web] ERROR", e)
                return f"Web Search Error: {e}"


    @tool
    def query_knowledge_graph(concept_term: str) -> str:
        """Query the course-level knowledge graph for a concept: its short
        definition/description AND how it relates to other concepts
        (is_a / prerequisite / part_of / related edges, 1-hop). Use this for
        ANY question that names a specific technical term or concept — both
        plain "what is X" definition questions and questions about how one
        concept connects to / depends on another. Prefer this alongside
        search_pdf when the question centers on a named concept."""
        print(f"[tool:query_knowledge_graph] term={concept_term!r} course_id={course_id}")
        concept, db = _find_concept(course_id, concept_term)
        try:
            if not concept:
                print("[tool:query_knowledge_graph] no matching concept")
                return f"No concept matching '{concept_term}' found in this course's knowledge graph."
            edges = db.query(ConceptEdge).filter(
                ConceptEdge.course_id == course_id,
            ).filter(
                (ConceptEdge.from_concept_id == concept.id) | (ConceptEdge.to_concept_id == concept.id)
            ).all()
            if not edges:
                print(f"[tool:query_knowledge_graph] concept '{concept.name}' has no edges")
                return f"Concept '{concept.name}' found, but has no recorded relations yet."
            id_to_name = {c.id: c.name for c in db.query(Concept).filter(Concept.course_id == course_id).all()}
            lines = [f"{id_to_name[e.from_concept_id]} --{e.relation_type}--> {id_to_name[e.to_concept_id]}"
                     for e in edges]
            print(f"[tool:query_knowledge_graph] concept='{concept.name}' edges={len(edges)}")
            return f"Concept: {concept.name} ({concept.description or 'no description'})\nRelations:\n" + "\n".join(lines)
        finally:
            db.close()

    @tool
    def get_concept_mastery(concept_term: str) -> str:
        """Look up the student's mastery level for a concept in this course
        (from spaced-repetition tracking). May return 'no data yet' if the
        mastery-tracking feature (P10) hasn't been populated for this concept."""
        print(f"[tool:get_concept_mastery] term={concept_term!r} course_id={course_id}")
        concept, db = _find_concept(course_id, concept_term)
        try:
            if not concept:
                return f"No concept matching '{concept_term}' found."
            m = db.query(ConceptMastery).filter_by(course_id=course_id, concept_id=concept.id).first()
            if not m:
                print(f"[tool:get_concept_mastery] no mastery row for '{concept.name}' (P10 not populated yet)")
                return f"No mastery data yet for '{concept.name}' (mastery tracking not yet populated)."
            print(f"[tool:get_concept_mastery] '{concept.name}' mastery_prob={m.mastery_prob}")
            return f"Concept '{concept.name}': mastery_prob={m.mastery_prob:.2f} (0=weak, 1=mastered)."
        finally:
            db.close()

    

    return [search_pdf, query_knowledge_graph, get_concept_mastery,search_web,]