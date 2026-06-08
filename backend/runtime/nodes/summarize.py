from __future__ import annotations

from backend.runtime.models import RouteDecision, SolutionItem


def build_solutions(
    *,
    connected: bool,
    robot_ref: str,
    host: str,
    analysis: dict[str, str],
) -> list[SolutionItem]:
    if not connected:
        return [
            SolutionItem(
                title="先连接机器人",
                detail="当前已完成问题理解、知识选择和工具规划，但机器人未连接，无法继续采集事实。",
            ),
            SolutionItem(
                title="连接后继续执行",
                detail="连接目标机器人后，可以继续执行 ToolExecutor 并进入真实诊断阶段。",
            ),
        ]

    return [
        SolutionItem(
            title="进入诊断执行阶段",
            detail=f"当前已连接 {robot_ref}（{host}），已完成第一批机器人检查，可继续深化分析。",
        ),
        SolutionItem(
            title="保留自动修复入口",
            detail=f"当前分析结论：{analysis['summary']}。后续可在 PermissionGuard 后挂接自动修复动作。",
        ),
    ]


def compose_answer(
    *,
    query: str,
    trace: list[RouteDecision],
    solutions: list[SolutionItem],
    connected: bool,
    robot_ref: str,
    host: str,
) -> str:
    lines = [f"已收到你的问题：“{query}”。", "", "当前链路按设计完成了以下阶段："]
    for item in trace:
        lines.append(f"- {item.stage}：{item.summary}")
    lines.append("")
    if connected and robot_ref:
        lines.append(f"当前机器人已连接：{robot_ref}（{host}）。")
    else:
        lines.append("当前还没有连接机器人，所以链路停在可执行前的规划/阻塞状态。")
    lines.append("")
    lines.append("建议下一步：")
    for solution in solutions:
        lines.append(f"- {solution.detail}")
    return "\n".join(lines)
