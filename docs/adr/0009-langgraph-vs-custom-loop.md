# ADR-0009: 用 LangGraph 编排 Agent，而非自研循环

- **状态 (Status)**: Accepted
- **日期 (Date)**: 2026-07-08
- **关联 (Related)**: [agent-orchestration.md](../architecture/agent-orchestration.md)（设计 + 实测踩坑）· [ADR-0003 LLM-decided web search](./0003-llm-decided-web-search.md)（本决策的前身/铺垫）

---

## 背景 (Context)

现有 `/ask` 的联网决策（ADR-0003）已经是"LLM 通过 Anthropic tool-use 自主决定要不要调用 `search_web`"，但仍是**单次决策、线性流程**：检索一次 → 生成答案 → 最多再判断一次要不要联网，没有"回头检查答案质量、不满意就重新规划"的能力。

P8 上线后，`/ask` 可用的数据源从"chunk 检索 + 网络搜索"扩展到了"知识图谱查询"、（未来的）"掌握度查询"——工具从 1 个变成 3–4 个。需要的不再是"再加一个 if 判断该不该联网"，而是一套通用的**多工具、多轮、可能需要重试**的决策机制。需要决定：这套机制自己写循环实现，还是引入一个专门的编排框架。

## 决策 (Decision)

采用 **LangGraph 的 `StateGraph`** 编排 Agent（Planner → ToolNode → Reflector 三节点，条件边控制流转），而不是手写一个 while 循环自己管理"要不要再调工具、要不要重试"。

## 理由 (Rationale)

- **状态管理是编排问题里最容易写错的部分，LangGraph 把它标准化了**。手写循环需要自己维护"消息历史、当前轮次、是否已重试"这些状态并小心处理边界条件；`StateGraph` 提供了 `TypedDict` 状态 + `add_messages` reducer 这样的标准模式，减少手写状态管理时的低级错误（虽然我们在实现中仍然踩了一个 TypedDict 相关的坑，见下方"后果"）。
- **`ToolNode` 现成处理"多工具并发调用+结果回填"**：Claude 一条消息里可能同时请求多个工具，`ToolNode` 自动执行并生成匹配的 `tool_result`，不需要自己写这部分的消息拼接逻辑。
- **条件边（conditional edges）直接表达"决策图"**，比一串 if/else 更贴近我们想表达的流程本身（Planner→工具→Planner→...→Reflector→通过/重试），代码结构和设计图是对应的，可维护性更好。
- **和项目已有的 LangChain 生态无缝衔接**：项目已经在用 LangChain 的组件（`JsonOutputParser`、`@tool`、`OllamaEmbeddings`、`Chroma`），LangGraph 是同一生态里"专门管编排"的那一层，不需要引入完全不同风格的框架。
- **单 agent 就够，不需要多 agent 编排框架**：LangGraph 也支持真正的多 agent（supervisor 模式），但我们的场景（几个工具，都不需要"自己再循环推理"）用单 agent + 工具列表就够，多 agent 模式对单人项目是过度设计——所以选的是 LangGraph 里最简单的那种用法，不是它的全部能力。

## 备选方案 (Alternatives Considered)

| 方案 | 不选的原因 |
|---|---|
| **手写 while 循环**（自己判断要不要继续调工具、要不要重试） | 需要自己实现"多工具并发执行+结果回填"、"状态在多轮间怎么传递"这些 LangGraph 已经标准化的部分；用于快速原型可以，但随着工具数量增加，手写的状态管理容易出现和我们在 §5 踩到的同类 bug（尤其是"判断是否完成"这类边界条件）。 |
| **继续沿用 ADR-0003 的单次决策模式**（只在联网这一个点加决策，其它工具再各自加 if） | 每加一个新数据源（知识图谱、掌握度）就要在 `/ask` 里加一段专门的判断逻辑，`/ask` 会变成一堆越叠越高的 if；无法表达"先查图谱、发现不够再联网"这种多步依赖。 |
| **多 agent supervisor 模式**（图谱查询、网络搜索各自是独立 agent，上层再有一个 supervisor 决定分派给谁） | 我们的工具都很单一、不需要"自己再循环思考"，supervisor 模式是给"子任务本身复杂到需要独立推理循环"的场景准备的；对当前工具集是过度设计，留作未来工具变复杂时的备选。 |

## 后果 (Consequences)

**正面**
- 新增工具（比如以后接 P9 GraphRAG、P10 掌握度）只需要在工具列表里加一个 `@tool` 函数，编排逻辑（Planner/ToolNode/Reflector 的流转）不用改。
- 条件边 + State 的结构，让"重试/循环"这类以前难写对的逻辑，用声明式的图结构表达出来，调试时日志埋点（`[planner]`/`[tool:...]`/`[reflect]`）能清楚看到每一步走到了图的哪个节点。

**负面 / 需注意**
- **框架不是银弹**：引入 LangGraph 后仍然踩了四个真实的坑（TypedDict 状态判断错误、ChromaDB 并发竞态、违反 Anthropic tool_use 协议、前端渲染耦合）——完整记录见 [agent-orchestration.md §5](../architecture/agent-orchestration.md)。框架标准化了"消息怎么传递、工具怎么并发执行"，但**不会替你验证"这份状态逻辑对不对""这份历史记录符不符合底层 API 协议"**，这些仍然需要在实现和测试时人工发现。
- **每次请求重建一次 `StateGraph`**（因为工具要闭包绑定 `filename`/`course_id`），有极小的构建开销，目前判断可忽略；未来若要用 LangGraph 的 checkpointer 做跨请求的多轮对话记忆，这里需要重构成不按请求重建图。
- **新增依赖**：`langgraph`、`langchain-anthropic`（之前项目里 Claude 调用都是直接用 `anthropic` SDK，这次为了配合 LangGraph 的工具调用集成，Agent 相关代码改用 `langchain_anthropic.ChatAnthropic`；其它端点不受影响，仍用原生 SDK）。
- **本次只做了"单 agent + 工具列表"这一种最简单的 LangGraph 用法**，其"多 agent 编排"等更复杂能力目前用不到，不代表以后不需要评估。
