from backend.runtime.models import DiagnosisSummary, EvidenceItem, RouteDecision, RuntimeEnvelope, RuntimeState, SolutionItem

__all__ = [
    "DiagnosisSummary",
    "EvidenceItem",
    "RouteDecision",
    "RuntimeEnvelope",
    "RuntimeService",
    "RuntimeState",
    "SolutionItem",
]


def __getattr__(name: str):
    if name == "RuntimeService":
        from backend.runtime.service import RuntimeService

        return RuntimeService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
