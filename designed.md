# RobotClaw V0.2 软件概要设计

## 1. 项目定位

RobotClaw 是一个面向机器人运维与诊断场景的聊天式 Agent Runtime。

用户通过聊天方式描述问题，例如：

- 机器人导航不了
- 雷达没有数据
- 地图加载失败
- 定位漂移严重

系统自动完成以下链路：

```text
问题理解
  ↓
Playbook 匹配
  ↓
知识库检索
  ↓
工具规划
  ↓
机器人检查
  ↓
问题分析
  ↓
解决方案生成
  ↓
自动修复（可选）
```

## 2. 设计原则

### 2.1 Playbook 优先

优先执行固化经验：

```text
自然语言
  ↓
Playbook Match
  ↓
Playbook Execute
```

未命中时进入兜底路径：

```text
Knowledge Base
  ↓
LLM Planner
  ↓
Tool Planning
```

### 2.2 LLM 不直接执行

LLM 只负责：

- 意图理解
- 工具规划
- 结果总结

LLM 不能：

- 直接执行工具
- 直接 SSH 机器人
- 直接修改配置
- 直接重启机器人

所有执行必须经过：

```text
ToolExecutor
  ↓
PermissionGuard
```

### 2.3 Tool 负责采集

Tool 只返回事实，例如：

- `/scan` 是否存在
- `/scan` 频率
- TF 是否存在
- 节点是否运行
- 日志是否有 `ERROR`

Tool 不做诊断。诊断由以下模块完成：

- Rule Engine
- Playbook

约定：

- `rule` 是独立通用组件
- `playbook` 可以引用 `rule`
- `playbook` 不内嵌具体规则实现

### 2.4 单活跃机器人设计

当前系统允许在运行期间切换机器人，但同一时间只允许一个活跃机器人实例存在，因此：

- 不设计 `RobotManager`
- 不设计 `RobotPool`
- 不设计多机器人并发调度

采用以下模式：

```text
Session
+ 当前机器人引用
  ↓
SSHManager
+ 当前机器人配置
+ 当前唯一 SSH 实例
```

### 2.5 可中断可恢复

任何诊断任务都必须支持：

- 暂停
- 恢复
- 取消
- 切换任务

## 3. 总体架构

```text
┌─────────────────────┐
│     Frontend UI     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     Chat Gateway    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Session Manager   │
├─────────────────────┤
│ Memory Manager      │
│ Task Store          │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Runtime Service   │
├─────────────────────┤
│ Runtime State       │
│ Execution Context   │
│ Interrupt / Resume  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ LangGraph Orchestr. │
├─────────────────────┤
│ Graph Builder       │
│ Node Router         │
│ Node Scheduling     │
└──────────┬──────────┘
           │
           ├──────────────────────────────┐
           │                              │
           ▼                              ▼
┌─────────────────────┐         ┌─────────────────────┐
│   Playbook Engine   │         │   Knowledge / RAG   │
├─────────────────────┤         ├─────────────────────┤
│ Playbook Match      │         │ Document Loader     │
│ Behavior Tree       │         │ Document Splitter   │
│ Condition / Action  │         │ Embedding           │
│ Condition Rule      │         │ Vector Store        │
└──────────┬──────────┘         │ FAQ / BM25 / Vector │
           │                    └──────────┬──────────┘
           │                               │
           └──────────────┬────────────────┘
                          │
                          ▼
                ┌─────────────────────┐
                │   Tool Executor     │
                ├─────────────────────┤
                │ Tool Registry       │
                └──────────┬──────────┘
                           │
                           ├───────────────┐
                           │               │
                           ▼               ▼
┌─────────────────────┐   ┌─────────────────────┐
│     Rule Engine     │   │     SSH Manager     │
├─────────────────────┤   ├─────────────────────┤
│ Rule Registry       │   │ Current Config      │
│ Rule Evaluate       │   │ Current SSH Client  │
└──────────┬──────────┘   └──────────┬──────────┘
           │                         │
           └──────────────┬──────────┘
                          │
                           ▼
┌─────────────────────┐
│       Robot         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Diagnosis Summary   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  LLM Summarizer     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Chat Response     │
└─────────────────────┘
```

## 4. 核心模块设计

### 4.1 Gateway

职责：

- 接收聊天请求
- 返回流式回复
- 管理 WebSocket 连接

接口：

- `/chat/send`
- `/chat/cancel`
- `/chat/resume`
- `/chat/history`

### 4.2 Session Manager

职责：

- 管理会话
- 管理任务状态
- 管理上下文
- 提供会话查询与切换入口
- 对外投影当前任务的可见执行状态

状态边界：

- `TaskState` 表示任务生命周期状态
- `RuntimeState` 表示 LangGraph 图运行状态
- `PlaybookExecutionState` 表示单个 Playbook 执行状态
- Session Manager 只拥有和维护 `SessionState`、`TaskState`

状态：

- `created`
- `running`
- `waiting_input`
- `waiting_confirm`
- `interrupted`
- `cancelled`
- `failed`
- `completed`

推荐文件拆分：

- `models.py`：定义 `SessionState`、`TaskState`、`UserIdentity`
- `manager.py`：会话创建、任务切换、状态更新
- `store.py`：Session / Task 的持久化抽象
- `history.py`：会话历史读取、摘要预览、最近消息拼装

建议：

- `SessionManager` 只拥有 `SessionState`、`TaskState`
- 聊天记录不要直接塞进 `SessionManager`
- 会话预览标题、最近消息摘要可通过 `history.py` 或 `memory` 协作生成

### 4.3 Memory Manager

分三层：

#### Short Memory

当前任务相关信息：

- 工具结果
- 规则结果
- 执行节点
- 当前阶段中间产物
- 最近一次人工确认上下文

#### Session Memory

当前会话相关信息：

- 聊天记录
- 上下文
- 当前会话共享变量
- 最近若干轮问题与结论

#### Long Memory

长期记忆：

- 历史故障
- 历史诊断
- 历史解决方案
- 可复用经验

推荐文件拆分：

- `models.py`：定义 `ShortMemory`、`SessionMemory`、`LongMemoryRecord`、`ChatTurn`
- `manager.py`：统一内存协调入口
- `short_memory.py`：当前任务短期记忆的读写与裁剪
- `session_memory.py`：会话级聊天历史与变量管理
- `long_memory.py`：长期记忆记录、检索与归档
- `store.py`：memory 的持久化抽象

边界：

- `ShortMemory` 面向单任务运行过程
- `SessionMemory` 面向单会话多轮对话
- `LongMemory` 面向跨会话的经验沉淀
- `MemoryManager` 负责统一路由，不建议让 Runtime 直接操作底层三类 memory 实现

当前编排层接入约定：

- `session_memory.chat_history` 负责保存会话级对话历史
- `langgraph/builder.py` 在构图状态时提取最近几轮历史，生成 `conversation_history`
- `conversation_history` 作为 Prompt 上下文提供给 `classify`、`build_messages`、`summarize` 等节点
- `short_memory.scratchpad` 负责保存单任务中间结果，如 `intent`、`playbook`、`knowledge`、`analysis`、`llm_messages`
- 当前阶段已实现“最近对话历史注入 Prompt”，但尚未完全实现长期记忆驱动的多轮规划

当前实现状态：

- 已落地：会话历史保存
- 已落地：最近几轮历史注入 `classify` / `build_messages` / `summarize` Prompt
- 已落地：`short_memory.scratchpad` 作为单任务中间结果缓存
- 已落地：`build_messages -> call_model -> interpret_output` 对话闭环
- 未完全落地：基于长期记忆的跨会话检索

### 4.4 Runtime

`Runtime` 不负责图编排，负责诊断任务的运行承载与执行协作。

职责：

- 持有 `RuntimeState`
- 管理运行时上下文
- 对接 Session / Memory / Tool / SSH / Diagnosis
- 管理中断恢复入口
- 对外暴露统一的 `run()` / `resume()` / `cancel()` 能力

边界：

