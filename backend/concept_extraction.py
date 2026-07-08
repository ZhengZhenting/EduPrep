"""
concept_extraction.py — P8: 从一份 PDF 的 chunk 里用 Claude 抽取课程级概念 + 关系。
(Step 2a：只抽取 + 打印，先看质量，暂不写库。)
"""
from __future__ import annotations
import os, json
import anthropic
from dotenv import load_dotenv
from langchain_chroma import Chroma
from rag import get_embedding_function, sanitize_collection_name, CHROMA_DIR
from database import SessionLocal
from models import Course, PdfFile, Concept, ConceptEdge
from typing import List, Literal
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from sqlalchemy.orm import Session

load_dotenv()
MODEL = "claude-sonnet-4-5"
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

class ConceptItem(BaseModel):
    name: str = Field(description="Concept name in German (source language), canonical form")
    description: str = Field(description="One short German sentence describing the concept")

class RelationItem(BaseModel):
    # 'from' 是 Python 关键字，不能直接当字段名 → 字段叫 source，但用 alias 让 JSON 里仍是 "from"
    source: str = Field(alias="from", description="Source concept name (German); must appear in concepts")
    target: str = Field(alias="to", description="Target concept name (German); must appear in concepts")
    type: Literal["is_a", "prerequisite", "part_of", "related"] = Field(description="Relation type")

class ConceptExtraction(BaseModel):
    concepts: List[ConceptItem] = Field(description="Key concepts taught in the material")
    relations: List[RelationItem] = Field(description="Directed relations between the concepts")

class AdjudicationResult(BaseModel):
    same: List[bool] = Field(description="For each pair in order: true if A and B are the SAME concept, else false")

class CrossRelations(BaseModel):
    relations: List[RelationItem] = Field(description="Directed relations that clearly hold between the listed concepts; omit uncertain ones")

VALID_RELATIONS = {"is_a", "prerequisite", "part_of", "related"} # 概念之间edge的四种关系
SIM_THRESHOLD = 0.70          # embedding 候选阈值：低于此不进入裁决

def load_chunks(filename: str) -> list[str]:
    """从 ChromaDB 拿这份 PDF 的所有 chunk 文本。"""
    db = Chroma(
        collection_name=sanitize_collection_name(filename),
        embedding_function=get_embedding_function(),
        persist_directory=CHROMA_DIR,
    )
    return db.get().get("documents", [])


def extract_concepts(filename: str, max_chars: int = 12000) -> dict:
    """一份 PDF → Claude 结构化输出 {concepts, relations}（Pydantic + JsonOutputParser）。"""
    context = "\n\n".join(load_chunks(filename))[:max_chars]
    parser = JsonOutputParser(pydantic_object=ConceptExtraction)

    system_prompt = """You extract a knowledge graph from German university lecture material.
Output ONLY a valid JSON object. Do not wrap in markdown code blocks. No explanation.

Rules:
- Concept names in GERMAN (source language), canonical form.
- Only concepts actually taught in the material; do not invent.
- relation types: is_a (subclass of), prerequisite (learn before), part_of (component of), related (association).
- Every name used in a relation MUST also appear in concepts.
- Focus on the key concepts, not every word."""

    user_prompt = f"""Lecture material:

{context}

{parser.get_format_instructions()}"""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return parser.parse(resp.content[0].text)   # 返回 dict，容错解析


def _cosine(a: list, b: list) -> float:
    """纯 Python 余弦相似度（768 维、几百概念足够快）。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb + 1e-9)

def _append_source(concept: Concept, pdf_file_id: int) -> None:
    """给概念追加来源（去重），重新赋值以标记 JSONB 为脏。
    SQLAlchemy 把"被改过、需要写回数据库"的对象/字段叫 dirty(脏)"""
    refs = list(concept.source_refs or [])
    if not any(r.get("pdf_file_id") == pdf_file_id for r in refs):
        refs.append({"pdf_file_id": pdf_file_id})
        concept.source_refs = refs


def adjudicate_same_batch(pairs: list[dict]) -> list[bool]:
    """一次 Claude 调用裁决多对概念是否"同一"。pairs=[{new_name,new_desc,cand_name,cand_desc}]。"""
    if not pairs:
        return []
    parser = JsonOutputParser(pydantic_object=AdjudicationResult)
    listing = "\n".join(
        f'{i}. A="{p["new_name"]}" ({p["new_desc"]})  vs  B="{p["cand_name"]}" ({p["cand_desc"]})'
        for i, p in enumerate(pairs, 1)
    )
    system = "You judge whether pairs of German technical concepts are the SAME concept (synonyms / identical meaning), NOT merely related."
    user = f"""For each numbered pair decide if A and B are the SAME concept.
