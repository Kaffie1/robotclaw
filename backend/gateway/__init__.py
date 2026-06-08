from backend.gateway.models import ChatRequest, ChatResponse

__all__ = ["ChatRequest", "ChatResponse", "GatewayApplication", "run_dev_server"]


def __getattr__(name: str):
    if name == "GatewayApplication":
        from backend.gateway.app import GatewayApplication

        return GatewayApplication
    if name == "run_dev_server":
        from backend.gateway.http import run_dev_server

        return run_dev_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