- `Runtime` 不负责定义 LangGraph 节点连接关系
- `Runtime` 不负责维护 Prompt 模板
- `Runtime` 不直接替代 ToolExecutor、PlaybookEngine、KnowledgeService

`runtime/workflow/` 推荐文件拆分：

- `events.py`：运行事件定义与发布格式
- `playbook_state.py`：playbook 执行状态投影、实时状态快照
- `confirmation.py`：人工确认请求生成、确认结果写回
- `resume.py`：中断恢复令牌、恢复位置、恢复参数处理
- `context.py`：运行时上下文展开、变量解析、上下文读写

约定：

- `runtime/service.py` 负责统一入口
- `runtime/control.py` 负责 run / resume / cancel 的控制逻辑
- `runtime/workflow/` 负责“运行过程控制”，不负责图编排
- `runtime/workflow/` 不直接替代 LangGraph 节点

### 4.5 LangGraph Orchestrator

采用：

- `LangGraph`

职责：

- 路由
- 状态流转
- 流程编排
- 节点调度
- 图构建

当前实现策略：

- 保留新结构中的 `gateway`、`runtime`、`session`、`memory`、`workflow` 作为运行时外壳
- 保留新的 HTTP 协议、任务状态、恢复令牌、事件广播与前端接口
- `backend/langgraph/` 这一层尽量向 `old/backend/agent/graph/` 的节点拆分与边结构靠拢
- 不再在新图中发明一套与 old 明显不同的“简化版诊断链路”
- 迁移时优先复用 old 已验证的编排思路，再由新 Runtime 提供运行时上下文与外围能力

设计目标：

- 外层运行时继续使用新架构
- 内层诊断编排尽量复用 old 的成熟图结构
- 将“运行控制”和“诊断编排”清晰分层，避免逻辑再次回流到 `runtime/service.py`

运行时节点建议拆分为：

- `classify`
- `match`
- `knowledge`
- `build_messages`
- `call_model`
- `interpret`
- `execute`
- `confirm`

知识检索路径采用 old 方案的显式多节点设计，而不是把多路检索封装进单一 service 黑盒中。

推荐节点链路：

- `classify_query`
- `match_playbook`
- `playbook_execution`
- `load_knowledge_source_docs`
- `retrieve_knowledge_faq`
- `retrieve_knowledge_bm25`
- `retrieve_knowledge_vector`
- `merge_knowledge_retrieval`
- `assemble_knowledge_context`
- `decide_knowledge_response_mode`
- `build_messages`
- `call_model`
- `interpret_output`
- `call_tools`
- `await_confirmation`

其中知识库路径的关键约束为：

- `knowledge route` 不等于“只做一次知识 service 调用”
- FAQ、BM25、Vector 三路检索必须在 LangGraph 图中有独立节点
- 多路结果必须显式 merge，而不是只保留单一路径结果
- merge 后必须显式生成 `knowledge_context`、`citations`、`confidence` 等中间结果
- `assemble_knowledge_context` 负责把知识证据整理成后续节点可消费的结构，而不是在 `summarize` 节点里临时拼接
- `decide_knowledge_response_mode` 负责明确区分知识直答模式与动作/排查模式，而不是把两类路径混在一个总结节点里
- `vector` 节点必须接入 embedding + 本地 `vectorstore/index.json`
- 如果向量检索失败，允许降级到 FAQ / BM25，但不能把向量检索链路从图中拿掉

当前图内的知识路径约定如下：

```text
match_playbook
  ↓
knowledge route
  ↓
load_knowledge_source_docs
  ├─ retrieve_knowledge_faq
  ├─ retrieve_knowledge_bm25
  └─ retrieve_knowledge_vector
  ↓
merge_knowledge_retrieval
  ↓
assemble_knowledge_context
  ↓
decide_knowledge_response_mode
  ↓
build_messages
  ↓
call_model
  ↓
interpret_output
  ├─ final / clarify -> finish
  ├─ retry -> call_model
  └─ tool_call -> call_tools -> call_model
```

`decide_knowledge_response_mode` 的设计约定：

- `answer`：当前信息足够，进入知识直答模式，模型直接输出最终文本答案
- `act`：仍需依赖工具、运行时状态或机器人环境，模型按协议输出 `command / clarify / final`

在图路由上：

- `response_mode=answer` 时，`build_messages` 会切换到知识直答系统提示词，禁止输出工具命令
- `response_mode=act` 时，`build_messages` 会切换到故障排查系统提示词，允许模型通过 `command` 进入工具回灌循环
- 当模型输出的工具需要先连接机器人时，`call_tools` 会转入 `await_confirmation`，并依旧复用新 Runtime 的恢复令牌与确认机制

约定：

- `Runtime` 负责运行
- `LangGraph` 负责编排
- `LangGraph` 通过节点调用 Runtime 相关能力，而不是反过来把全部逻辑堆进 Runtime
- 推荐代码组织上将二者拆为 `backend/runtime/` 与 `backend/langgraph/` 两个目录
- `langgraph/builder.py` 负责声明节点、边和入口点
- `langgraph/router.py` 负责条件分支判断

同时将 `prompts` 放入 `langgraph/` 目录下，作为编排层的配套模块，为 LangGraph 节点提供统一 Prompt 构造能力，而不是把 Prompt 文本散落在节点实现内部。

当前实现状态：

- 已落地：知识检索三路节点 `FAQ / BM25 / Vector`
- 已落地：`assemble_knowledge_context`
- 已落地：`decide_knowledge_response_mode`
- 已落地：`build_messages -> call_model -> interpret_output -> call_tools -> call_model` 主循环
- 已落地：`response_mode=answer` 时切换到知识直答协议，直接输出最终文本
- 已落地：图执行失败时保留 fallback 顺序执行
- 已落地：工具调用前的人工确认仍复用新 Runtime / Workflow 外壳

### 4.5.1 LangGraph State

`backend/langgraph/state.py` 中的 `ChatGraphState` 是当前 LangGraph 图运行时的共享状态容器。

设计原则：

- `ChatGraphState` 负责承载“图内节点之间需要共享的运行上下文”
- 业务长期状态仍由 `SessionState`、`TaskState`、`RuntimeState`、`ShortMemory` 分层承载
- `ChatGraphState` 更像“本轮图执行视图”，不是持久化主模型
- 能放引用就尽量放引用，避免把所有业务对象拍平成大字典

当前字段建议按下面几组理解。

1. 请求与运行入口

```python
class ChatGraphState(TypedDict, total=False):
    request: ChatRequest  # 当前用户请求，请求正文、request_id、resume 标记等入口信息
    envelope: RuntimeEnvelope  # 运行时总封装，包含 session、task、diagnosis、robot_config
    runtime_state: RuntimeState  # 当前任务的运行控制面状态，如 current_step、finished、resume_from_step
    diagnosis: DiagnosisSummary  # 当前任务的诊断输出对象，最终答案、证据、建议会写入这里
    connected: bool  # 当前是否已满足机器人连接条件
```

说明：

- `request` 是图的直接输入
- `runtime_state` 是图执行过程真正会持续读写的控制面状态
- `diagnosis` 是图最终给外部返回的结果对象

2. 能力依赖与服务引用

```python
class ChatGraphState(TypedDict, total=False):
    playbook_engine: PlaybookEngine  # Playbook 匹配与分析能力
    knowledge_service: KnowledgeService  # 知识检索服务入口
    get_llm_client: Any  # 获取当前激活 LLMClient 的工厂函数，便于热切模型
    tool_executor: ToolExecutor  # 工具规划与执行入口
    memory_manager: MemoryManager  # Memory 访问入口
    workflow_store: WorkflowStore  # Workflow 状态持久化入口
    event_bus: WorkflowEventBus  # Workflow 事件广播入口
```

说明：

- 这些字段本质是“图执行依赖注入”
- 不建议节点自己重新实例化这些能力对象
- `get_llm_client` 使用工厂函数而不是直接塞实例，是为了兼容 profile 热更新

3. Memory 与 Prompt 依赖

