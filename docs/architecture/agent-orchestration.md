# Agent 编排设计 (Agent Orchestration)

> **状态**: **Implemented（核心 Agent 循环跑通，MCP 部分未开始）**
> **更新**: 2026-07-08
> **关联**: [ADR-0009](../adr/0009-langgraph-vs-custom-loop.md)（LangGraph vs 自研循环选型）· [model-tiering.md](./model-tiering.md)（模型分层）· [knowledge-graph-schema.md](./knowledge-graph-schema.md)（`query_knowledge_graph` 读的数据）
> **代码**: `backend/agent_graph.py`（StateGraph 定义）· `backend/agent_tools.py`（工具集）· `backend/main.py`（`POST /ask/agent` 端点）· `frontend/.../LearnTab.tsx`（前端接入）

---

## 1. 背景：为什么 `/ask` 需要一个 Agent

现有 `/ask` 是**写死的线性流程**：检索 → 生成答案 → LLM 决定要不要联网（ADR-0003 的"轻量决策"）。这套流程只有一个决策点，**没有"回头检查、换个思路重试"的能力**——答案生成完就直接返回，即使检索质量很差或答案没有被引用内容支撑。

P8 上线后，又多了两个可能有用的数据源：知识图谱（`concept`/`concept_edge`）和（未来的）掌握度（`concept_mastery`）。把这些接入 `/ask` 需要的不再是"多写一个 if"，而是**"这道题该用哪些工具、要不要循环重试"**——这正是需要一个真正的 Agent 编排层的原因。

## 2. 一个 Agent，不是三个

**术语澄清（详见此前讨论）**：一个 agent = 一张 LangGraph `StateGraph`。图里的 Planner / ToolNode / Reflector 是**同一个 agent 内部的三个节点（角色）**，不是三个独立的 agent。**图本身（节点 + 条件边）就是 orchestrator**，不需要在图之上再加一层"总调度"。

```
                     ┌─────────────┐
        ┌───────────▶│   Planner   │◀────────────┐
        │            │  (LLM node) │              │ 条件边:
        │            └──────┬──────┘              │ Reflector 判断
        │                   │ 决定调哪些工具         │ "不通过→重来"（有限次数）
        │                   ▼
        │            ┌─────────────┐
        │            │  ToolNode    │   ← 执行 Planner 选中的工具（普通代码，非 LLM）
        │            └──────┬──────┘
        │                   │ 工具结果写回 State
        │                   ▼
        │              (回到 Planner，可能再调一轮工具)
        │
        │            ┌─────────────┐
        └────────────│  Reflector   │  (LLM node，校验答案有没有被工具结果支撑)
        不通过         └──────┬──────┘
                              │ 通过 / 达到重试上限
                              ▼
                          返回最终答案
```

工具本身是**普通 Python 函数**（不是 agent），由 LangGraph 的 `ToolNode` 统一执行。

## 3. 工具集（`agent_tools.py`）

| 工具 | 数据来源 | 现状 |
|---|---|---|
| `search_pdf` | 复用 `rag.py` 的 hybrid 检索（BM25+vector+RRF） | 完全可用 |
| `query_knowledge_graph` | P8 已建的课程级图谱（1 跳关系 + 概念描述） | 可用（数据取决于该课程是否已上传/抽取过 PDF） |
| `get_concept_mastery` | P10 的 `concept_mastery` 表 | **现阶段恒空**——P10（知识追踪）未实现，表里没有任何数据；工具调用后会诚实返回"暂无数据" |
| `search_web` | Tavily（和 `tools.py` 的 `search_web` 同款 API，但独立实现，统一放在 agent 工具文件里） | 完全可用 |

