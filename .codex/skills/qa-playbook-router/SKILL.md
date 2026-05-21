---
name: qa-playbook-router
description: 输入一段文本或一个文件，先提取内容并按条目判断更适合走 QA 结构化消息还是 playbook 生成；支持混合型文档分流，QA 转交 `frontend-qa-message-generator`，playbook 转交 `fault-playbook-generator`。
---

# Text To QA Or Playbook Router

这个 skill 用于做内容分流。

输入可能是一段话，也可能是一个文件路径。你的任务不是直接完成 QA 或 playbook 产物，而是先读取内容、必要时拆成多个条目、判断类型，再把后续工作交给合适的 skill。

## 适用场景

- 用户给一段自然语言，希望系统自己判断该产出 QA 还是 playbook
- 用户给一个 `.md`、`.txt` 或其他文本文件，希望从文件内容自动路由
- 上游输入混杂了问题描述、解决方案、经验记录、FAQ 片段，需要先分流
- 希望统一入口，减少人工判断应该调用哪个 skill

如果用户已经明确说“就是要 QA”或“就是要 playbook”，不要绕路，直接用对应 skill。

## 输入

支持两类输入：

1. 一段直接提供的文本
2. 一个本地文本文件路径

如果输入是文件路径，先读取文件内容，再做判断。

如果文件很长，先提取与“问题现象、处理步骤、结论、协议/接口”最相关的段落，不要把整份长文逐字搬运进输出。

如果输入明显包含多条独立问题，不要只做整篇级别的一次性判断；先按问题拆分，再逐条路由。

## 目标

你要先输出一个简短的路由判断，再继续使用目标 skill 完成后续工作。

路由目标只有两个：

- `frontend-qa-message-generator`
- `fault-playbook-generator`

如果输入是混合型材料，允许同时命中两个目标 skill。不要为了只给一个总分类，牺牲条目级判断准确性。

## 判断规则

### 优先判为 QA 的情况

满足以下特征时，默认走 `frontend-qa-message-generator`：

- 文本本质上是在问答、解释、说明、回复前端
- 输出目标更像“给人看的答案”而不是“给 agent 执行的模板”
- 内容以 `Q/A`、FAQ、客服回复、排查结论、说明文案为主
- 没有明确要求产出 `playbook.yaml`、`rules.yaml` 或行为树结构
- 没有稳定的分步执行意图，只是整理成前端展示消息

这类内容即使提到原因、建议、简单步骤，也仍然优先算 QA，只要它的核心价值是“告诉人答案是什么”。

### 优先判为 Playbook 的情况

满足以下特征时，走 `fault-playbook-generator`：

- 文本目标是沉淀成可重复执行的故障处理模板
- 明确包含问题描述、排查顺序、恢复动作、停止条件、升级条件
- 明确提到协议文档、接口名、topic/service/action/message
- 用户希望产出 `playbook.yaml`、`rules.yaml`、行为树 `root` 或脚本化步骤
- 内容重点不是“回答用户”，而是“指导 agent 按步骤执行”

以下信号出现两个及以上时，默认优先判为 playbook 候选，而不是 QA：

- 有明确故障现象
- 有固定排查顺序，步骤前后顺序不能随意打乱
- 有恢复动作，例如重启、切换、重新加载、重新部署
- 有验证动作，例如查看状态、检查话题、确认接口返回值
- 有明确升级条件或联系对象
- 明确引用容器、服务、topic、service、action、message、配置项、命令

像“如何排查”“如何恢复”“出现某错误码后按什么顺序处理”这类问题，不要因为它采用问句形式，就自动判成 QA。

### 混合型输入的判断

满足以下任一情况时，先拆条再判断，不要整篇只给一个总路由：

- 文本里包含多条以标题、小节、问句、编号分隔的独立问题
- 同一文件里同时存在 FAQ 型说明和可执行排查流程
- 某些条目明显偏展示型回答，另一些条目明显偏执行型步骤

拆条后逐条判断：

- 展示型、说明型、结论型条目走 QA
- 稳定排查链路、恢复流程、接口操作链路走 playbook

## 默认策略