```python
class ChatGraphState(TypedDict, total=False):
    short_memory: ShortMemory  # 单任务短期记忆，保存 scratchpad、tool_results、pending_confirmation
    build_classify_prompt: Any  # classify 节点 Prompt 构造器
    build_route_prompt: Any  # route / match 相关 Prompt 构造器
    build_planner_prompt: Any  # planner Prompt 构造器，当前更多用于兼容过渡期
    build_summary_prompt: Any  # summary Prompt 构造器
    conversation_history: list[dict[str, str]]  # 最近几轮会话历史，供多轮承接理解
```

说明：

- `short_memory` 承担本轮任务级 scratchpad，不把临时中间结果直接塞进 `RuntimeState`
- `conversation_history` 是这次多轮衔接修复的关键字段
- Prompt builder 放进 state 后，节点层就只关心“何时调用”，不关心 Prompt 文本放在哪

4. 理解、路由与知识检索中间态

```python
class ChatGraphState(TypedDict, total=False):
    intent: dict[str, Any]  # classify 结果，如 category / summary / detail
    playbook: dict[str, Any]  # playbook 匹配结果
    knowledge_source_docs: list[Any]  # 知识源文档全集或候选集
    knowledge_faq_docs: list[Any]  # FAQ 检索结果
    knowledge_bm25_docs: list[Any]  # BM25 检索结果
    knowledge_vector_docs: list[Any]  # Vector 检索结果
    knowledge_merged_docs: list[Any]  # 多路 merge 后的候选证据
    knowledge: dict[str, Any]  # 最终整理后的知识上下文、citations、confidence 等
    response_mode: str  # 知识响应模式，典型值为 answer / act
    analysis: dict[str, Any]  # 诊断分析结果或阶段性结论
```

说明：

- 这一组字段让知识路径不再是黑盒 service
- `knowledge_*` 字段保留多路检索的显式过程态，便于日志、调试和 rerank 扩展
- `response_mode` 是后续系统提示词切换和输出协议切换的关键开关

5. 模型循环过程态

```python
class ChatGraphState(TypedDict, total=False):
    messages: list[LLMMessage]  # 当前喂给模型的完整消息链
    response_content: str  # 最近一次模型返回的原始文本
    model_loop_count: int  # 当前主循环已调用模型的次数，用于防止死循环
    parsed_response: dict[str, Any]  # interpret_output 解析出的结构化结果
    pending_commands: list[dict[str, Any]]  # 等待执行的工具命令列表
    result_kind: str  # 当前解析结论，如 final / clarify / retry / tool_call / confirmation
    final_message: str  # 当前轮已经生成的最终答复文本
```

说明：

- 这是这次从 `old` 迁过来的核心状态组
- `messages` 是 `build_messages -> call_model -> interpret_output -> call_tools -> call_model` 能闭环的关键
- `result_kind` 负责驱动图路由，不建议节点之间用布尔标志散乱判断
- `model_loop_count` 用来限制错误输出导致的无限重试

6. 确认与中断恢复态

```python
class ChatGraphState(TypedDict, total=False):
    confirmation_request: ConfirmationRequest  # 当前待用户确认的挂起请求
```

说明：

- `confirmation_request` 是 LangGraph 图与 Runtime Workflow 外壳的连接点
- 需要人工确认时，图内会生成它，但真正的挂起、持久化和恢复仍由 `workflow_store`、`event_bus`、`RuntimeState.resume_from_step` 完成

补充约定：

- `ChatGraphState` 可以保存节点中间结果，但不应替代 `ShortMemory`
- 原始 Prompt 文本、原始工具回包、超大知识文档对象不建议长期堆积在 state 中
- 若某字段只是单节点局部临时变量，应尽量保留在节点内部，而不是扩散到全局 state
- 文档中的字段分组应与 [backend/langgraph/state.py](/Users/wanghusen/Desktop/code/robot-control/backend/langgraph/state.py) 保持同步，后续新增字段时应先判断属于哪一组

当前代码对应关系：

- 图结构定义在 [backend/langgraph/builder.py](/Users/wanghusen/Desktop/code/robot-control/backend/langgraph/builder.py)
- 条件路由定义在 [backend/langgraph/router.py](/Users/wanghusen/Desktop/code/robot-control/backend/langgraph/router.py)
- 共享状态定义在 [backend/langgraph/state.py](/Users/wanghusen/Desktop/code/robot-control/backend/langgraph/state.py)
- 回答主循环节点在 [backend/langgraph/nodes/answer.py](/Users/wanghusen/Desktop/code/robot-control/backend/langgraph/nodes/answer.py)

#### State Boundary Cheat Sheet

为了避免后续继续把运行状态、图状态和临时 scratchpad 混在一起，建议按下面这个边界理解：

| 状态对象 | 主要职责 | 适合存放 | 不适合存放 |
| --- | --- | --- | --- |
| `RuntimeState` | Runtime 与 LangGraph 共享的控制面状态 | `current_step`、`finished`、`resume_from_step`、`planned_tools`、`trace`、`tool_results` | 原始 Prompt、完整消息链、大段知识上下文、局部临时变量 |
| `ShortMemory` | 单任务短期记忆与 scratchpad | `intent`、`playbook`、`knowledge`、`analysis`、`llm_messages`、`pending_confirmation` | 跨会话历史、长期经验、需要对外直接返回的正式结果 |
| `ChatGraphState` | 单次图执行期间的共享视图 | 运行依赖注入、节点中间态引用、模型循环态、最近几轮 `conversation_history` | 持久化主模型、全量业务数据库对象、与图无关的外围状态 |

进一步约定：

- `RuntimeState` 关注“流程现在走到哪、是否结束、从哪恢复”
- `ShortMemory` 关注“本轮任务临时记住了什么”
- `ChatGraphState` 关注“这次图执行需要把哪些东西串起来”

判断一个字段该放哪，可以用这三个问题快速区分：

1. 这个字段是否需要跨中断恢复继续生效，而且属于流程控制语义？
   如果是，优先放 `RuntimeState`
2. 这个字段是否只是本轮任务中间结果，后续节点要读，但不适合放控制面？
   如果是，优先放 `ShortMemory`
3. 这个字段是否只是为了让当前图节点拿到依赖或共享一次运行视图？
   如果是，优先放 `ChatGraphState`

### 4.6 LangGraph Prompts

`prompts` 是 `langgraph` 的配套模块，负责管理所有给 LLM 使用的系统提示词、节点提示词和输出协议。

职责：

- 为 LangGraph 节点生成 Prompt
- 统一维护输出协议
- 统一维护角色设定
- 屏蔽节点内的硬编码字符串

边界：

- `prompts` 只负责构造 Prompt，不负责调用模型
- `prompts` 不负责执行工具
- `prompts` 不负责保存运行状态
- LangGraph 节点负责决定何时使用哪个 Prompt
- Prompt 文件与节点文件同属编排层，不放入 Runtime 层

推荐拆分：

- `answer.py`
- `route.py`
- `planner.py`
- `summary.py`
- `protocols.py`

集成方式：

```text
LangGraph Node
  ↓
Prompt Builder
  ↓
LLM Call
  ↓
Structured Output
```

建议约定：

- `match` / `route` 节点使用路由 Prompt
- `plan` 节点使用工具规划 Prompt
- `build_messages` 节点根据 `response_mode` 选择故障排查 Prompt 或知识直答 Prompt
- `summarize` 节点使用最终总结 Prompt
- 若走知识库兜底路径，可使用知识问答 Prompt
- 所有 Prompt 输出格式应由 `protocols.py` 统一约束
- `classify` / `build_messages` / `summarize` Prompt 必须能够接收最近几轮会话上下文
- 对于“对应的”“这个”“那个”“继续输出一下”这类承接式追问，Prompt 必须结合 `conversation_history` 理解，而不是只看当前单句输入
- `summary` Prompt 应优先输出“结论 -> 原因/现状 -> 建议”的结构化自然语言，便于客户理解

### 4.7 LLM Layer

`llm` 是独立于 `langgraph/prompts` 的模型接入层。

