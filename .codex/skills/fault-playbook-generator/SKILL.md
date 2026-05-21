---
name: fault-playbook-generator
description: 从故障问题、解决方案和协议文档生成脚本化标准 playbook，适合整理 ROS 接口、可执行步骤、恢复策略和升级条件。
---

# Playbook Generator

## 用途

当用户给出一个故障问题、对应解决方案，外加一份协议文档时，生成一份标准 playbook。
重点是把“经验描述”整理成稳定、可执行、可复用的脚本化结构，而不是临场编排自然语言排查。

## 何时使用

- 需要把一个故障案例沉淀成固定排查模板
- 需要从协议文档里抽取真实存在的 topic / service / action / message
- 需要把人工经验转换成可给 agent 执行的脚本步骤
- 需要为现有 playbook 补齐 `script`、`escalation_notes`
- 需要把一个问题拆成一个目录，目录里放 `playbook.yaml` 和可选的辅助文件
- 需要明确“脚本写在哪里”和“后端怎么执行”

## 输入

- `问题描述`
- `解决方案` 或 `排查思路`
- `protocol.md` 或同类协议文档
- 可选：现有 `fault_playbooks/` 目录

## 输出

输出一套完整的 playbook 目录内容，**必须同时生成** `playbook.yaml` 和 `rules.yaml`，并且两者都要按照最新模板生成。至少包含：

- `id`
- `title`
- `root`
- `escalation_notes`
- `execution_notes`
- `rules`（如果该 playbook 需要独立规则文件）

输出时要明确标注：

- `playbook.yaml` 必须严格对齐 [`references/playbook.template.yaml`](references/playbook.template.yaml)
- `rules.yaml` 必须严格对齐 [`references/rules.template.yaml`](references/rules.template.yaml)

## 工作流

1. 先读取最新模板作为唯一结构参考：
   - [`references/playbook.template.yaml`](references/playbook.template.yaml)
   - [`references/rules.template.yaml`](references/rules.template.yaml)
2. 先输出 `config/fault_playbooks/<playbook_id>/playbook.yaml`，并保证字段、层级、字段名都与 `playbook.template.yaml` 保持一致
3. 再输出同目录下的 `config/fault_playbooks/<playbook_id>/rules.yaml`，并保证字段、层级、字段名都与 `rules.template.yaml` 保持一致
4. 再从问题描述里提炼出用户会怎么说这类故障，写成 `title`
5. 默认不要写 `match_rules`，让 LLM 负责意图判断和路由
6. 每个节点的`display_name`要尽量对应用户的自然语言描述，保持可读性和可理解性
7. 再从解决方案里提炼检查顺序，写成行为树 `root`
8. 默认优先用 `sequence`、`selector`、`condition`、`action`、`call_playbook`、`result` 这些节点表达流程，不要先退回旧 `script`
9. `condition` / `action` 这类叶子节点都要包含 `tool_name`、`arguments`、`assert_ref` 或 `assert`，必要时加 `failure_message`
10. 如果需要等现场状态稳定后再验证，可以在叶子节点上加 `wait_seconds`
11. 如果需要连续订阅多次再确认，继续用 `confirm_times`
12. `rules.yaml` 只写规则定义，规则 id 尽量使用 `rule_1`、`rule_2` 这类通用命名
13. 只从 `protocol.md` 里选真实存在的接口名、类型名和字段名
14. 如果方案里包含恢复动作，把它写进 `action` 节点，默认加人工确认
15. 如果某一步其实是在处理另一个独立问题，优先写成 `call_playbook`
16. 如果信息还不够明确，写进 `escalation_notes`，不要硬编
17. 最后检查是否符合可执行性和一致性：接口名真实、步骤顺序合理、没有空话，且 `playbook.yaml` / `rules.yaml` 都能直接落到 `config/fault_playbooks/<playbook_id>/`
18. 输出完成后，必须自己逐项对比生成内容和最新模板，确认字段名、层级、必填项、顺序和语义都对应上；如果不一致，要先修正再输出最终结果

## 规则

- 所有的ros接口都必须从 `protocol.md` 里抽取，不能凭空编造
- 不把自然语言建议写成无法执行的步骤
- 优先把检查步骤写成“能验证什么”，而不是“应该怎么想”
- 默认优先用行为树 `root`，新增 playbook 不要再默认产出旧 `script`
- “先判断，不满足再恢复”优先写成 `selector`
- “先做 A，再做 B，再做 C”优先写成 `sequence`
- 连续确认恢复状态时，优先用 `confirm_times`，不要把“等一会儿再看”写进自然语言
- 默认不要写 `match_rules`，由 LLM 负责路由到对应 playbook
- 默认让脚本前半段偏只读，恢复步骤偏保守
- 如果 playbook 面向 agent 执行，叶子节点里要对应到具体接口或工具类型
- 如果需要直接给出结论，不要硬写失败跳转，优先用 `result`
- 这个仓库里脚本化 playbook 的落点是 `config/fault_playbooks/<playbook_id>/playbook.yaml`，执行入口在 `backend/agent/playbooks/executor.py`
- `references/playbook.template.yaml` 和 `references/rules.template.yaml` 是本 skill 的结构真源，后续生成和修改都应优先对齐这两份文件
- 默认生成结果必须是成对文件：`playbook.yaml` + `rules.yaml`，不能只产出其中一个
- 输出完成后必须自检，对照最新模板确认生成内容一一对应
- `call_playbook` 只用于切换到另一个独立子问题，不要拿它当普通跳转标签

## 参考

如果当前工作区里有 `protocol.md`，优先读取它来抽取接口定义。
标准输出格式以 [`references/playbook.template.yaml`](references/playbook.template.yaml) 和 [`references/rules.template.yaml`](references/rules.template.yaml) 为准。
如果没有特别原因，默认输出行为树 `root`，而不是旧 `script`。
如果你需要单独的可执行脚本文件，优先把它放在同目录下，再由后端执行入口按目录加载。
