from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
import os
import re

CHROMA_DIR = "./chroma_db" 
EMBEDDING_MODEL = "nomic-embed-text"

def get_embedding_function():
    """docstring ：
    返回Ollama的Embedding函数模型，
    每次调用这个函数，都会使用同一个Embedding模型，
    关键点在于存块时用什么Embedding模型，查询时就必须用同一个模型，否则向量空间不一致，查询结果会很差甚至完全不相关
    把它封装成函数，是为了保证两处（store,search）都调用同一个地方
    """
    return OllamaEmbeddings(model=EMBEDDING_MODEL)


def store_chunks(chunks:list, filename: str):
    """
    把PDF切块存入ChromaDB
    用filename作为collection名，每个PDF独立存储
    """

    # collection名不能有特殊字符
    collection_name=filename.replace(".","_").replace(" ","_")  

    # 如果这个PDF之前存过，先删除旧数据再重新存
    db=Chroma(
        collection_name=collection_name,
        embedding_function=get_embedding_function(),
        persist_directory=CHROMA_DIR
    )
    db.delete_collection()  

    # 重新创建collection并存入新数据
    # 这里的from_documents方法会自动计算每个chunk的embedding并存储到ChromaDB
    db=Chroma.from_documents(
        documents=chunks,
        embedding=get_embedding_function(),
        collection_name=collection_name,
        persist_directory=CHROMA_DIR
    )

    print(f"Chunks stored in ChromaDB: {len(chunks)} chunks, collection name = {collection_name}.")
    return collection_name


def sanitize_collection_name(filename: str) -> str:
    return filename.replace(".", "_").replace(" ", "_")

def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r'[a-z0-9äöüß]+|[\u4e00-\u9fff]', text) #分词
    return tokens

def _build_bm25(docs:list[Document]) -> tuple[BM25Okapi, list[Document]]:
    tokenized = [_tokenize(doc.page_content) for doc in docs] #把每个 chunk 的文字都分词，变成词列表的列表
    bm25 = BM25Okapi(tokenized) #建立BM25索引
    return bm25, docs #BM25 存词频，docs 存原始内容

def _bm25_search(
        query: str,
        bm25: BM25Okapi,
        docs: list[Document],
        k: int = 5
)->list[tuple[Document, float]]:
    """
    BM25 关键词检索
    返回 [(Document, score), ...] 分数越高越相关
    """
    query_tokens = _tokenize(query)
    scores = bm25.get_scores(query_tokens)
    scored_docs = list(zip(docs, scores))
    scored_docs = sorted(
        zip(docs, scores),
        key=lambda x: x[1],
        reverse=True
    )
    return scored_docs[:k]

def _reciprocal_rank_fusion(
        vector_results: list[tuple[Document, float]],
        bm25_results: list[tuple[Document, float]],
        k: int=60
)->list[tuple[Document, float]]:
    """
    RRF（倒数排名融合）算法
    把向量检索和 BM25 的结果融合成一个排名

    RRF 公式：score = Σ 1/(k + rank)
    k=60 是经验常数，来自 RRF 论文
    """
    rrf_scores = {}
    doc_map = {}

    for rank, (doc, _) in enumerate(vector_results,start=1):
        key=doc.page_content
        rrf_scores[key] = rrf_scores.get(key, 0) + 1/(k + rank)
        doc_map[key] = doc

    for rank, (doc, _) in enumerate(bm25_results,start=1):
        key=doc.page_content
        rrf_scores[key] = rrf_scores.get(key, 0) + 1/(k + rank)
        doc_map[key] = doc

    sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    return [(doc_map[key], score) for key, score in sorted_items]



def search_chunks_with_score(query: str, filename: str, k: int = 5)-> tuple[list[tuple[Document, float]], float]:
    """
    混合检索：向量检索 + BM25，用 RRF 融合排名
    """
    collection_name = sanitize_collection_name(filename)

    # vector search
    db=Chroma(
        collection_name=collection_name,
        embedding_function=get_embedding_function(),
        persist_directory=CHROMA_DIR
    )
    vector_results = db.similarity_search_with_score(query, k=k*2)  
    print(f"[Vector] Found {len(vector_results)} chunks") 
    if not vector_results:
        return [], 999.0
    best_cosine_score = min(score for _, score in vector_results)
    print(f"[Vector] Best cosine score: {best_cosine_score}")

    # bm25 search
    all_docs_results = db.similarity_search(query, k=100)
    if all_docs_results:
        bm25, docs = _build_bm25(all_docs_results)
        bm25_results = _bm25_search(query, bm25, docs, k=k*2)
        print(f"[BM25] Found {len(bm25_results)} chunks")
    else:
        bm25_results = []

    # RRF fused
    results = _reciprocal_rank_fusion(vector_results, bm25_results, k=k*2)
    final_results = results[:k]
    
    print(f"[Hybrid] Final top-{k} chunks selected")
    return final_results, best_cosine_score

def search_chunks(query: str, filename:str, k:int=5) -> list[Document]:
    results, _ = search_chunks_with_score(query, filename, k)
    return [doc for doc, _ in results] # 只返回文档，丢掉分数