职责：

- 统一封装模型调用入口
- 统一封装模型配置、超时、重试和流式输出能力
- 统一处理结构化输出解析
- 为 `langgraph` 节点提供稳定的 `invoke` / `invoke_structured` 能力

边界：

- `llm` 负责调用模型，不负责编排
- `llm` 不负责工具执行
- `llm` 不负责业务路由判断
- `prompts` 负责构造输入，`llm` 负责把输入送入模型并解析输出
- `langgraph/nodes` 负责决定在什么节点调用什么模型能力

建议拆分：

- `client.py`：统一模型调用入口
- `config.py`：模型名、超时、temperature、provider 配置
- `parser.py`：结构化输出解析与容错
- `schemas.py`：分类、规划、总结等结构化输出 Schema
- `models.py`：LLM 请求与响应对象

典型调用链：

```text
LangGraph Node
  ↓
Prompt Builder
  ↓
LLM Client
  ↓
Structured Parser
  ↓
Node State Update
```

建议接入位置：

- `classify` 节点：意图理解、问题分类
- `match` / `route` 节点：候选 Playbook 路由判断
- `plan` 节点：工具规划
- `knowledge` 相关节点：文档装载、多路检索、证据合并、知识问答
- `summarize` 节点：最终用户答案与诊断总结

建议约定：

- 默认通过 `llm/client.py` 统一发起调用，不在节点中直接拼 SDK 代码
- 结构化输出优先，不依赖自由文本解析
- 模型原始输出不直接写入 `RuntimeState`
- 节点只写入已经通过 `parser.py` 校验后的结果

### 4.8 Playbook Engine

Playbook 形式：

- YAML 模板

执行方式：

```text
YAML
  ↓
Parser
  ↓
PyTree
  ↓
Runner
```

目录示例：

```text
playbooks/
 ├── navigation_failure.yaml
 ├── localization_failure.yaml
 └── lidar_failure.yaml
```

### 4.9 Knowledge / RAG

知识库用于承接未命中 Playbook 时的检索与回答辅助。

整体链路：

```text
知识文档
  ↓
Document Loader
  ↓
Document Splitter
  ↓
Embedding
  ↓
Vector Store Build
  ↓
FAQ / BM25 / Vector Retrieval
  ↓
Evidence Select
  ↓
Runtime / LLM
```

设计要点：

- 支持 `txt`、`md`、`docx`、`pdf`
- `txt` / `md` 直接读取，`pdf` / `docx` 先转 Markdown 再进入统一流程
- 优先按 Markdown 标题结构切分，再按字符窗口二次切块
- 向量库采用本地文件持久化
- 检索采用多路召回：`FAQ`、`BM25`、`Vector`
- 召回结果统一做去重、排序，并提取证据片段供回答使用

职责边界：

- 文档加载、切分、embedding、向量库构建属于知识库离线准备过程
- Runtime 不负责构建知识库，只负责在运行时选择知识检索路径并消费检索结果

## 5. 行为树设计

### 5.1 行为树必须支持中断

新增节点：

- `InterruptCheckNode`

执行流程：

```text
每次 Tick
  ↓
检查 InterruptFlag
  ↓
中断
  ↓
保存执行快照
  ↓
保存当前 Node
  ↓
返回 Interrupted
```

恢复流程：

```text
恢复执行快照
  ↓
恢复 CurrentNode
  ↓
继续 Tick
```

### 5.2 行为树支持动态变量

支持来源：

- 用户输入
- Session 变量
- 行为树执行上下文变量
- Tool 输出

示例：

```yaml
topic: "{{ inputs.topic }}"
keyword: "{{ check_scan.error_keyword }}"
```

统一通过 `VariableResolver` 解析。

### 5.3 行为树支持用户输入

示例：

```yaml
- type: input
  field: topic_name
  prompt: "请输入雷达话题"
```

运行时流程：

```text
进入 WAITING_INPUT
  ↓
用户输入
  ↓
继续执行
```

## 6. Tool 平台设计

### 6.1 Tool 统一接口

```python
class Tool:
    name: str
    schema: dict

    def run(params):
        pass
```

### 6.2 Tool 分类

#### ROS

- `topic_monitor`
- `node_status`
- `service_call`
- `action_check`
- `param_read`

#### TF

- `tf_monitor`

#### Log

- `log_search`

#### Config

- `config_read`
- `config_modify`

#### Shell

- `shell_command`

## 7. SSH 管理

### 7.1 设计目标

当前系统采用单活跃机器人模型，因此：

- 允许切换机器人
- 同一时间只保留一个 SSH 实例
- 不支持多机器人并发连接
- `SSHManager` 负责当前唯一连接

### 7.2 配置来源

前端配置项：

- 机器人 IP
- SSH 端口
- 用户名
- 密码
- 私钥
- ROS 版本
- Workspace
- Setup 脚本

配置页面：

```text
系统设置
  →
Robot Connection
```

### 7.3 SSHManager

职责：

- 建立连接
- 断开连接
- 切换当前活跃机器人
- 执行命令

结构：

```python
class SSHManager:
    current_config

    def connect():
        pass

    def disconnect():
        pass

    def switch_config():
        pass

    def run_command():
        pass
```

### 7.4 切换机器人

流程：

```text
前端选择新机器人
  ↓
加载目标机器人配置
  ↓
关闭旧 SSH 实例
  ↓
测试新连接
  ↓
SSHManager 切换
  ↓
新连接建立
```

## 8. Rule Engine

职责：

- 接收 Playbook 传入的数据
- 根据规则条件做布尔判断
- 返回 `true / false` 供 Playbook 决策
- 支持规则注册、规则查找、规则执行
- 支持规则定义校验

定位：

- `rule` 是独立目录
- `rule` 是通用判断组件，不按业务场景拆 `builtin`
- `playbook` 通过 `rule_id` 或规则引用来消费规则能力
- 同一条规则可以被多个 playbook 复用

边界：

- `rule` 负责判断
- `playbook` 负责流程
- `tool` 负责采集事实
- `diagnosis summary` 负责面向用户的最终汇总

推荐文件拆分：

- `models.py`：规则引用、规则调用、规则结果等核心数据结构
- `schema.py`：规则定义校验
- `registry.py`：规则注册与索引
- `engine.py`：规则执行入口
- `operators.py`：通用比较、集合、文本、时间等判断算子
- `resolver.py`：字段路径解析、上下文取值、变量展开

推荐能力：

- 支持通过 `rule_id` 调用规则
- 支持显式传入 `payload` 与 `context`
- 支持通用比较运算，如 equals / contains / greater_than
- 支持字段路径解析，如 `scan.hz`
- 支持运行时上下文变量引用
- 支持规则执行结果标准化

示例：

```text
输入：
scan.hz = 0
```

规则：

```text
scan_has_data = scan.hz > 0
```

输出：

- `true`
- `false`

## 9. Permission Guard

当前阶段先保留设计，不进入实现范围。

所有工具执行必须经过：

```text
Tool Registry
  ↓
Schema Validate
  ↓
Permission Guard
```

风险等级划分如下。

### Low

- `topic_monitor`
- `tf_monitor`
- `log_search`

处理方式：自动执行。

### Medium

- `restart_service`
- `reload_config`

处理方式：可配置。

### High

- `reboot_robot`
- `switch_map`
- `factory_reset`

处理方式：必须确认。

## 10. Diagnosis Summary

在 LangGraph 方案下，诊断过程态由 Runtime State 承载，这里不再单独设计一套完整 Blackboard 主结构。

这一节仅保留“最终诊断结果对象”，用于汇总对用户有价值的输出：

```python
class DiagnosisSummary:
    evidence
    solutions
    final_answer
```

说明：

- 运行过程中的工具结果、规则结果、当前节点等信息，优先放在 `ShortMemory`
- `RuntimeState` 只保留跨节点共享所必需的控制面信息和少量结构化结果引用
- `DiagnosisSummary` 只保留最终面向用户的诊断结果

## 11. 模块数据结构定义

