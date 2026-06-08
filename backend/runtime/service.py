from __future__ import annotations

from dataclasses import asdict

from backend.gateway.models import ChatRequest, ChatResponse
from backend.langgraph import run_chat_graph
from backend.knowledge import KnowledgeService
from backend.llm import LLMClient
from backend.memory import MemoryManager
from backend.playbook import PlaybookEngine
from backend.runtime.models import DiagnosisSummary, EvidenceItem, RouteDecision, RuntimeEnvelope, RuntimeState
from backend.runtime.workflow import WorkflowEventBus, WorkflowStore, build_resume_token
from backend.runtime.workflow.models import WorkflowEvent
from backend.shared import infer_title, next_event_id, next_request_id, next_resume_token, now_iso
from backend.tools import ToolExecutor


class RuntimeService:
    def __init__(
        self,
        *,
        playbook_engine: PlaybookEngine | None = None,
        knowledge_service: KnowledgeService | None = None,
        llm_client: LLMClient | None = None,
        tool_executor: ToolExecutor | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        self.playbook_engine = playbook_engine or PlaybookEngine()
        self.knowledge_service = knowledge_service or KnowledgeService()
        self.llm_client = llm_client or LLMClient()
        self.tool_executor = tool_executor or ToolExecutor()
        self.memory_manager = memory_manager or MemoryManager()
        self.workflow_store = WorkflowStore()
        self.event_bus = WorkflowEventBus()

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
        self._publish_event(
            session_id=envelope.session.session_id,
            task_id=envelope.task.task_id,
            event_type="runtime.started",
            payload={"request_id": request.request_id, "query": request.content},
        )
        state, diagnosis = run_chat_graph(
            request=request,
            envelope=envelope,
            state=state,
            connected=connected,
            playbook_engine=self.playbook_engine,
            knowledge_service=self.knowledge_service,
            llm_client=self.llm_client,
            tool_executor=self.tool_executor,
            memory_manager=self.memory_manager,
        )
        self.workflow_store.save_runtime_state(state)
        self._publish_event(
            session_id=envelope.session.session_id,
            task_id=envelope.task.task_id,
            event_type="runtime.completed",
            payload={"current_step": state.current_step, "matched_playbook_id": state.matched_playbook_id},
        )
        response = ChatResponse(
            session_id=envelope.session.session_id,
            task_id=envelope.task.task_id,
            status="completed",
            summary=diagnosis.final_answer,
            playbook_id=state.matched_playbook_id,
            data={
                "trace": [asdict(item) for item in state.trace],
                "evidence": [item.content for item in diagnosis.evidence],
                "solutions": [asdict(item) for item in diagnosis.solutions],
                "planned_tools": [asdict(item) for item in state.planned_tools],
                "tool_results": self.tool_executor.to_payload(state.tool_results),
                "title_hint": infer_title(request.content, envelope.task.title),
                "events": self.drain_events(envelope.task.task_id),
            },
        )
        return state, diagnosis, response

    def interrupt_task(self, session_id: str, task_id: str) -> str:
        runtime_state = self.workflow_store.get_runtime_state(task_id)
        resume_token = build_resume_token(
            token=next_resume_token(),
            session_id=session_id,
            task_id=task_id,
            resume_from_step=runtime_state.current_step if runtime_state else "",
            payload={"current_step": runtime_state.current_step if runtime_state else ""},
        )
        self.workflow_store.save_resume_token(resume_token)
        self._publish_event(
            session_id=session_id,
            task_id=task_id,
            event_type="runtime.interrupted",
            payload={"resume_token": resume_token.token},
        )
        return resume_token.token

    def resume_request(self, session_id: str, task_id: str, content: str, token: str, user_id: str) -> ChatRequest:
        resume_token = self.workflow_store.get_resume_token(token)
        if resume_token is None or resume_token.session_id != session_id or resume_token.task_id != task_id:
            raise ValueError("无效的恢复令牌")
        request = self.build_request(session_id=session_id, user_id=user_id, content=content)
        request.resume = True
        return request

    def get_runtime_payload(self, task_id: str) -> dict:
        state = self.workflow_store.get_runtime_state(task_id)
        if state is None:
            return {"runtime_state": None, "events": []}
        return {
            "runtime_state": {
                "session_id": state.session_id,
                "task_id": state.task_id,
                "route": state.route,
                "matched_playbook_id": state.matched_playbook_id,
                "current_step": state.current_step,
                "knowledge_used": state.knowledge_used,
                "knowledge_confidence": state.knowledge_confidence,
                "interrupt_flag": state.interrupt_flag,
                "resume_token": state.resume_token,
                "resume_from_step": state.resume_from_step,
                "finished": state.finished,
            },
            "events": [asdict(event) for event in self.workflow_store.list_events(task_id)],
        }

    def drain_events(self, task_id: str) -> list[dict]:
        payloads = self.event_bus.drain_payloads()
        return [payload for payload in payloads if payload["task_id"] == task_id]

    def _publish_event(self, *, session_id: str, task_id: str, event_type: str, payload: dict) -> None:
        event = WorkflowEvent(
            event_id=next_event_id(),
            session_id=session_id,
            task_id=task_id,
            event_type=event_type,
            payload=payload,
            created_at=now_iso(),
        )
        self.workflow_store.append_event(event)
        self.event_bus.publish(event)
