from __future__ import annotations

from backend.common import infer_title, next_request_id
from backend.models import ChatRequest, ChatResponse, DiagnosisSummary, EvidenceItem, RuntimeEnvelope, RuntimeState, SolutionItem


class RuntimeService:
    """Current MVP runtime keeps the LangGraph-facing state explicit even before full graph execution lands."""

    def build_request(self, session_id: str, user_id: str, content: str) -> ChatRequest:
        return ChatRequest(
            session_id=session_id,
            user_id=user_id,
            content=content,
            request_id=next_request_id(),
        )

    def initial_state(self, envelope: RuntimeEnvelope, request: ChatRequest) -> RuntimeState:
        return RuntimeState(
            session_id=envelope.session.session_id,
            task_id=envelope.task.task_id,
            user_query=request.content,
            route="chat",
            current_step="gateway_received",
        )

    def run(self, envelope: RuntimeEnvelope, request: ChatRequest, connected: bool) -> tuple[RuntimeState, DiagnosisSummary, ChatResponse]:
        state = self.initial_state(envelope, request)
        state.current_step = "runtime_answering"

        diagnosis = envelope.diagnosis
        diagnosis.evidence = [
            EvidenceItem(source="user", content=request.content, confidence=1.0),
        ]

        if connected and envelope.robot_config.robot_ref:
            diagnosis.solutions = [
                SolutionItem(
                    title="进入真实诊断流程",
                    detail=f"当前已连接 {envelope.robot_config.robot_ref}，下一步可以继续接入真实 Runtime 节点。",
                )
            ]
            diagnosis.final_answer = (
                f"已收到你的问题：“{request.content}”。\n\n"
                f"当前机器人 {envelope.robot_config.robot_ref}（{envelope.robot_config.host}） 已连接，"
                "下一步我们可以继续接入真实诊断流程。"
            )
        else:
            diagnosis.solutions = [
                SolutionItem(
                    title="连接机器人",
                    detail="如果后续需要执行机器人相关操作，请先在右侧连接目标机器人。",
                )
            ]
            diagnosis.final_answer = (
                f"已收到你的问题：“{request.content}”。\n\n"
                "当前前后端交互已经打通。如果你需要执行机器人相关操作，"
                "可以先在右侧连接目标机器人。"
            )

        state.current_step = "completed"
        state.finished = True
        response = ChatResponse(
            session_id=envelope.session.session_id,
            task_id=envelope.task.task_id,
            status="completed",
            summary=diagnosis.final_answer,
            playbook_id="",
            data={
                "evidence": [item.content for item in diagnosis.evidence],
                "solutions": [item.detail for item in diagnosis.solutions],
                "title_hint": infer_title(request.content, envelope.task.title),
            },
        )
        return state, diagnosis, response