这一节只定义核心数据结构，不展开实现细节。目标是先把模块边界和字段收敛下来，后续再分别落到 `schema.py`、`models.py`、`state.py`。

### 11.1 通用基础结构

```python
from dataclasses import dataclass, field
from typing import Any, Literal

TaskStatus = Literal[
    "created",
    "running",
    "waiting_input",
    "waiting_confirm",
    "interrupted",
    "cancelled",
    "failed",
    "completed",
]

RiskLevel = Literal["low", "medium", "high"]


@dataclass
class UserIdentity:
    user_id: str  # 用户唯一 ID
    username: str = ""  # 用户名或展示名
    roles: list[str] = field(default_factory=list)  # 用户角色列表


@dataclass
class TimestampSet:
    created_at: str = ""  # 创建时间
    updated_at: str = ""  # 最近更新时间
    started_at: str = ""  # 开始执行时间
    finished_at: str = ""  # 结束时间
```

### 11.2 Gateway 数据结构

```python
@dataclass
class ChatRequest:
    session_id: str  # 当前会话 ID
    user_id: str  # 发起请求的用户 ID
    content: str  # 用户输入内容
    request_id: str = ""  # 请求唯一 ID，便于链路追踪
    interrupt: bool = False  # 是否为中断请求
    resume: bool = False  # 是否为恢复请求


@dataclass
class ChatResponse:
    session_id: str  # 当前会话 ID
    task_id: str  # 当前任务 ID
    status: TaskStatus  # 当前任务状态
    summary: str  # 返回给用户的主摘要
    continuation_token: str = ""  # 恢复执行时使用的 continuation 标识
    playbook_id: str = ""  # 命中的 playbook ID
    data: dict[str, Any] = field(default_factory=dict)  # 扩展响应载荷
```

说明：

- `Gateway` 只关心请求接入和响应返回
- 流式输出如果需要，视为传输协议结构，不放在 Gateway 核心模型里

### 11.3 Session Manager 数据结构

```python
@dataclass
class SessionState:
    session_id: str  # 会话唯一 ID
    user: UserIdentity  # 当前会话所属用户
    current_task_id: str = ""  # 当前活跃任务 ID
    current_robot_ref: str = ""  # 当前会话绑定的机器人引用
    status: TaskStatus = "created"  # 会话层当前状态
    active_topic: str = ""  # 当前会话关注的话题或故障主题
    timestamps: TimestampSet = field(default_factory=TimestampSet)  # 会话时间信息


@dataclass
class TaskState:
    task_id: str  # 任务唯一 ID
    session_id: str  # 所属会话 ID
    title: str  # 任务标题
    task_type: str  # 任务类型，如 diagnose/deploy
    status: TaskStatus = "created"  # 任务生命周期状态
    current_node: str = ""  # 当前任务对外可见的执行位置
    error: str = ""  # 最近一次错误信息
    retry_count: int = 0  # 已重试次数
    timestamps: TimestampSet = field(default_factory=TimestampSet)  # 任务时间信息
```

说明：

- `TaskState` 是任务层对外状态，不承载 LangGraph 节点间共享数据
- `TaskState.current_node` 是面向外部展示的当前位置，可由 `RuntimeState.current_step` 或 `PlaybookExecutionState.current_node_id` 投影而来

### 11.4 Memory Manager 数据结构

```python
@dataclass
class ChatTurn:
    role: Literal["user", "assistant", "system", "tool"]  # 消息角色
    content: str  # 消息正文
    created_at: str = ""  # 消息时间


@dataclass
class ShortMemory:
    task_id: str  # 关联任务 ID
    tool_results: list[dict[str, Any]] = field(default_factory=list)  # 当前任务工具结果
    rule_results: list[dict[str, Any]] = field(default_factory=list)  # 当前任务规则结果
    visited_nodes: list[str] = field(default_factory=list)  # 已执行节点路径
    current_node: str = ""  # 当前运行节点
    pending_confirmation: dict[str, Any] | None = None  # 待确认上下文
    scratchpad: dict[str, Any] = field(default_factory=dict)  # 当前任务中间产物缓存


@dataclass
class SessionMemory:
    session_id: str  # 关联会话 ID
    chat_history: list[ChatTurn] = field(default_factory=list)  # 会话聊天历史
    variables: dict[str, Any] = field(default_factory=dict)  # 会话级共享变量
    topic_stack: list[str] = field(default_factory=list)  # 会话中出现过的话题轨迹
    latest_summary: str = ""  # 最近一次会话摘要


@dataclass
class LongMemoryRecord:
    memory_id: str  # 长期记忆记录 ID
    category: Literal["fault", "diagnosis", "solution", "experience"]  # 记忆分类
    title: str  # 记忆标题
    content: str  # 记忆正文
    tags: list[str] = field(default_factory=list)  # 标签
    source_session_id: str = ""  # 来源会话 ID
    source_task_id: str = ""  # 来源任务 ID
    created_at: str = ""  # 沉淀时间
```

说明：

- `ShortMemory` 适合放“本轮执行态”，例如工具结果、规则结果、待确认上下文
- `SessionMemory` 适合放“多轮会话态”，例如聊天记录、变量、最近摘要
- `LongMemoryRecord` 适合放“沉淀知识态”，例如稳定经验和历史解决方案

### 11.5 Runtime 数据结构

设计原则：

- `RuntimeState` 只放图执行过程中必须跨节点共享的信息
- SSH 连接信息、切分建库过程、工具原始结果、最终诊断结果不直接堆进 `RuntimeState`
- `RuntimeState` 更偏控制面状态，不替代 `SessionState`、`TaskState`、`DiagnosisSummary`
- 知识库的离线构建不属于 `Runtime`，但运行时检索结果需要进入 `RuntimeState`
- `RuntimeState` 是 Runtime 与 LangGraph 共享的运行态，不直接承担任务生命周期管理

```python
@dataclass
class PlannedToolCall:
    tool_name: str  # 计划调用的工具名
    params: dict[str, Any] = field(default_factory=dict)  # 工具入参


@dataclass
class RuntimeState:
    session_id: str  # 当前会话 ID
    task_id: str  # 当前任务 ID
    user_query: str  # 用户原始问题

    route: str = ""  # 当前命中的主路径，如 playbook/knowledge/planner
    matched_playbook_id: str = ""  # 命中的 playbook ID

    current_step: str = ""  # 当前图执行步骤或节点名称
    planned_tools: list[PlannedToolCall] = field(default_factory=list)  # 待执行工具计划

    retrieval_result: "RetrievalResult | None" = None  # 当前知识检索结果
    knowledge_used: bool = False  # 当前流程是否使用了知识检索
    knowledge_confidence: float = 0.0  # 当前检索结果置信度
    knowledge_low_confidence: bool = False  # 当前检索结果是否低置信度

    interrupt_flag: bool = False  # 是否收到中断标记
    resume_token: str = ""  # 恢复执行令牌
    resume_from_step: str = ""  # 恢复时要接续的步骤

    finished: bool = False  # 当前流程是否已经结束
```

说明：

- `RuntimeState` 是 Runtime 持有、并由 LangGraph 编排流程读写的共享运行态
- `RuntimeState.current_step` 表示图当前执行到的节点或阶段
- `RuntimeState.finished` 只表示图本轮是否收口，不等同于 `TaskState.status`
- 当图进入 Playbook 路径时，`RuntimeState` 持有对当前 Playbook 的引用，但 Playbook 内部进度由 `PlaybookExecutionState` 管理
- Prompt 模板本身不放进 `RuntimeState`
- 只有节点真正需要跨节点共享的 Prompt 结果才允许写入 `RuntimeState`
- 例如：路由结果、结构化规划结果、最终总结结果可以进入 RuntimeState，但原始 Prompt 字符串应保留在 `prompts/` 模块中

### 11.6 Knowledge / RAG 数据结构

