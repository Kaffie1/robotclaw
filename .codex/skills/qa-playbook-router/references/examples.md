# Examples

## Example 1: Route To QA

输入：

```text
Q: 为什么底盘启动后还是不动？
A: 先确认急停状态，再确认底盘是否已经上电。如果两者都正常，再提供当前报错信息，方便继续判断。
```

路由判断：

```json
{
  "route": "frontend-qa-message-generator",
  "reason": "内容以问答和补充信息为主，更适合整理成前端展示消息。"
}
```

后续：

- 继续使用 `frontend-qa-message-generator`

## Example 2: Route To Playbook

输入：

```text
机器人无法行走。
排查顺序：
1. 检查急停状态。
2. 检查底盘上电状态。
3. 订阅底盘状态 topic，确认 enable 字段。
4. 如果未使能，执行恢复动作并等待 3 秒后复核。
协议见 protocol.md。
```

路由判断：

```json
{
  "route": "fault-playbook-generator",
  "reason": "内容包含明确排查顺序、恢复动作和协议线索，更适合沉淀为可执行 playbook。"
}
```

后续：

- 继续使用 `fault-playbook-generator`