Synonyms or identical meaning = same (true). Related-but-different (e.g. 'Euklidische Distanz' vs 'Manhattan Distanz') = not same (false).

Pairs:
{listing}

{parser.get_format_instructions()}
Return exactly {len(pairs)} booleans, in the same order as the pairs."""
    resp = client.messages.create(
        model=MODEL, 
        max_tokens=1000, 
        temperature=0,
        system=system, 
        messages=[{"role": "user", "content": user}],
    )
    verdicts = parser.parse(resp.content[0].text).get("same", [])
    return (list(verdicts) + [False] * len(pairs))[:len(pairs)]   # 对齐长度兜底

def merge_into_graph(course_id: int, pdf_file_id: int, extracted: dict, db: Session) -> tuple[int, int]:
    """三级消歧（精确名 → embedding 候选 → Claude 批量裁决）+ 边去重。返回 (新增概念, 新增边)。"""
    embedder = get_embedding_function()

    # 载入本课程已有概念（含向量），供消歧比对
    existing = db.query(Concept).filter(Concept.course_id == course_id).all()
    existing_by_name: dict[str, Concept] = {c.name: c for c in existing}
    existing_emb: list[tuple[Concept, list]] = [(c, c.embedding) for c in existing if c.embedding]

    name_to_concept: dict[str, Concept] = {}
    pending: list[dict] = []                       # 待新建或待裁决的概念

    concepts: list[dict] = extracted.get("concepts", [])
    for c in concepts:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        desc = (c.get("description") or "").strip()
        hit = existing_by_name.get(name)           # ① 精确名匹配
        if hit:
            _append_source(hit, pdf_file_id)
            name_to_concept[name] = hit
            continue
        vec = embedder.embed_query(f"{name}: {desc}" if desc else name)   # ② embedding 找候选
        best_c, best_sim = None, -1.0
        for ec, eemb in existing_emb:
            sim = _cosine(vec, eemb)
            if sim > best_sim:
                best_c, best_sim = ec, sim
        pending.append({
            "name": name, "desc": desc, "vec": vec,
            "candidate": best_c if best_sim >= SIM_THRESHOLD else None,
        })

    # ③ 批量裁决（只问有候选的）
    to_judge = [p for p in pending if p["candidate"] is not None]
    pairs = [{"new_name": p["name"], "new_desc": p["desc"],
              "cand_name": p["candidate"].name, "cand_desc": p["candidate"].description or ""}
             for p in to_judge]
    verdicts = adjudicate_same_batch(pairs)
    judged = {id(p): v for p, v in zip(to_judge, verdicts)}

    # 定稿：合并 or 新建
    new_concepts = 0
    for p in pending:
        cand = p["candidate"]
        if cand is not None and judged.get(id(p), False):     # Claude 判同一 → 合并
            _append_source(cand, pdf_file_id)
            name_to_concept[p["name"]] = cand
        else:                                                  # 新建
            concept = Concept(
                course_id=course_id, name=p["name"],
                description=p["desc"] or None, embedding=p["vec"],
                source_refs=[{"pdf_file_id": pdf_file_id}],
            )
            db.add(concept); db.flush()
            new_concepts += 1
            name_to_concept[p["name"]] = concept
            existing_emb.append((concept, p["vec"]))           # 让本次后续概念也能匹配到它

    # 边（逻辑不变）
    new_edges = 0
    relations: list[dict] = extracted.get("relations", [])
    for r in relations:
        rtype = r.get("type")
        if rtype not in VALID_RELATIONS:
            continue
        f = name_to_concept.get((r.get("from") or "").strip())
        t = name_to_concept.get((r.get("to") or "").strip())
        if not f or not t or f.id == t.id:
            continue
        exists = db.query(ConceptEdge).filter_by(
            from_concept_id=f.id, to_concept_id=t.id, relation_type=rtype
        ).first()
        if not exists:
            db.add(ConceptEdge(course_id=course_id, from_concept_id=f.id,
                               to_concept_id=t.id, relation_type=rtype))
            new_edges += 1

    db.commit()
    return new_concepts, new_edges

def link_cross_pdf(course_id: int, pdf_file_id: int, db: Session, top_k: int = 5) -> int:
    """给本份 PDF 的概念，用 embedding 找课程里最近的其它概念，让 Claude 判关系，建跨 PDF 边。返回新增边数。"""
    all_c = db.query(Concept).filter(Concept.course_id == course_id).all()
    by_id = {c.id: c for c in all_c}
    by_name = {c.name: c for c in all_c}
    emb = {c.id: c.embedding for c in all_c if c.embedding}

    # 本份 PDF 涉及的概念（source_refs 含本 pdf_file_id）
    involved_ids = [c.id for c in all_c
                    if any(r.get("pdf_file_id") == pdf_file_id for r in (c.source_refs or []))]
    # 候选只从"别的 PDF"来的概念里选（否则单份 PDF 会自己连自己）
    other_ids = {c.id for c in all_c
                 if any(r.get("pdf_file_id") != pdf_file_id for r in (c.source_refs or []))}

    # ① 每个涉及概念取 top-K 最近邻，收集无序候选对
    pair_sim: dict = {}
    for cid in involved_ids:
        if cid not in emb:
            continue
        sims = sorted(
            ((oid, _cosine(emb[cid], emb[oid])) for oid in other_ids if oid != cid and oid in emb),
            key=lambda x: x[1], reverse=True,
        )
        for oid, sim in sims[:top_k]:
            key = tuple(sorted((cid, oid)))
            pair_sim[key] = max(pair_sim.get(key, 0.0), sim)   # 相似度留作边权重
    if not pair_sim:
        return 0
    pair_ids = pair_sim.keys()

    # ② 给 Claude：涉及概念清单 + 候选对，批量判关系
    involved_all = {i for pair in pair_ids for i in pair}
    concept_lines = "\n".join(f'- "{by_id[i].name}": {by_id[i].description or ""}' for i in involved_all)
    pair_lines = "\n".join(f'"{by_id[a].name}" <-> "{by_id[b].name}"' for a, b in pair_ids)

    parser = JsonOutputParser(pydantic_object=CrossRelations)
    system = "You find directed relations between German technical concepts from the SAME course, to connect a knowledge graph across lecture PDFs."
    user = f"""Concepts (name: description):
{concept_lines}