```python
@dataclass
class KnowledgeDocument:
    doc_id: str  # 文档唯一 ID
    source: str  # 原始文件路径
    filename: str  # 文件名
    filetype: str  # 文件类型，如 md/pdf/docx/txt
    content: str  # 文档清洗后的完整文本
    loader: str = ""  # 使用的加载器，如 text/mineru


@dataclass
class KnowledgeChunk:
    chunk_id: str  # 切片唯一 ID
    doc_id: str  # 所属文档 ID
    content: str  # 切片文本
    title_path: list[str] = field(default_factory=list)  # 标题层级路径
    metadata: dict[str, Any] = field(default_factory=dict)  # 附加元数据


@dataclass
class EmbeddingSpec:
    provider: str  # embedding 提供方
    model: str  # embedding 模型名
    base_url: str = ""  # embedding 服务地址


@dataclass
class VectorRecord:
    chunk_id: str  # 对应切片 ID
    embedding: list[float] = field(default_factory=list)  # 向量值
    metadata: dict[str, Any] = field(default_factory=dict)  # 向量记录元数据


@dataclass
class RetrievalRequest:
    query: str = ""  # 检索查询文本
    top_k: int = 0  # 召回数量
    channels: list[str] = field(default_factory=list)  # 检索通道，如 faq/bm25/vector


@dataclass
class RetrievalHit:
    chunk_id: str = ""  # 命中的切片 ID
    filename: str = ""  # 来源文件名
    score: float = 0.0  # 检索得分
    snippet: str = ""  # 命中文本片段
    channel: str = ""  # 来源检索通道


@dataclass
class RetrievalResult:
    query: str = ""  # 原始查询
    hits: list[RetrievalHit] = field(default_factory=list)  # 命中结果
    context: str = ""  # 拼接后的检索上下文
    confidence: float = 0.0  # 检索置信度
    low_confidence: bool = False  # 是否低置信度
```

说明：

- `KnowledgeDocument` 对应文档加载后的统一文本对象
- `KnowledgeChunk` 对应切分后的最小检索单元
- `VectorRecord` 对应向量库中的持久化记录
- `RetrievalResult` 是多路召回、去重、排序后的统一检索结果

### 11.7 Playbook Engine 数据结构

```python
BTNodeType = Literal["sequence", "selector", "condition", "action", "input", "result"]


@dataclass
class PlaybookMeta:
    playbook_id: str  # Playbook 唯一 ID
    name: str  # Playbook 名称
    version: str = "v1"  # 版本号
    category: str = "fault"  # 分类，如 fault/normal
    description: str = ""  # 说明描述


@dataclass
class ConditionRuleRef:
    rule_id: str  # 当前 condition 节点使用的规则 ID
    inputs: dict[str, str] = field(default_factory=dict)  # 规则输入名到上下文字段路径的映射
    expected: bool = True  # 期望的规则结果，通常为 true


@dataclass
class BTNodeSpec:
    node_id: str  # 节点唯一 ID
    node_type: BTNodeType  # 节点类型
    name: str  # 节点名称
    tool: str = ""  # action 节点关联工具名
    args: dict[str, Any] = field(default_factory=dict)  # action 节点参数
    rule: ConditionRuleRef | None = None  # condition 节点关联规则
    prompt: str = ""  # 输入节点提示词
    children: list["BTNodeSpec"] = field(default_factory=list)  # 子节点
    success_message: str = ""  # 成功提示
    failure_message: str = ""  # 失败提示


@dataclass
class PlaybookSpec:
    meta: PlaybookMeta  # Playbook 元信息
    root: BTNodeSpec  # 行为树根节点
    input_fields: list[str] = field(default_factory=list)  # 启动时所需输入字段
    tags: list[str] = field(default_factory=list)  # 检索或分类标签


@dataclass
class PlaybookExecutionState:
    playbook_id: str  # 当前执行的 playbook ID
    current_node_id: str = ""  # 当前 playbook 内部执行节点 ID
    completed_nodes: list[str] = field(default_factory=list)  # 已完成节点列表
    failed_nodes: list[str] = field(default_factory=list)  # 失败节点列表
    waiting_input_field: str = ""  # 正在等待的输入字段
    passed: bool | None = None  # 当前 playbook 是否通过
```

说明：

- `condition` 节点表示“纯规则判断节点”，输入来自当前上下文，不先调用工具
- `condition` 节点必须包含 `rule`
- `action` 节点表示“执行工具节点”，不直接包含规则判断
- 如果需要“先执行工具，再判断输出”，则拆成两个节点：
  - `action` 先产出工具结果
  - 后续 `condition` 再对上下文中的工具结果做判断
- `PlaybookExecutionState` 只描述单个 Playbook 的执行现场
- `PlaybookExecutionState.current_node_id` 是 playbook 内部节点位置，不等同于 `RuntimeState.current_step`
- 当系统当前未走 playbook 路径时，可以不存在 `PlaybookExecutionState`
- `ConditionRuleRef` 定义“当前 condition 节点要调用哪条规则，以及规则输入从哪里取值”
- `RuleCall` 是运行时真正发给 `Rule Engine` 的调用对象
- `RuleResult` 返回后，由 Playbook 根据 `expected` 决定节点是否通过以及下一步走向

### 11.8 行为树运行时数据结构

```python
@dataclass
class BlackboardSnapshot:
    current_node_id: str  # 快照时的当前节点 ID
    observations: dict[str, Any] = field(default_factory=dict)  # 已观察到的事实
    variables: dict[str, Any] = field(default_factory=dict)  # 解析后的变量
    tool_outputs: dict[str, Any] = field(default_factory=dict)  # 工具输出缓存


@dataclass
class InterruptState:
    interrupted: bool = False  # 是否已中断
    reason: str = ""  # 中断原因
    current_node_id: str = ""  # 中断时所在节点
    blackboard: BlackboardSnapshot | None = None  # 中断时的黑板快照


@dataclass
class NodeExecutionResult:
    node_id: str  # 节点 ID
    status: Literal["success", "failure", "running", "interrupted"]  # 节点结果状态
    output: dict[str, Any] = field(default_factory=dict)  # 节点输出
    rule_result: "RuleResult | None" = None  # 当前节点关联的规则判断结果
    message: str = ""  # 节点说明消息
```

说明：

- 这一组结构仅用于 playbook / 行为树内部执行快照
- `BlackboardSnapshot` 不是系统级独立主结构，只是行为树执行器内部概念
- 系统级运行共享状态仍以 `RuntimeState + ShortMemory` 为主

### 11.9 Tool 平台数据结构

```python
@dataclass
class ToolSchemaField:
    name: str  # 参数名
    field_type: str  # 参数类型
    required: bool = True  # 是否必填
    description: str = ""  # 参数说明


@dataclass
class ToolSpec:
    tool_name: str  # 工具名称
    category: str  # 工具分类
    description: str  # 工具描述
    risk_level: RiskLevel = "low"  # 风险等级
    input_schema: list[ToolSchemaField] = field(default_factory=list)  # 输入参数定义
    output_schema: list[ToolSchemaField] = field(default_factory=list)  # 输出结果定义


@dataclass
class ToolCall:
    call_id: str  # 工具调用 ID
    tool_name: str  # 工具名
    params: dict[str, Any]  # 调用参数
    session_id: str  # 所属会话 ID
    task_id: str  # 所属任务 ID


@dataclass
class ToolResult:
    call_id: str  # 对应的工具调用 ID
    tool_name: str  # 工具名
    success: bool  # 是否执行成功
    status: str  # 统一状态: completed / failed / blocked / unavailable / rejected
    facts: dict[str, Any] = field(default_factory=dict)  # 面向规则和后续流程的结构化事实
    summary: str = ""  # 给 LLM / 前端展示的简短摘要
    data: dict[str, Any] = field(default_factory=dict)  # 补充载荷，业务输出统一放在 data.output
    error: str = ""  # 错误码或错误摘要；成功时通常为空
    raw_output: str = ""  # 原始输出文本，优先 stdout，否则回退 stderr
```

约定：

