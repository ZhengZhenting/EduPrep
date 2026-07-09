"""
agent_graph.py — P11: LangGraph 版 /ask。

一个 agent = 一张 StateGraph：
  planner (LLM 决策+可能调工具) --条件边--> tools (执行) --> 回到 planner (可能再调一轮)
                              \--(没有工具调用)--> reflect (校验引用) --条件边--> 通过:END / 不通过:回 planner(有限重试)

图本身(节点+条件边) 就是 orchestrator，不需要额外再加一层调度。
"""
from __future__ import annotations
import os
import re
from typing import TypedDict, Annotated
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
import anthropic

from agent_tools import build_tools

load_dotenv()

# 模型分层（见 docs/architecture/model-tiering.md）：
# 先用 sonnet 保持和项目其它端点一致、成本可控；以后可按 roadmap P11 升级 Planner 为 opus。
AGENT_MODEL = "claude-sonnet-4-5"
MAX_TOOL_ROUNDS = 4      # 防止 LLM 陷入无限调工具的循环
MAX_REFLECT_RETRIES = 1  # Reflector 判不通过时最多重来一次，防止无限循环

_judge_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]   # LangGraph 标准的消息累积 reducer
    filename: str
    course_id: int
    tool_rounds: int
    retry_count: int
    verified: bool
    final_answer: str
    done: bool   # 显式完成标志；TypedDict 的 key 一旦初始化就"永远存在"，不能靠 "key not in state" 判断是否完成


def _extract_pages(messages) -> list[int]:
    """从 search_pdf 工具的返回结果里抠出 '[Page N]' 标记的页码。"""
    pages = set()
    for m in messages:
        if getattr(m, "type", "") == "tool" and getattr(m, "name", "") == "search_pdf":
            pages.update(int(p) for p in re.findall(r"\[Page (\d+)\]", m.content))
    return sorted(pages)


def _extract_urls(messages) -> list[str]:
    """从 search_web 工具的返回结果里抠出 'from: <url>' 标记的链接。"""
    urls = []
    for m in messages:
        if getattr(m, "type", "") == "tool" and getattr(m, "name", "") == "search_web":
            urls.extend(re.findall(r"from:\s*(\S+)", m.content))
    return urls


def _judge_citation(question: str, draft_answer: str, tool_context: str) -> bool:
    """Reflector 用：让 Claude 判断草稿答案是否被工具返回的内容支持（简化版 verify_citation）。"""
    system = "You check whether an answer is faithfully supported by the given context. Reply with exactly one word: YES or NO."
    user = f"""Question: {question}

Context the assistant used:
{tool_context[:3000]}

Draft answer:
{draft_answer}

Is the draft answer faithfully supported by the context (no fabricated claims)? Reply YES or NO only."""
    resp = _judge_client.messages.create(
        model=AGENT_MODEL, max_tokens=5, temperature=0,
        system=system, messages=[{"role": "user", "content": user}],
    )
    verdict = resp.content[0].text.strip().upper()
    print(f"[reflect] citation judge verdict={verdict!r}")
    return verdict.startswith("Y")


def build_graph(filename: str, course_id: int):
    """每次请求现建一张图（工具要闭包绑定 filename/course_id，代价很小，忽略不计）。"""
    tools = build_tools(filename, course_id)
    base_llm = ChatAnthropic(model=AGENT_MODEL, temperature=0)
    llm_with_tools = base_llm.bind_tools(tools)

    def planner_node(state: AgentState) -> dict:
        rounds = state.get("tool_rounds", 0)
        print(f"[planner] round={rounds} messages_so_far={len(state['messages'])}")
        if rounds >= MAX_TOOL_ROUNDS:
            # 达到轮次上限：不绑工具直接调用，模型在结构上就不可能再发起 tool_use，
            # 避免"已发起 tool_use 但没有对应 tool_result"违反 Anthropic 协议导致 400。
            print(f"[planner] !! hit MAX_TOOL_ROUNDS={MAX_TOOL_ROUNDS}, invoking WITHOUT tools to force a final answer")
            ai_msg = base_llm.invoke(state["messages"])
        else:
            ai_msg = llm_with_tools.invoke(state["messages"])
        n_calls = len(getattr(ai_msg, "tool_calls", []) or [])
        print(f"[planner] AI requested {n_calls} tool call(s)"
              + (f": {[c['name'] for c in ai_msg.tool_calls]}" if n_calls else " -> producing final answer"))
        return {"messages": [ai_msg], "tool_rounds": rounds + 1}

    def should_call_tools(state: AgentState) -> str:
        last = state["messages"][-1]
        has_calls = bool(getattr(last, "tool_calls", None))
        return "tools" if has_calls else "reflect"

    tool_node = ToolNode(tools)

    def reflect_node(state: AgentState) -> dict:
        question = next((m.content for m in state["messages"] if isinstance(m, HumanMessage)), "")
        draft = state["messages"][-1].content
        tool_context = "\n\n".join(
            m.content for m in state["messages"] if getattr(m, "type", "") == "tool"
        )
        ok = _judge_citation(question, draft, tool_context) if tool_context else True
        retries = state.get("retry_count", 0)
        if ok or retries >= MAX_REFLECT_RETRIES:
            print(f"[reflect] finalizing (ok={ok}, retries={retries})")
            return {"verified": ok, "final_answer": draft, "done": True}
        print(f"[reflect] NOT supported, asking planner to redo (retry {retries + 1}/{MAX_REFLECT_RETRIES})")
        nudge = HumanMessage(content="Revise your answer to be strictly grounded in the tool results above. "
                                      "Output ONLY the corrected final answer for the student, in the same "
                                      "clean format as before — do not mention tools, re-checking, retries, "
                                      "or your reasoning process. Just the answer.")
        return {"messages": [nudge], "retry_count": retries + 1, "done": False}

    def should_retry(state: AgentState) -> str:
        return END if state.get("done") else "planner"

    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("tools", tool_node)
    graph.add_node("reflect", reflect_node)
    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", should_call_tools, {"tools": "tools", "reflect": "reflect"})
    graph.add_edge("tools", "planner")
    graph.add_conditional_edges("reflect", should_retry, {"planner": "planner", END: END})
    return graph.compile()


