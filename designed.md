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
│ LangGraph Runtime   │
├─────────────────────┤
│ Runtime State       │
│ Route Decision      │
│ Knowledge Selection │
│ Tool Planning       │
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
                │ Rule Engine         │
                │ Tool Registry       │
                └──────────┬──────────┘
                           │
                           ▼
┌─────────────────────┐
│     SSH Manager     │
├─────────────────────┤
│ Current Config      │
│ Current SSH Client  │
└──────────┬──────────┘
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

### 4.3 Memory Manager

分三层：

#### Short Memory

当前任务相关信息：

- 工具结果
- 规则结果
- 执行节点

#### Session Memory

当前会话相关信息：

- 聊天记录
- 上下文

#### Long Memory

长期记忆：

- 历史故障
- 历史诊断
- 历史解决方案

### 4.4 Runtime

采用：

- `LangGraph`

职责：

- 路由
- 状态流转
- 流程编排
- 中断恢复

### 4.5 Playbook Engine

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

### 4.6 Knowledge / RAG

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
保存 Blackboard
  ↓
保存当前 Node
  ↓
返回 Interrupted
```

恢复流程：

```text
恢复 Blackboard
  ↓
恢复 CurrentNode
  ↓
继续 Tick
```

### 5.2 行为树支持动态变量

支持来源：

- 用户输入
- Session 变量
- Blackboard 变量
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

## 10. Diagnosis Blackboard

在 LangGraph 方案下，诊断过程态由 Runtime State 承载，这里不再单独设计一套完整 Blackboard 主结构。

这一节仅保留“最终诊断结果对象”，用于汇总对用户有价值的输出：

```python
class DiagnosisSummary:
    evidence
    solutions
    final_answer
```

说明：

- 运行过程中的工具结果、规则结果、当前节点等信息，放在 LangGraph `RuntimeState`
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


@dataclass
class SessionMemory:
    session_id: str  # 关联会话 ID
    chat_history: list[ChatTurn] = field(default_factory=list)  # 会话聊天历史
    variables: dict[str, Any] = field(default_factory=dict)  # 会话级共享变量


@dataclass
class LongMemoryRecord:
    memory_id: str  # 长期记忆记录 ID
    category: Literal["fault", "diagnosis", "solution", "experience"]  # 记忆分类
    title: str  # 记忆标题
    content: str  # 记忆正文
    tags: list[str] = field(default_factory=list)  # 标签
```

### 11.5 Runtime 数据结构

设计原则：

- `RuntimeState` 只放图执行过程中必须跨节点共享的信息
- SSH 连接信息、切分建库过程、工具原始结果、最终诊断结果不直接堆进 `RuntimeState`
- `RuntimeState` 更偏控制面状态，不替代 `SessionState`、`TaskState`、`DiagnosisSummary`
- 知识库的离线构建不属于 `Runtime`，但运行时检索结果需要进入 `RuntimeState`
- `RuntimeState` 是 LangGraph 主 state，不直接承担任务生命周期管理

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

- `RuntimeState` 是 LangGraph 图在节点之间流转的共享运行态
- `RuntimeState.current_step` 表示图当前执行到的节点或阶段
- `RuntimeState.finished` 只表示图本轮是否收口，不等同于 `TaskState.status`
- 当图进入 Playbook 路径时，`RuntimeState` 持有对当前 Playbook 的引用，但 Playbook 内部进度由 `PlaybookExecutionState` 管理

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
    query: str  # 检索查询文本
    top_k: int  # 召回数量
    channels: list[str] = field(default_factory=list)  # 检索通道，如 faq/bm25/vector


@dataclass
class RetrievalHit:
    chunk_id: str  # 命中的切片 ID
    filename: str  # 来源文件名
    score: float  # 检索得分
    snippet: str = ""  # 命中文本片段
    channel: str = ""  # 来源检索通道


@dataclass
class RetrievalResult:
    query: str  # 原始查询
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
    data: dict[str, Any] = field(default_factory=dict)  # 结构化结果
    error: str = ""  # 错误信息
    raw_output: str = ""  # 原始输出文本
```

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

### 11.13 Diagnosis Blackboard 数据结构

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
- RuntimeState 承载运行过程中的共享状态
- `DiagnosisSummary` 只承载最终汇总结果
- SSHManager 只消费 `RobotConnectionConfig` 与 `RemoteCommand`

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
  "data": {
    "has_msg": false,
    "hz": 0
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
LangGraph Runtime
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
LangGraph Runtime
  ↓
Knowledge Retrieve
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
用户
```

## 14. MVP 范围

### Playbook

- `navigation_failure`
- `localization_failure`
- `lidar_no_data`

### Tool

- `topic_monitor`
- `node_status`
- `tf_monitor`
- `log_search`
- `restart_service`

### Memory

- Session
- History

### Interrupt

- 暂停
- 恢复
- 取消

### SSH

- 单活跃机器人
- 前端配置
- 支持 IP 切换

## 15. 架构总结

```text
RobotClaw =

LangGraph Runtime
+ Playbook Engine
+ PyTree Runner
+ Tool Platform
+ SSH Manager
+ Memory
+ Interrupt
+ Rule Engine
+ LLM Summary
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
Blackboard
  ↓
LLM Summary
```

最终形成一个可扩展、可记忆、可中断、可远程诊断的机器人运维平台。