**工具描述（docstring）即 LLM 看到的"使用说明"**——工具描述的措辞直接决定 Planner 会不会用它。这次踩过的坑：最初把 `query_knowledge_graph` 的描述写成"仅用于概念间关系比较"，导致模型对着"什么是 X"这种纯定义问题从不调用它（即使该课程图谱里明明有 X 这个概念、有现成的 `description` 字段）——**不是模型笨，是工具描述把它的适用范围写窄了**。放宽描述为"任何问到具体术语的问题都可以用"后，行为立刻改变。

## 4. System Prompt 的决策策略

`run_agent` 里的 system prompt 明确写了：
- 先查 `search_pdf`；问到具体概念/术语必须调 `query_knowledge_graph`；
- 判断"概念是否被讲义真正讲解"（只是标题/图注/一笔带过 ⇒ 判定为未讲解）；
- 未讲解 ⇒ 必须调用一次 `search_web` 补充，不能直接说"讲义未涉及"；
- 讲义与网络内容并存时，分清各自来源；
- **输出格式硬规则**：只给答案本身，不叙述"我用了什么工具、检查了什么"——这条规则是后来加的，见 §5.3。

## 5. 实测踩坑记录（四个真实 bug，均已修复）

这一节的价值：证明"能用 LangGraph 画出流程图"和"这套流程图在 Anthropic 工具协议 + 并发执行下真的能跑"是两回事。四个 bug 都是**先跑出真实报错、再定位根因、再验证修复**，不是纸上谈兵。

### 5.1 TypedDict 状态判断错误 —— `should_retry` 永远直接结束

**症状**：Reflector 判定答案不合格、理应打回 Planner 重试，但图直接结束了，返回的"答案"竟然是我们塞给模型的**重试提示语本身**。

**根因**：
```python
def should_retry(state: AgentState) -> str:
    return "planner" if "final_answer" not in state else END
```
`AgentState` 是 TypedDict，`initial_state` 一开始就初始化了 `"final_answer": ""`——这个 key **从流程一开始就"存在"**（哪怕值是空字符串），LangGraph 按 key 合并更新、不会删除已有 key。所以 `"final_answer" not in state` **永远是 False**，`should_retry` 永远直接判定结束，不管 Reflector 到底想不想重试。第一次测试"看起来正常"纯属巧合——那次 Reflector 第一轮就判过了，走的是"设置真实 final_answer"分支。

**修复**：不能用"key 存不存在"判断完成，改用一个**显式的 `done: bool` 标志位**，只有 Reflector 真正判定"结束"时才置 `True`：
```python
class AgentState(TypedDict):
    ...
    done: bool

# reflect_node 两个分支都显式带上 done
return {"verified": ok, "final_answer": draft, "done": True}       # 通过
return {"messages": [nudge], "retry_count": retries + 1, "done": False}  # 重试

def should_retry(state: AgentState) -> str:
    return END if state.get("done") else "planner"
```

**教训**：LangGraph 的 State 一旦初始化就带着所有 key，**永远不要用 `"key" not in state` 判断"是否发生过某事"**，要用一个专门的布尔标志。

### 5.2 ChromaDB 并发初始化竞态

**症状**：`POST /ask/agent` 500，堆栈最底部是 `chromadb/api/shared_system_client.py` 的 `KeyError: './chroma_db'`。

**根因**：LangGraph 的 `ToolNode` **默认用线程池并发执行同一条 AI 消息里的多个工具调用**——Planner 一次请求了 2 个 `search_pdf`，两个调用被并发执行。而 `rag.py` 每次调用都新建一个 `Chroma(...)` 客户端指向同一路径，ChromaDB 底层的 `SharedSystemClient` 并发初始化同一路径时有已知的线程安全 bug（检查+创建不是原子操作）。这个坑在**旧的单线程 `/ask`** 里从未暴露过——Agent 是第一次让同一份代码在同一进程里并发跑。

**修复**：不改 `rag.py`（其它端点还在正常用），只在 Agent 工具层加锁，把对 Chroma 的访问串行化：
```python
_chroma_lock = threading.Lock()

@tool
def search_pdf(query: str) -> str:
    with _chroma_lock:
        results, best_score = search_chunks_with_score(query, filename, k=5)
    ...
```

