from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import tempfile
import os # operating system：Python内置的标准库，提供了一系列和操作系统交互的功能

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

        # 用RecursiveCharacterTextSplitter切块
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800, 
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", ""]) # 优先在段落、句子的边界处切割，保持语义完整
        chunks = splitter.split_documents(pages) # 这里的输入是LangChain的Document对象列表，每个Document对象都有page_content和metadata属性

        for chunk in chunks:
            chunk.metadata["source"]=filename  # 在metadata中保留文件名信息，方便后续追踪来源

        print(f"PDF processed: {len(pages)} pages split into {len(chunks)} chunks.")
        return chunks
    
    finally:
        # Clean up the temporary file
        os.unlink(temp_path)