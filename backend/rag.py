from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
import os

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

def search_chunks(query: str, filename:str, k:int=5):
    """
    根据问题，从ChromaDB里找最相关的k个块
    原理：把query也向量化，找向量距离最近的k个块 
    """

    collection_name=filename.replace(".","_").replace(" ","_")  

    db = Chroma(
        collection_name=collection_name,
        embedding_function=get_embedding_function(),
        persist_directory=CHROMA_DIR
    )

    # similarity_search会把query用同一个Embedding模型转成向量,计算它与数据库里所有向量的余弦相似度,返回最相似的k个块
    results = db.similarity_search(query, k=k)

    return results

def search_chunks_with_score(query: str, filename: str, k: int = 5):
    """
    和search_chunks一样，但同时返回相关性分数
    分数是向量距离，越小说明越相关
    """
    collection_name = filename.replace(".","_").replace(" ","_")

    print(f"[DEBUG] Searching in collection: {collection_name}")

    db = Chroma(
        collection_name=collection_name,
        embedding_function=get_embedding_function(),
        persist_directory=CHROMA_DIR
    )

    # 返回 [(Document, score), (Document, score), ...]
    results = db.similarity_search_with_score(query, k=k)

    print(f"[DEBUG] Found {len(results)} chunks")  # 加这行
    if results:
        print(f"[DEBUG] First chunk preview: {results[0][0].page_content[:100]}")
    
    return results