- `success` 只表达“工具本次执行是否成功”
- `status` 只表达“工具当前处于什么状态”，必须属于 `completed / failed / blocked / unavailable / rejected`
- `summary` 必须始终可读，优先面向前端展示和 LLM 回灌
- `error` 成功时为空字符串，失败时写错误码或错误摘要
- `data.output` 承载业务输出；不要再把 `exit_code/stdout/stderr` 之类字段额外漂到顶层

### 11.10 SSH 管理数据结构

```python
@dataclass
class RobotConnectionConfig:
    robot_ref: str = ""  # 机器人引用标识
    host: str = ""  # 机器人 IP 或主机名
    port: int = 22  # SSH 端口
    username: str = ""  # SSH 用户名
    password: str = ""  # SSH 密码
    private_key_path: str = ""  # 私钥路径
    ros_version: str = ""  # ROS 版本
    workspace: str = ""  # 远端工作空间路径
    setup_script: str = ""  # 环境加载脚本


@dataclass
class SSHConnectionState:
    connected: bool = False  # 当前是否已连接
    robot_ref: str = ""  # 当前连接对应的机器人引用
    host: str = ""  # 当前连接主机
    port: int = 22  # 当前连接端口
    username: str = ""  # 当前连接用户名
    last_error: str = ""  # 最近一次连接错误
    connected_at: str = ""  # 建连时间


@dataclass
class RemoteCommand:
    command: str  # 远端执行命令
    timeout_sec: int = 30  # 超时时间
    cwd: str = ""  # 工作目录
    env: dict[str, str] = field(default_factory=dict)  # 环境变量


@dataclass
class RemoteCommandResult:
    success: bool  # 是否执行成功
    exit_code: int = 0  # 退出码
    stdout: str = ""  # 标准输出
    stderr: str = ""  # 标准错误
```

### 11.11 Rule Engine 数据结构

```python
@dataclass
class RuleCondition:
    field: str  # 待判断字段路径
    op: str  # 比较操作符
    value: Any = None  # 目标值


@dataclass
class RuleSpec:
    rule_id: str  # 规则 ID
    name: str  # 规则名称
    conditions: list[RuleCondition] = field(default_factory=list)  # 判断条件列表


@dataclass
class RuleCall:
    rule_id: str  # 调用的规则 ID
    inputs: dict[str, Any] = field(default_factory=dict)  # Playbook 传入的判断输入


@dataclass
class RuleResult:
    rule_id: str  # 对应规则 ID
    passed: bool  # 判断结果，true 表示条件成立
```

说明：

- `RuleCondition` 表示最基础的单条判断条件
- `RuleSpec` 表示可注册、可复用的通用规则定义
- `RuleCall` 是 Runtime / Playbook 发给 Rule Engine 的标准调用对象
- `RuleResult` 是统一返回格式，便于写入 `ShortMemory.rule_results`

### 11.11.1 Runtime Workflow 数据结构

```python
@dataclass
class ConfirmationRequest:
    request_id: str  # 确认请求 ID
    session_id: str  # 会话 ID
    task_id: str  # 任务 ID
    node_path: str  # 当前节点路径
    message: str  # 给用户展示的确认信息
    options: list[str] = field(default_factory=list)  # 候选选项


@dataclass
class ResumeToken:
    token: str  # 恢复令牌
    session_id: str  # 会话 ID
    task_id: str  # 任务 ID
    resume_from_step: str = ""  # 恢复步骤
    payload: dict[str, Any] = field(default_factory=dict)  # 恢复所需附加数据


@dataclass
class WorkflowEvent:
    event_id: str  # 事件 ID
    session_id: str  # 会话 ID
    task_id: str  # 任务 ID
    event_type: str  # 事件类型
    payload: dict[str, Any] = field(default_factory=dict)  # 事件载荷
    created_at: str = ""  # 事件时间
```

说明：

- `ConfirmationRequest` 对应 `runtime/workflow/confirmation.py`
- `ResumeToken` 对应 `runtime/workflow/resume.py`
- `WorkflowEvent` 对应 `runtime/workflow/events.py`
- `playbook_state.py` 负责把 playbook 内部执行态投影为前端和 Runtime 可消费的结构

### 11.12 Permission Guard 数据结构

这一部分仅作为预留设计，当前版本不实现。

```python
@dataclass
class PermissionPolicy:
    tool_name: str  # 受控工具名
    risk_level: RiskLevel  # 风险等级
    require_confirm: bool = False  # 是否需要人工确认
    allowed_roles: list[str] = field(default_factory=list)  # 允许执行的角色


@dataclass
class PermissionDecision:
    tool_name: str  # 工具名
    allowed: bool  # 是否允许执行
    risk_level: RiskLevel  # 判定后的风险等级
    reason: str = ""  # 判定理由
```

### 11.13 Diagnosis Summary 数据结构

```python
@dataclass
class EvidenceItem:
    source: str  # 证据来源，如 tool/rule/doc
    content: str  # 证据内容
    confidence: float = 0.0  # 证据置信度


@dataclass
class SolutionItem:
    title: str  # 方案标题
    detail: str  # 方案描述
    auto_fix: bool = False  # 是否支持自动修复


@dataclass
class DiagnosisSummary:
    evidence: list[EvidenceItem] = field(default_factory=list)  # 汇总证据
    solutions: list[SolutionItem] = field(default_factory=list)  # 汇总方案
    final_answer: str = ""  # 最终输出答案
```

### 11.14 模块之间共享的最小上下文

```python
@dataclass
class RuntimeEnvelope:
    session: SessionState  # 会话上下文
    task: TaskState  # 任务上下文
    diagnosis: DiagnosisSummary  # 最终诊断结果对象
    robot_config: RobotConnectionConfig  # 当前机器人连接配置
```

默认约定：

- Gateway 负责创建 `ChatRequest` 和 `RuntimeEnvelope`
- Session Manager 负责维护 `SessionState` 与 `TaskState`
- Runtime 负责持有并管理 `RuntimeState`
- LangGraph 负责驱动节点读写 `RuntimeState`
- `DiagnosisSummary` 只承载最终汇总结果
- SSHManager 只消费 `RobotConnectionConfig` 与 `RemoteCommand`
- Prompt 模块只提供 Prompt Builder，不直接参与状态持久化

机器人切换约定：

```text
用户发起切换机器人
  ↓
SessionState.current_robot_ref 更新
  ↓
关闭当前 SSH 实例
  ↓
加载新的 RobotConnectionConfig
  ↓
建立新的 SSH 实例
  ↓
更新 SSHConnectionState
```

## 12. 消息结构

这一节描述模块之间或对外接口常用的消息载荷示例，不等同于内部完整运行时结构。

### ChatRequest

```json
{
  "session_id": "s001",
  "user_id": "u001",
  "request_id": "req_001",
  "content": "机器人导航不了",
  "interrupt": false,
  "resume": false
}
```

### ToolCall

```json
{
  "call_id": "call_001",
  "tool_name": "topic_monitor",
  "session_id": "s001",
  "task_id": "t001",
  "params": {
    "topic": "/scan"
  }
}
```

### ToolResult

```json
{
  "call_id": "call_001",
  "tool_name": "topic_monitor",
  "success": true,
  "status": "completed",
  "facts": {
    "topic": "/scan",
    "exists": true,
    "has_msg": false
  },
  "summary": "topic /scan 已注册，但暂未收到消息。",
  "data": {
    "params": {
      "topic": "/scan"
    },
    "output": {
      "exists": true,
      "has_msg": false,
      "age": -1.0,
      "hz": 0,
      "last_msg_time": ""
    }
  },
  "error": "",
  "raw_output": "topic exists, hz=0"
}
```

### RuleResult

```json
{
  "rule_id": "rule_1",
  "passed": false
}
```

### DiagnosisResponse

```json
{
  "session_id": "s001",
  "task_id": "t001",
  "status": "completed",
  "summary": "发现雷达无数据，当前判断雷达链路异常。",
  "evidence": [
    "/scan频率为0"
  ],
  "solutions": [
    "检查雷达连接"
  ],
  "continuation_token": "",
  "playbook_id": "lidar_no_data"
}
```

