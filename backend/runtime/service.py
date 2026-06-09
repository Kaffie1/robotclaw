from __future__ import annotations

from dataclasses import asdict

from backend.gateway.models import ChatRequest, ChatResponse
from backend.langgraph import run_chat_graph
from backend.knowledge import KnowledgeService
from backend.llm import LLMRegistry
from backend.memory import MemoryManager
from backend.playbook import PlaybookEngine
from backend.runtime.models import DiagnosisSummary, EvidenceItem, RouteDecision, RuntimeEnvelope, RuntimeState
from backend.runtime.workflow import WorkflowEventBus, WorkflowStore, build_resume_token
from backend.runtime.workflow.models import WorkflowEvent
from backend.shared import get_logger, infer_title, next_event_id, next_request_id, next_resume_token, now_iso
from backend.tools import ToolExecutor


logger = get_logger("runtime.service")


class RuntimeService:
    def __init__(
        self,
        *,
        playbook_engine: PlaybookEngine | None = None,
        knowledge_service: KnowledgeService | None = None,
        llm_registry: LLMRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        self.playbook_engine = playbook_engine or PlaybookEngine()
        self.knowledge_service = knowledge_service or KnowledgeService()
        self.llm_registry = llm_registry or LLMRegistry()
        self.tool_executor = tool_executor or ToolExecutor()
        self.memory_manager = memory_manager or MemoryManager()
        self.workflow_store = WorkflowStore()
        self.event_bus = WorkflowEventBus()

    def build_request(self, session_id: str, user_id: str, content: str) -> ChatRequest:
        request = ChatRequest(
            session_id=session_id,
            user_id=user_id,
            content=content,
            request_id=next_request_id(),
        )
        logger.info("Built request request_id=%s session_id=%s user_id=%s", request.request_id, session_id, user_id)
        return request

    def initial_state(self, envelope: RuntimeEnvelope, request: ChatRequest) -> RuntimeState:
        if request.resume:
            stored_state = self.workflow_store.get_runtime_state(envelope.task.task_id)
            if stored_state is not None:
                stored_state.interrupt_flag = False
                stored_state.finished = False
                stored_state.user_query = request.content
                return stored_state
        return RuntimeState(
            session_id=envelope.session.session_id,
            task_id=envelope.task.task_id,
            user_query=request.content,
            route="chat",
            current_step="gateway_received",
        )

    def run(self, envelope: RuntimeEnvelope, request: ChatRequest, connected: bool) -> tuple[RuntimeState, DiagnosisSummary, ChatResponse]:
        logger.info(
            "Runtime run started request_id=%s session_id=%s task_id=%s connected=%s resume=%s",
            request.request_id,
            envelope.session.session_id,
            envelope.task.task_id,
            connected,
            request.resume,
        )
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
            llm_registry=self.llm_registry,
            tool_executor=self.tool_executor,
            memory_manager=self.memory_manager,
            workflow_store=self.workflow_store,
            event_bus=self.event_bus,
        )
        if state.current_step in {"waiting_confirm", "waiting_input"} and not state.resume_token:
            resume_token = build_resume_token(
                token=next_resume_token(),
                session_id=envelope.session.session_id,
                task_id=envelope.task.task_id,
                resume_from_step=state.resume_from_step or "tool_planning",
                payload={"current_step": state.current_step},
            )
            state.resume_token = resume_token.token
            state.resume_from_step = resume_token.resume_from_step
            self.workflow_store.save_resume_token(resume_token)
            logger.info(
                "Generated resume token task_id=%s resume_token=%s resume_from_step=%s",
                envelope.task.task_id,
                state.resume_token,
                state.resume_from_step,
            )
        if state.finished and state.resume_token:
            self.workflow_store.delete_resume_token(state.resume_token)
            state.resume_token = ""
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
            status=self._response_status(state),
            summary=diagnosis.final_answer,
            continuation_token=state.resume_token,
            playbook_id=state.matched_playbook_id,
            data={
                "trace": [asdict(item) for item in state.trace],
                "evidence": [item.content for item in diagnosis.evidence],
                "solutions": [asdict(item) for item in diagnosis.solutions],
                "planned_tools": [dict(item) for item in state.planned_tools],
                "tool_results": self.tool_executor.to_payload(state.tool_results),
                "title_hint": infer_title(request.content, envelope.task.title),
                "events": self.drain_events(envelope.task.task_id),
                "confirmation": self._confirmation_payload(envelope.task.task_id),
                "llm_debug": self._llm_debug_payload(envelope.task.task_id),
            },
        )
        logger.info(
            "Runtime run finished task_id=%s status=%s current_step=%s matched_playbook_id=%s",
            envelope.task.task_id,
            response.status,
            state.current_step,
            state.matched_playbook_id,
        )
        return state, diagnosis, response

    def interrupt_task(self, session_id: str, task_id: str) -> str:
        logger.info("Interrupt requested session_id=%s task_id=%s", session_id, task_id)
        runtime_state = self.workflow_store.get_runtime_state(task_id)
        if runtime_state is None:
            runtime_state = RuntimeState(session_id=session_id, task_id=task_id, user_query="")
        runtime_state.interrupt_flag = True
        resume_token = build_resume_token(
            token=next_resume_token(),
            session_id=session_id,
            task_id=task_id,
            resume_from_step=runtime_state.current_step if runtime_state else "",
            payload={"current_step": runtime_state.current_step if runtime_state else ""},
        )
        runtime_state.resume_token = resume_token.token
        runtime_state.resume_from_step = resume_token.resume_from_step
        self.workflow_store.save_runtime_state(runtime_state)
        self.workflow_store.save_resume_token(resume_token)
        self._publish_event(
            session_id=session_id,
            task_id=task_id,
            event_type="runtime.interrupted",
            payload={"resume_token": resume_token.token},
        )
        logger.info("Interrupt prepared task_id=%s resume_token=%s", task_id, resume_token.token)
        return resume_token.token

    def resume_request(self, session_id: str, task_id: str, content: str, token: str, user_id: str) -> ChatRequest:
        logger.info("Resume requested session_id=%s task_id=%s user_id=%s", session_id, task_id, user_id)
        resume_token = self.workflow_store.get_resume_token(token)
        if resume_token is None or resume_token.session_id != session_id or resume_token.task_id != task_id:
            raise ValueError("无效的恢复令牌")
        request = self.build_request(session_id=session_id, user_id=user_id, content=content)
        request.resume = True
        runtime_state = self.workflow_store.get_runtime_state(task_id)
        if runtime_state is not None:
            runtime_state.resume_token = token
            runtime_state.resume_from_step = resume_token.resume_from_step
            runtime_state.finished = False
            self.workflow_store.save_runtime_state(runtime_state)
        self.workflow_store.clear_confirmation(task_id)
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

    def _response_status(self, state: RuntimeState) -> str:
        if state.current_step == "waiting_input":
            return "waiting_input"
        if state.current_step == "waiting_confirm":
            return "waiting_confirm"
        if state.interrupt_flag:
            return "interrupted"
        if state.finished:
            return "completed"
        return "running"

    def _confirmation_payload(self, task_id: str) -> dict | None:
        confirmation = self.workflow_store.get_confirmation(task_id)
        if confirmation is None:
            return None
        return asdict(confirmation)

    def _llm_debug_payload(self, task_id: str) -> dict:
        short_memory = self.memory_manager.get_short_memory(task_id)
        scratchpad = short_memory.scratchpad
        return {
            "classify_llm_attempted": bool(scratchpad.get("classify_llm_attempted", False)),
            "classify_source": str(scratchpad.get("classify_source", "fallback")),
            "plan_llm_attempted": bool(scratchpad.get("plan_llm_attempted", False)),
            "plan_source": str(scratchpad.get("plan_source", "fallback")),
            "summary_llm_attempted": bool(scratchpad.get("summary_llm_attempted", False)),
            "summary_source": str(scratchpad.get("summary_source", "fallback")),
        }

    def llm_status(self) -> dict:
        return self.llm_registry.status_payload()

    def activate_llm_profile(self, profile_id: str) -> dict:
        logger.info("Switching active llm profile to %s", profile_id)
        self.llm_registry.activate(profile_id)
        return self.llm_registry.status_payload()

    def upsert_llm_profile(self, payload: dict, activate: bool = False) -> dict:
        logger.info("Upserting llm profile profile_id=%s activate=%s", payload.get("profile_id", ""), activate)
        self.llm_registry.upsert_profile(payload, activate=activate)
        return self.llm_registry.status_payload()
