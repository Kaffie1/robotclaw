from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "apply_confirmation_response": "..shared.confirmation",
    "append_chat_history_turn": "..shared.confirmation",
    "build_confirmation_options": "..shared.confirmation",
    "build_confirmation_payload": "..shared.confirmation",
    "clear_chat_history": "..shared.confirmation",
    "clear_pending_confirmation": "..shared.confirmation",
    "clear_playbook_input": "..shared.confirmation",
    "delete_chat_history_file": "..shared.confirmation",
    "expand_context_references": "..shared.confirmation",
    "get_chat_history": "..shared.confirmation",
    "get_chat_state": "..shared.confirmation",
    "get_confirmation_request": "..shared.confirmation",
    "get_context_value": "..shared.confirmation",
    "get_pending_confirmation": "..shared.confirmation",
    "get_playbook_input": "..shared.confirmation",
    "get_playbook_inputs": "..shared.confirmation",
    "get_session": "..shared.confirmation",
    "has_context_value": "..shared.confirmation",
    "list_recent_chat_history": "..shared.confirmation",
    "reset_chat_state": "..shared.confirmation",
    "resolve_confirmation_value": "..shared.confirmation",
    "resolve_pending_confirmation_reply": "..shared.confirmation",
    "store_pending_confirmation": "..shared.confirmation",
    "store_playbook_input": "..shared.confirmation",
    "ApiError": "..core.models",
    "append_fault_trace": "..shared.logging",
    "append_runtime_trace": "..shared.logging",
    "get_fault_logger": "..shared.logging",
    "get_fault_trace_logger": "..shared.logging",
    "get_runtime_logger": "..shared.logging",
    "get_runtime_trace_logger": "..shared.logging",
    "logger": "..shared.logging",
    "setup_fault_logger": "..shared.logging",
    "setup_fault_trace_logger": "..shared.logging",
    "setup_runtime_logger": "..shared.logging",
    "setup_runtime_trace_logger": "..shared.logging",
    "trace_logger": "..shared.logging",
    "truncate_trace_value": "..shared.logging",
    "build_backup_path": "..shared.remote",
    "extract_critical_command_warnings": "..shared.remote",
    "is_dir": "..shared.remote",
    "is_remote_subpath": "..shared.remote",
    "iter_command_output_lines": "..shared.remote",
    "log_command_result": "..shared.remote",
    "render_remote_command": "..shared.remote",
    "short_error": "..shared.remote",
    "extract_json_payload": "..shared.text",
    "normalize_message_content": "..shared.text",
    "strip_think_blocks": "..shared.text",
    "download_file_from_chfs": "..shared.files",
    "extract_package_prefix": "..shared.files",
    "get_asset_version": "..shared.files",
    "is_api_request": "..shared.files",
    "load_json_config": "..shared.validation",
    "migrate_legacy_runtime_files": "..shared.files",
    "now_text": "..shared.runtime",
    "parse_bool": "..shared.validation",
    "prepare_package_bytes": "..shared.files",
    "prepare_package_source": "..shared.files",
    "materialize_package_bytes_from_source": "..shared.files",
    "require_text": "..shared.validation",
    "require_upload": "..shared.validation",
    "resolve_download_source_path": "..shared.files",
    "resolve_module_path": "..shared.files",
    "connection_cache_store": "..shared.runtime",
    "deploy_config_store": "..shared.runtime",
    "history_store": "..shared.runtime",
    "session_store": "..shared.runtime",
    "task_manager": "..shared.runtime",
    "templates": "..shared.runtime",
    "upload_progress_manager": "..shared.runtime",
}


__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