Candidate pairs (a relation may or may not exist for each):
{pair_lines}

For pairs with a CLEAR relation, output a directed edge. Types:
- is_a: from is a kind/subclass of to
- prerequisite: from must be learned before to
- part_of: from is a component of to
- related: ONLY a strong, specific association — otherwise omit it.
Strongly prefer is_a / prerequisite / part_of. Do NOT emit related for loose or obvious links. 
Only clear relations; omit uncertain pairs. Use the EXACT concept names above.

{parser.get_format_instructions()}"""
    resp = client.messages.create(
        model=MODEL, 
        max_tokens=4000, 
        temperature=0,
        system=system, 
        messages=[{"role": "user", "content": user}],
    )
    rels: list[dict] = parser.parse(resp.content[0].text).get("relations", [])

    # ③ 建边（名字→概念，去重，跳过自环/未知）
    new_edges = 0
    for r in rels:
        rtype = r.get("type")
        if rtype not in VALID_RELATIONS:
            continue
        f = by_name.get((r.get("from") or "").strip())
        t = by_name.get((r.get("to") or "").strip())
        if not f or not t or f.id == t.id:
            continue
        exists = db.query(ConceptEdge).filter_by(
            from_concept_id=f.id, to_concept_id=t.id, relation_type=rtype
        ).first()
        if not exists:
            w = pair_sim.get(tuple(sorted((f.id, t.id))), 1.0)      # embedding 相似度当权重
            db.add(ConceptEdge(course_id=course_id, from_concept_id=f.id,
                               to_concept_id=t.id, relation_type=rtype, weight=round(w, 3)))
            new_edges += 1
    db.commit()
    return new_edges


if __name__ == "__main__":
    import sys
    filename = sys.argv[1] if len(sys.argv) > 1 else "MachineLearning-SimpleClassifiers-NCC.pdf"
    db = SessionLocal()
    try:
        course = db.query(Course).first()
        if not course:
            raise SystemExit("没有课程，先跑 init_db.py")
        pdf = db.query(PdfFile).filter_by(course_id=course.id, filename=filename).first()
        if not pdf:
            pdf = PdfFile(course_id=course.id, filename=filename, chunk_count=0)
            db.add(pdf); db.commit(); db.refresh(pdf)
        print(f"course_id={course.id}  pdf_file_id={pdf.id}")
        extracted = extract_concepts(filename)
        nc, ne = merge_into_graph(course.id, pdf.id, extracted, db)
        ncross = link_cross_pdf(course.id, pdf.id, db)
        print(f"新增概念 {nc}，PDF内新增边 {ne}，跨PDF新增边 {ncross}")
    finally:
        db.close()