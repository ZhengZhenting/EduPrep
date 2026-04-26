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
- RAG向量搜索: 把PDF切成小块，存入ChromaDB向量数据库, langchain + chromadb
-  Preview模式: 上传PDF后，自动生成一份双语摘要和关键词汇表, 写好Prompt，让Ollama按照固定格式输出
- Quiz测验: 后端新增一个 /quiz 接口，让Ollama根据PDF内容生成测验
- 进度追踪: 用 localStorage 记录每道题的答题情况，计算每个章节的掌握百分比,在界面上显示进度条。错误的题目下次优先出现。
- 界面美化: Tailwind CSS, 做一个左侧边栏，显示三个模式（Preview / Learn / Review）的切换导航，以及已上传的文件列表。
- 网络搜索功能和来源引用：Tavily API，显示pdf页码来源


## Key Design Decisions
- Learning flow is strictly sequential: Preview → Learn → Review
- AI acts as both tutor and system guide
- Simplicity is prioritized over feature complexity (MVP first)