**教训**：任何"看起来只会被单线程调用"的既有代码，一旦被 Agent 框架并发执行，都可能暴露之前从未触发过的并发 bug。

### 5.3 违反 Anthropic 的 `tool_use`/`tool_result` 协议

**症状**：达到 `MAX_TOOL_ROUNDS` 上限、触发"强制停止去 reflect"的安全阀后，下一次 Claude API 调用直接 400：
```
'tool_use' ids were found without 'tool_result' blocks immediately after
```

**根因**：原来的安全阀是"模型已经发起了 `tool_use` 请求之后，才丢弃、跳去 reflect"：
```python
if has_calls and state.get("tool_rounds", 0) >= MAX_TOOL_ROUNDS:
    return "reflect"   # 直接跳过 ToolNode，从没执行这些工具
```
但 Anthropic 的协议要求**任何 `tool_use` 块之后必须紧跟对应的 `tool_result`**。这条历史记录（带着未回应的 `tool_use`）之后再发给 Claude，就被 400 拒绝。

**修复**：把拦截**提前到请求发起之前**——命中轮次上限时，Planner **不绑定工具**直接调用模型，让它在结构上**不可能**再发起 `tool_use`：
```python
base_llm = ChatAnthropic(model=AGENT_MODEL, temperature=0)
llm_with_tools = base_llm.bind_tools(tools)

def planner_node(state):
    if state.get("tool_rounds", 0) >= MAX_TOOL_ROUNDS:
        ai_msg = base_llm.invoke(state["messages"])       # 不带工具，无法再发起 tool_use
    else:
        ai_msg = llm_with_tools.invoke(state["messages"])
    ...
```

**教训**：对"结构化协议"（Anthropic 的 tool_use/tool_result 配对）的约束，必须在**发起请求之前**满足，不能靠"事后丢弃"来规避——协议校验的是完整的历史记录，不是单次调用。

### 5.4 前端 UrlsFooter 被错误耦合进 `web_supplement` 判断块

**症状**：徽章正确显示 `pdf+web`（说明后端确实返回了 `urls`），但气泡下方**从来不出现网址标签**。

**根因**：`LearnTab.tsx` 的 JSX 里，`<UrlsFooter>` 被嵌套在"只有 `web_supplement` 非空才渲染"的代码块里——这是**旧 `/ask`（两段式答案）**的历史遗留结构：旧设计假设"有网址就一定伴随一段独立的网络补充文字"。但 Agent 端点**不分离两段答案**，联网内容直接融进 `answer` 正文，`web_supplement` 永远是空字符串，导致这整个块（包括嵌在里面的 `UrlsFooter`）永远不渲染。

**修复**：把 `<UrlsFooter sources={m.sources} />` 移出该条件块，独立渲染（它内部本就有 `urls.length === 0` 时返回 `null` 的判断，不需要外层再包一层）。

**教训**：给旧功能设计的 UI 结构，接入新功能时不能想当然复用——即使数据字段名一样（`sources.urls`），渲染逻辑背后的隐藏假设（"网址一定伴随网络补充文字"）可能已经不成立。

## 6. 模型分层

按 [model-tiering.md](./model-tiering.md) 的原则：现阶段 Planner / Reflector 统一用 `claude-sonnet-4-5`（和项目其它端点一致、成本可控）。Roadmap 设想的"主循环 opus、工具抽取 sonnet"分层留待后续按实际成本/质量数据决定是否升级 Planner。

## 7. 与旧 `/ask` 并存

`POST /ask/agent` 是**独立新端点**，不影响现有 `/ask`：
- 前端 `LearnTab.tsx` 已切换为调用 `AIAPI.askAgent`；
- 消息落库沿用 `/ask` 的 `{pages, urls, web_supplement}` 结构，`PagesFooter`/`UrlsFooter` 组件直接复用；
- **暂不接入** conversation memory / history 压缩（现有 `/ask` 的功能）——先跑通 Agent 架构本身，历史记忆整合留作后续。