- 单条内容无法确定时，默认先走 `frontend-qa-message-generator`
- 多条内容无法整体确定时，优先拆条，不要直接整篇默认走 QA
- 只有在“明显要沉淀成标准执行模板”时才走 `fault-playbook-generator`
- 不要因为出现“解决方案”“步骤”几个字就草率判成 playbook
- 也不要因为内容写成问答形式，就忽略其中已经稳定成型的执行流程

## 工作流

1. 识别输入来源
- 如果是直接文本，直接使用
- 如果是文件路径，先读取文件

2. 判断是否需要拆条
- 如果输入只围绕一个问题，保持单条处理
- 如果输入包含多个独立问题，先按问题切分
- 每个条目尽量保留“问题 + 回答/步骤/结论”的最小闭环

3. 提取核心内容
- 提炼问题现象
- 提炼回答、方案、步骤、结论
- 如果有协议/接口文档线索，单独标记

4. 做路由判断
- 先按条目判断输出是偏“展示型回答”还是偏“执行型模板”
- 如果全部条目都同类，再给单一路由
- 如果条目混合，给混合路由，并列出各条目去向
- 给出一句简短理由

5. 继续调用目标 skill
- 如果某条是 QA，按 [`../frontend-qa-message-generator/SKILL.md`](../frontend-qa-message-generator/SKILL.md) 的要求生成结果，并默认写入 `doc/qa.md`
- 如果某条是 playbook，按 [`../fault-playbook-generator/SKILL.md`](../fault-playbook-generator/SKILL.md) 的要求生成结果
- 如果是混合型输入，先完成 QA 条目落库，再为 playbook 条目逐条生成 playbook，不要强行二选一

## 输出要求

先给出路由判断，再继续完成目标产物。

路由判断建议至少包含：

- `route`
- `reason`

如果是混合型输入，额外包含：

- `mode`
- `qa_items`
- `playbook_items`

示例：

```json
{
  "route": "frontend-qa-message-generator",
  "reason": "内容以问答和解释为主，目标更适合直接返回前端展示。"
}
```

或：

```json
{
  "route": "fault-playbook-generator",
  "reason": "内容包含问题、处理步骤和执行条件，更适合沉淀为标准 playbook。"
}
```

混合型示例：

```json
{
  "route": "mixed",
  "mode": "split-by-item",
  "reason": "输入包含 FAQ 型说明和可执行排查流程，适合按条目分流。",
  "qa_items": [
    "V1.4.0 版本支持哪些激光雷达？"
  ],
  "playbook_items": [
    "底盘未上报电量信息如何排查？"
  ]
}
```

完成路由判断后，不要停在分类结果；继续产出目标 skill 要求的最终结果。

如果最终路由到 QA：

- 默认将整理后的 QA 结果写入 `doc/qa.md`
- 如果输入本身包含多条 QA，逐条整理并写入 `doc/qa.md`
- 写入前先查重；命中同一问题时更新原条目，不重复追加近义问题
- 除非用户明确指定其他目标文件，否则不要只在终端返回结果而不落库

如果最终是混合路由：

- QA 条目默认写入 `doc/qa.md`
- playbook 条目不要塞进 QA 文档里凑数
- 对每个 playbook 条目单独整理问题、步骤、恢复动作、验证动作、升级条件，再交给 `fault-playbook-generator`
- 如果用户这次只想先分类或只想先修改 skill，而不是立刻生成 playbook，就停在分类和 skill 修改结果

## 参考

需要样例时，读取 [references/examples.md](references/examples.md)。

具体生成规则分别以这两个 skill 为准：

- [../frontend-qa-message-generator/SKILL.md](../frontend-qa-message-generator/SKILL.md)
- [../fault-playbook-generator/SKILL.md](../fault-playbook-generator/SKILL.md)

## 质量检查

交付前至少自查这些点：

- 是否真的读取了输入文本或文件内容，而不是只看文件名猜测
- 路由理由是否简洁、具体
- 是否把“前端展示答案”和“agent 执行模板”区分清楚
- 多条内容时，是否先判断了要不要拆条
- 是否避免把整份混合文档粗暴地只归到 QA
- 模糊场景下是否按默认策略优先走 QA
- 路由后是否继续按目标 skill 产出最终结果，而不是只给分类结论
- 如果路由到 QA，是否已经将结果写入 `doc/qa.md`，并按问题去重更新
- 如果某条已经具备稳定排查链路，是否认真评估过它应不应该转成 playbook
