import os
import re
from dotenv import load_dotenv
from langchain_core.tools import tool
from tavily import TavilyClient

load_dotenv()
OLLAMA_URL = os.getenv("OLLAMA_URL")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Helper functions
def _strip_think_blocks(text: str) -> str:
    """剥离<think>...</think>块，保留其中的内容，但丢弃块标签和块内的任何文本。"""
    if "</think>" in text:
        text = text.split("</think>")[-1]
    return text.strip() 

def _extract_mermaid_body(raw: str) -> str:    
    """从原始文本中提取Mermaid图表的主体内容，去掉可能的Markdown代码块标记和多余的空白。"""
    text = raw.strip()
    text = re.sub(r"^```(?:mermaid)?\s*\n?", "", text)  # remove beginning ```mermaid or ```
    text = re.sub(r"\n?```\s*$", "", text)              # remove trailing ```
    return text.strip()
 
# Tool1:Tavily Web Search
@tool
def search_web(query: str) -> str:
    """Search the web for information not found in the PDF.

    Use when the question requires current information, external examples,
    or knowledge beyond the lecture content.

    Input: a clear search query in English or German.
    Returns: combined text from the top 3 search results with their URLs.
    """
    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)
        results = client.search(query, max_results=3, search_depth="basic")

        output_parts = []
        for r in results["results"]:
            output_parts.append(f"from: {r['url']}\ncontent: {r['content']}")

        return "\n\n---\n\n".join(output_parts)

    except Exception as e:
        return f"Web Search Error: {str(e)}"



# Tool2:Mermaid Diagram Generator
@tool
def generate_mermaid_chart(description: str) -> str:
    """Generate a Mermaid diagram from a natural-language description.

    Use ONLY when the question explicitly involves a process flow, system
    architecture, state machine, or entity relationships.

    Do NOT use for definitions, comparisons, formulas, or code samples.

    Input: short English description of what the diagram should show.
    Returns: a fenced mermaid code block ready to embed in the answer.
    """
    import anthropic as _anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")

    prompt=f"""/no_think
        sGenerate ONLY valid Mermaid diagram syntax. No explanations, no markdown fences, no extra text.

        Diagram to create: """ + description + """

        Rules:
        Pick the most suitable Mermaid type:
        - Pick the most suitable type: flowchart LR/TD, sequenceDiagram, stateDiagram-v2, classDiagram
        - At most 8 nodes and 10 edges
        - Node labels must NOT contain parentheses () or special characters
        - Use only letters, numbers, spaces, hyphens in node labels
        - Start directly with the diagram-type keyword"""

    try:
        client = _anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw_text = message.content[0].text
        body = _extract_mermaid_body(raw_text)
        if not body:
            return (
                "```mermaid\n"
                "flowchart LR\n"
                '  A["Empty output"] --> B["Try rephrasing"]\n'
                "```"
            )
        return f"```mermaid\n{body}\n```"


    except Exception as e:
        return (
            "```mermaid\n"
            "flowchart LR\n"
            f'  A["Diagram generation failed"] --> B["{type(e).__name__}"]\n'
            "```"
        )


# Claude API Tool Calling
CLAUDE_TOOLS = [
    {
        "name": "search_web",
        "description": "Search the web for current information not found in the PDF. Use when the question requires information beyond the lecture content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query in English or German"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "generate_mermaid_chart",
        "description": "Generate a Mermaid diagram. Use ONLY when the question explicitly asks for a flow diagram, process visualization, or system architecture.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Short English description of what the diagram should show"
                }
            },
            "required": ["description"]
        }
    }
]