## 8. 待办 / 已知局限

- [ ] `get_concept_mastery` 现阶段恒无数据，等 P10 知识追踪实现后才有实际意义。
- [ ] Conversation memory 未接入 Agent 路径。
- [ ] 未做 Agent 版本的评测（P6 风格的 Recall/Answer 对比），无法量化"Agent 版 `/ask` 是否比旧版更好"——这是下一步该做的事，呼应"先建评测、用数据决策"的项目原则。
- [ ] `search_pdf` 加锁后是串行执行，多个并发工具调用时有轻微延迟（可接受，正确性优先）。

### 8.1 MCP：roadmap P11 的另一半（尚未开始）

[MCP（Model Context Protocol）](https://www.anthropic.com/news/model-context-protocol) 是 Anthropic 2024 年 11 月推出的开放标准，基于 JSON-RPC 2.0，把"AI 应用怎么接入外部工具/数据"标准化。三个角色：**Host**（实际的 AI 应用，如 Claude Desktop / Cursor）、**Client**（Host 内部为每个 Server 建立的连接）、**Server**（把工具/资源暴露出来给任何 Client 用）。有两种角色，本项目未来可以两个都做：

**① 作为 MCP Server（把 `agent_tools.py` 的工具暴露出去）**

把 `search_pdf` / `query_knowledge_graph` / `get_concept_mastery` 包一层 MCP Server 协议外壳，跑成一个独立进程。之后**任何 MCP Client**（Claude Desktop、Cursor，或别人自己写的 Agent）配置里加上这个 Server 地址，就能直接调用这几个工具——不用打开 EduPrep 网站。这正是 roadmap 说的"从应用变成平台"：现在这几个工具只有 `agent_graph.py` 里的 Planner 能调，做成 Server 后变成任何 MCP Client 都能插上就用的公共能力。

- 传输方式：本地用 **stdio**；要给远程用户用则要 **Streamable HTTP**（2025-11 规范新增，取代旧的 SSE）。
- 待定：哪些工具适合公开（`search_pdf`/`query_knowledge_graph` 大概率可以；`get_concept_mastery` 涉及具体学生数据，暴露前要想清楚鉴权/隐私边界，不能是任何 Client 连上就能读到某个学生的掌握度）。

**② 作为 MCP Client（反过来外接别人现成的 Server）**

`agent_graph.py` 的 Planner 不必只调用我们自己写的 4 个工具——MCP 生态里已有 **200+ 现成 Server**（GitHub、Slack、Google Drive、Notion、Jira 等主流工具都有官方实现，见 [WorkOS: Everything your team needs to know about MCP in 2026](https://workos.com/blog/everything-your-team-needs-to-know-about-mcp-in-2026)）。把 Agent 也接成 MCP Client，就能白嫖这些现成能力，不用重复造轮子。对 EduPrep 可能有意义的外部 Server 举例（都待评估，非承诺）：

- **GitHub MCP Server** —— 学生问"这个开源项目怎么用"时，Agent 能直接查代码/README；
- **Slack MCP Server** —— 把 P10 的复习提醒（FSRS 到期）推送到学生的 Slack，而不是只能在网站里看；
- **Google Drive / Notion MCP Server** —— 学生自己的笔记如果存在这些地方，Agent 能一并检索。

**两者不互斥**：一个成熟的 Agent 系统往往既是某些能力的 Server（暴露 EduPrep 的图谱/检索能力），又是别的能力的 Client（消费 GitHub/Slack 等外部能力）。两者都建在同一张 `agent_graph.py` 的 `StateGraph` 之上——MCP 只是改变"工具从哪来、暴露给谁"，不改变 §2 的编排结构（Planner→ToolNode→Reflector 照旧，ToolNode 里的工具来源可以是本地函数，也可以是 MCP Client 代理调用的远程工具）。