def run_agent(question: str, filename: str, course_id: int) -> dict:
    """对外入口：main.py 调这个函数即可，不需要知道 LangGraph 内部细节。"""
    print(f"\n===== [agent] run_agent start | course_id={course_id} filename={filename} =====")
    print(f"[agent] question={question!r}")
    system = SystemMessage(content=(
        """
You are a learning assistant for international students studying German lecture material.

Your goal is to answer using the lecture whenever possible, but ensure every concept is actually explained.

Available tools:

- search_pdf
  Search the lecture PDF and return relevant passages with page numbers.

- query_knowledge_graph
  Retrieve a concept's definition and related concepts.
  ALWAYS use this tool whenever the user's question explicitly mentions a specific concept or term.

- get_concept_mastery
  Retrieve the student's weak concepts so explanations can focus on them.

- search_web
  Search reliable external sources.
  Use this tool AT MOST ONCE.

Decision policy:

1. First search the lecture PDF.

2. If the user asks about a specific concept or term, ALWAYS call query_knowledge_graph.

3. Evaluate whether the lecture actually explains the concept.

A concept is considered **NOT explained** if ANY of the following is true:

- it appears only once or only in passing;
- it is only listed as an example or keyword;
- the retrieved text is only a title, caption, heading, or page header;
- no definition or explanation is provided;
- search_pdf returns irrelevant matches.

If the concept is NOT explained, you MUST call search_web once to obtain a proper explanation.

Do NOT simply answer that "the lecture does not cover this concept" without first using search_web.

When both lecture material and web information exist:

- prioritize the lecture for course-specific content;
- use the web only to explain the missing concept;
- clearly distinguish which information comes from the lecture and which comes from external sources.

If the concept does not exist in either the lecture or the knowledge graph, search_web should still be used before concluding it is outside the lecture scope.

Answer in Chinese.

Keep answers concise.

Whenever information comes from search_pdf, cite the page numbers.

Output format (STRICT):

- Output ONLY the direct answer to the student's question.
- NEVER narrate your process: do not say things like "let me check", "根据工具返回",
  "重新检查后", "search_pdf 返回了...", "我使用了 X 工具", or describe which tools you
  called or what each one returned.
- Do not mention tools, retries, or your own reasoning steps at all — the student only
  wants the answer and where it comes from (page numbers / whether it's from the lecture
  or external knowledge), not a report on how you found it.
"""
    ))
    graph = build_graph(filename, course_id)
    initial_state: AgentState = {
        "messages": [system, HumanMessage(content=question)],
        "filename": filename,
        "course_id": course_id,
        "tool_rounds": 0,
        "retry_count": 0,
        "verified": False,
        "final_answer": "",
        "done": False,
    }
    final_state = graph.invoke(initial_state, config={"recursion_limit": 25})
    answer = final_state.get("final_answer") or final_state["messages"][-1].content
    pages_used = _extract_pages(final_state["messages"])
    urls_used = _extract_urls(final_state["messages"])
    print(f"[agent] pages_used={pages_used} urls_used={urls_used}")
    print(f"[agent] DONE verified={final_state.get('verified')} retry_count={final_state.get('retry_count')}")
    print(f"[agent] final answer (first 150 chars): {answer[:150]!r}")
    print("===== [agent] run_agent end =====\n")
    return {
        "answer": answer,
        "verified": final_state.get("verified", False),
        "tool_rounds": final_state.get("tool_rounds", 0),
        "pages_used": pages_used,
        "urls_used": urls_used,
    }