## 13. 消息流转

### 命中 Playbook

```text
用户
  ↓
Gateway
  ↓
Session Manager
  ↓
Runtime Service
  ↓
LangGraph Orchestrator
  ↓
Route Prompt
  ↓
Playbook Match
  ↓
Playbook Load
  ↓
Behavior Tree Execute
  ↓
Tool Executor
  ↓
Rule Engine
  ↓
Playbook Branch Decision
  ↓
Diagnosis Summary
  ↓
用户
```

### 未命中 Playbook

```text
用户
  ↓
Gateway
  ↓
Session Manager
  ↓
Runtime Service
  ↓
LangGraph Orchestrator
  ↓
Route Prompt
  ↓
Knowledge Retrieve
  ↓
Planner Prompt
  ↓
LLM Planner
  ↓
Tool Planning
  ↓
Tool Executor
  ↓
Rule Engine
  ↓
Diagnosis Summary
  ↓
Summary Prompt
  ↓
用户
```

## 14. 架构总结

```text
RobotClaw =

Runtime Service
+ LangGraph Orchestrator
+ Playbook Engine
+ PyTree Runner
+ Tool Platform
+ SSH Manager
+ Memory
+ Interrupt
+ Rule Engine
+ Diagnosis Summary
```

核心执行链路：

```text
Natural Language
  ↓
Playbook / Knowledge
  ↓
Tool Planning
  ↓
Tool Execute
  ↓
Rule Judge
  ↓
ShortMemory / RuntimeState
  ↓
Diagnosis Summary
```

最终形成一个可扩展、可记忆、可中断、可远程诊断的机器人运维平台。

推荐完整目录结构：

```text
robotclaw/
├── server.py
├── designed.md
├── frontend/
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── assets/
│       ├── robot-full.png
│       ├── robot-tight.png
│       └── ...
├── backend/
│   ├── __init__.py
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── ids.py
│   │   ├── text.py
│   │   └── time.py
│   ├── gateway/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── http.py
│   │   └── models.py
│   ├── session/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── manager.py
│   │   ├── store.py
│   │   └── history.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── manager.py
│   │   ├── short_memory.py
│   │   ├── session_memory.py
│   │   ├── long_memory.py
│   │   └── store.py
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── models.py
│   │   ├── control.py
│   │   └── workflow/
│   │       ├── __init__.py
│   │       ├── context.py
│   │       ├── events.py
│   │       ├── playbook_state.py
│   │       ├── confirmation.py
│   │       └── resume.py
│   ├── langgraph/
│   │   ├── __init__.py
│   │   ├── builder.py
│   │   ├── router.py
│   │   ├── nodes/
│   │       ├── __init__.py
│   │       ├── classify.py
│   │       ├── match.py
│   │       ├── knowledge.py
│   │       ├── plan.py
│   │       ├── execute.py
│   │       ├── analyze.py
│   │       └── summarize.py
│   │   └── prompts/
│   │       ├── __init__.py
│   │       ├── route.py
│   │       ├── planner.py
│   │       ├── answer.py
│   │       ├── summary.py
│   │       └── protocols.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── config.py
│   │   ├── parser.py
│   │   ├── schemas.py
│   │   └── models.py
│   ├── playbook/
│   │   ├── __init__.py
│   │   ├── catalog.py
│   │   ├── loader.py
│   │   ├── matcher.py
│   │   ├── engine.py
│   │   ├── parser.py
│   │   ├── runner.py
│   │   ├── schema.py
│   │   └── models.py
│   ├── rule/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── registry.py
│   │   ├── operators.py
│   │   ├── resolver.py
│   │   ├── schema.py
│   │   └── models.py
│   ├── knowledge/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── loader.py
│   │   ├── splitter.py
│   │   ├── embeddings.py
│   │   ├── vectorstore.py
│   │   ├── retrieval.py
│   │   └── models.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── common.py
│   │   ├── registry.py
│   │   ├── executor.py
│   │   ├── permission_guard.py
│   │   ├── models.py
│   │   ├── ros/
│   │   │   ├── __init__.py
│   │   │   ├── topic_monitor.py
│   │   │   ├── node_status.py
│   │   │   ├── service_call.py
│   │   │   ├── action_check.py
│   │   │   └── param_read.py
│   │   ├── tf/
│   │   │   ├── __init__.py
│   │   │   └── tf_monitor.py
│   │   ├── log/
│   │   │   ├── __init__.py
│   │   │   └── log_search.py
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── config_read.py
│   │   │   └── config_modify.py
│   │   └── shell/
│   │       ├── __init__.py
│   │       └── shell_command.py
│   ├── ssh/
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   ├── client.py
│   │   └── models.py
│   └── diagnosis/
│       ├── __init__.py
│       ├── summarizer.py
│       └── models.py
├── playbooks/
│   ├── navigation_failure.yaml
│   ├── localization_failure.yaml
│   └── lidar_no_data.yaml
├── data/
│   ├── knowledge/
│   │   ├── faq/
│   │   ├── manuals/
│   │   └── troubleshooting/
│   ├── vectorstore/
│   └── memory/
├── tests/
│   ├── gateway/
│   ├── session/
│   ├── memory/
│   ├── runtime/
│   ├── langgraph/
│   ├── playbook/
│   ├── rule/
│   ├── tools/
│   ├── ssh/
│   ├── diagnosis/
│   └── knowledge/
└── scripts/
    ├── ingest_knowledge.py
    ├── build_vectorstore.py
    └── dev_server.sh
```

其中：

- `runtime/service.py` 负责运行入口与运行时协调
- `runtime/control.py` 负责中断、恢复、取消等控制能力
- `runtime/workflow/` 负责运行中断、人工确认、playbook 实时状态与恢复上下文
- `runtime/workflow/events.py` 负责运行事件定义与广播载荷
- `runtime/workflow/playbook_state.py` 负责 playbook 执行状态投影
- `runtime/workflow/confirmation.py` 负责确认请求构造与确认结果回写
- `runtime/workflow/resume.py` 负责恢复令牌与恢复参数处理
- `runtime/workflow/context.py` 可选，用于变量展开与上下文读写
- `langgraph/builder.py` 负责构建 LangGraph 主图
- `langgraph/router.py` 负责图条件路由规则
- `langgraph/nodes/` 负责节点逻辑
- `langgraph/prompts/` 负责为节点生成 Prompt
- `llm/` 负责统一模型调用、结构化解析与模型配置
- `session/store.py` 负责 Session / Task 的持久化抽象
- `session/history.py` 负责会话历史拼装与摘要预览
- `session/manager.py` 负责会话创建、任务切换、状态更新
- `memory/short_memory.py` 负责单任务短期记忆
- `memory/session_memory.py` 负责单会话会话记忆
- `memory/long_memory.py` 负责长期记忆沉淀与检索
- `memory/manager.py` 负责三层 memory 的统一路由入口
- `playbook/` 负责 Playbook 的加载、匹配、Schema 校验、解析和执行
- `rule/` 负责通用规则注册、Schema 校验和判断执行
- `rule/operators.py` 负责通用比较运算
- `rule/resolver.py` 负责字段路径解析与上下文取值
- `knowledge/` 负责知识库离线准备与运行时检索
- `tools/base.py` 负责工具定义与运行时上下文抽象
- `tools/registry.py` 负责工具注册、检索与统一调用入口
- `tools/` 负责工具权限控制和分类实现
- `ssh/` 负责唯一 SSH 连接与命令执行
- `diagnosis/` 负责最终诊断总结与用户答案组织

参考 `old/backend/runtime` 的设计吸收：

- 保留 `playbook`、`rule`、`tools`、`workflow` 四层分工
- 保留 `tool definition + tool registry + tool runtime context` 的分层方式
- 保留 `playbook schema` 与 `rule schema` 的显式校验层
- 保留 `playbook_state / confirmation / resume` 这类运行时状态组件
- 但新结构中将编排层单独提升到 `langgraph/`，不再与 runtime 本身混放
