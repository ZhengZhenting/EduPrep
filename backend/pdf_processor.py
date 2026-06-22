from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from rag import get_embedding_function   # 复用检索同款 embedding 模型
import tempfile
import os 

def process_pdf(file_bytes: bytes, filename:str) -> list:
    """
    接收PDF的二进制内容，返回切好的文本块列表
    每个块包含：文字内容 + 页码元数据
    """

    # PyPDFLoader需要读取文件路径，不能直接读二进制,所以先把上传的文件临时保存到磁盘
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(file_bytes)
        temp_path = temp_file.name

    try:
        # 用LangChain的PyPDFLoader加载PDF,自动保留每页的页码信息
        loader = PyPDFLoader(temp_path)
        pages = loader.load()

        # sementic chunker 
        semantic_splitter = SemanticChunker(
            get_embedding_function(),
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=90,
            min_chunk_size=400   
        )
        # chunking page to page (preseve page information)
        semantic_chunks = semantic_splitter.split_documents(pages)
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

        print(f"PDF processed: {len(pages)} pages -> "
              f"{len(semantic_chunks)} semantic chunks -> {len(chunks)} final chunks.")
        return chunks
    
    finally:
        # Clean up the temporary file
        os.unlink(temp_path)