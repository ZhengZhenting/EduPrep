import re
import httpx
from langchain_core.tools import tool

OLLAMA_URL = "http://localhost:11434/api/generate"
TOOL_MODEL = "qwen2.5:3b"

# Helper functions
def _strip_think_blocks(text: str) -> str:
    """剥离<think>...</think>块，保留其中的内容，但丢弃块标签和块内的任何文本。"""
    if "</think>" in text:
        text = text.split("</think>")[-1]
    return text.strip()


def _extract_mermaid_body(raw: str) -> str:    
    """从原始文本中提取Mermaid图表的主体内容，去掉可能的Markdown代码块标记和多余的空白。"""
    text = raw.strip()
    text = re.sub(r"^```(?:mermaid)?\s*\n?", "", text)  # 去掉开头的 ```mermaid 或 ```
    text = re.sub(r"\n?```\s*$", "", text)              # 去掉结尾的 ```
    return text.strip()

# Tool1:写 Mermaid 语法的文本生成器，Mermaid图表在前端实现
@tool
async def generate_mermaid_chart(description: str) -> str:
    """Generate a Mermaid diagram from a natural-language description.

    Use ONLY when the question explicitly involves a process flow, a system
    architecture, a state machine, or a relationship between entities that
    cannot be adequately explained in plain text.

    Do NOT use for:
    - Definitions or single-concept explanations
    - Comparisons that fit naturally in a table
    - Mathematical formulas (use render_math_formula instead)
    - Code samples (use highlight_code instead)

    The input should be a short English description of what the diagram needs
    to show, e.g. "TCP three-way handshake between client and server".
    Returns a fenced ```mermaid code block ready to embed in the answer.
    """

    prompt=f"""/no_think
        You are a Mermaid diagram expert. Output ONLY valid Mermaid syntax — no explanations, no markdown fences, no thinking.

        The diagram should illustrate: {description}

        Pick the most suitable Mermaid type:
        - flowchart LR / flowchart TD for processes and architectures
        - sequenceDiagram for interactions between parties
        - stateDiagram-v2 for state machines
        - classDiagram for class relationships

        Constraints:
        - At most 8 nodes and 10 edges (keep it readable)
        - All node labels in clear English
        - Start the output directly with the diagram-type keyword
        - No prose before or after, no ``` fences"""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                OLLAMA_URL,
                json={
                    "model":TOOL_MODEL,
                    "prompt":prompt,
                    "stream":False,
                    "think": False,
                    "options": {
                        "temperature": 0.2
                    }
                }
            )
            raw_text = response.json()["response"]
    except Exception as e:
        return (
            "```mermaid\n"
            "flowchart LR\n"
            f'  A["Diagram generation failed"] --> B["{type(e).__name__}"]\n'
            "```"
        )
    cleaned=_strip_think_blocks(raw_text)
    body=_extract_mermaid_body(cleaned)
    if not body:
        return (
            "```mermaid\n"
            "flowchart LR\n"
            '  A["Empty model output"] --> B["Try rephrasing"]\n'
            "```"
        )

    return f"```mermaid\n{body}\n```"

# Tool2: 把任何形态的 LaTeX 输入，洗成前端能识别的 $$...$$ 标准格式,由KaTeX的JS库生成漂亮的数学公式
@tool
def render_math_formula(latex_expression: str) -> str:
    """Render a LaTeX math formula for display in the answer.

    Use ONLY when the question involves mathematical notation, equations,
    derivations, or formulas drawn from the lecture material.

    Do NOT use for:
    - Conceptual or narrative explanations
    - Plain numbers or arithmetic that fit inline in prose
    - Pseudocode or program logic (use highlight_code instead)

    The input must be a single valid LaTeX expression WITHOUT surrounding
    dollar signs, e.g. "E = mc^2" or "\\sum_{i=1}^{n} x_i".
    Returns a $$...$$ block that the frontend will render with KaTeX.
    """
    
    expr = latex_expression.strip() #去前后空白

    while expr.startswith("$"):
        expr = expr.lstrip("$").strip()  # 反复剥掉开头的 $

    while expr.endswith("$"):
        expr = expr.rstrip("$").strip()  # 反复剥掉结尾的 $
    
    if not expr:
        return "$$\n\\text{(empty formula)}\n$$"   # 空输入兜底

    return f"$$\n{expr}\n$$"  # 套上 $$ 返回


# Tool3:高亮代码 
@tool
def highlight_code(code: str, language: str) -> str:
    """Format a code snippet for syntax-highlighted display.

    Use ONLY when the question involves programming code, algorithms, or
    pseudocode taken from the lecture material.

    Do NOT use for:
    - Conceptual explanations of an algorithm in prose
    - Mathematical expressions (use render_math_formula instead)
    - Configuration files unless the question is specifically about them

    Inputs:
    - code: the raw source text, preserved verbatim including indentation
    - language: a short identifier such as "python", "java", "sql", "bash"

    Returns a fenced ```<language> code block ready for the frontend
    highlight.js renderer.
    """

    #fence是markdown里用三个连续的反引号 ``` 圈出代码块的边界的标记
    lang = language.strip().lower() or "text" #去空白、转小写、空字符串兜底
    fence = "````" if "```" in code else "```" # 如果代码里有 ```，就用 ```` 作为 fence，否则用 ``` 就好
    return f"{fence}{lang}\n{code}\n{fence}" # 套fence返回


# All tools
ALL_TOOLS = [generate_mermaid_chart, render_math_formula, highlight_code]
