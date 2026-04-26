# EduPrep Project State

## Project Overview
EduPrep is an AI-based learning platform for international students in Germany.
It follows a structured learning flow: Preview → Learn → Review.

Current phase: Early-stage architecture & system design.

## Completed Work
- FastAPI + PDF提取 + Ollama问答 + React基础界面

## In Progress
- RAG

## Next Steps
- RAG向量搜索: 用 unstructured 替换 PyPDF2，把PDF切成小块，存入ChromaDB向量数据库, langchain + chromadb
- 把现有的 /ask 接口改成真正的 RAG：提问时语义检索最相关的5-6个段落，回答里附上页码来源。
-  Preview模式: 后端新增 /preview 接口，上传PDF后，自动生成一份双语摘要和关键词汇表, 写好Prompt，让Ollama按照固定格式输出
- Quiz测验: 后端新增 /quiz 接口，让Ollama根据PDF内容生成测验，用 localStorage 记录答题历史，进度条显示掌握百分比
- 界面美化1: 用 React Router 拆分成三个独立页面，做左侧导航栏，显示三个模式（Preview / Learn / Review）的切换导航，以及已上传的文件列表。
- 网络搜索功能和来源引用：Tavily API，回答里标注"来源：讲义第X页"或"来源：网络搜索"。
- 界面美化2: 安装 Tailwind CSS，三个模式用不同配色区分（Preview 黄色系、Learn 蓝色系、Review 绿色系），加打字机效果和骨架屏加载。
- 收尾：统一错误处理、Toast 通知、移动端响应式、边界情况测试。


## Key Design Decisions
- Learning flow is strictly sequential: Preview → Learn → Review
- AI acts as both tutor and system guide
- Simplicity is prioritized over feature complexity (MVP first)

