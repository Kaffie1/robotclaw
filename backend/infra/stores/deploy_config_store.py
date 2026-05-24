import json
import threading
from pathlib import Path
from typing import Any


def normalize_machine_option(option: Any) -> dict[str, str] | None:
    if isinstance(option, dict):
        value = str(option.get("value") or option.get("id") or option.get("name") or "").strip()
        label = str(option.get("label") or option.get("title") or value).strip()
    else:
        value = str(option or "").strip()
        label = value
    if not value:
        return None
    return {"value": value, "label": label or value}


def normalize_doc_link(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    title = str(entry.get("title") or "").strip()
    url = str(entry.get("url") or "").strip()
    if not title or not url:
        return None
    return {"title": title, "url": url}


def normalize_deploy_profile(profile: Any, defaults: dict[str, Any]) -> dict[str, Any]:
    item = profile if isinstance(profile, dict) else {}
    probe_command_template = str(item.get("probe_command_template") or defaults.get("probe_command_template", "")).strip()
    install_template = str(item.get("install_template") or defaults["install_template"]).strip()
    if not install_template:
        install_template = defaults["install_template"]
    normalized = {
        "probe_command_template": probe_command_template,
        "install_template": install_template,
        "start_command": str(item.get("start_command", defaults["start_command"])).strip(),
        "health_command": str(item.get("health_command", defaults["health_command"])).strip(),
        "rollback_template": str(item.get("rollback_template", defaults["rollback_template"])).strip(),
        "auto_rollback": bool(item.get("auto_rollback", defaults["auto_rollback"])),
    }
    raw_machine_options = item.get("machine_options", defaults.get("machine_options", []))
    machine_options: list[dict[str, str]] = []
    if isinstance(raw_machine_options, list):
        for option in raw_machine_options:
            normalized_option = normalize_machine_option(option)
            if normalized_option:
                machine_options.append(normalized_option)
    if machine_options:
        normalized["machine_options"] = machine_options
    raw_machine_profiles = item.get("machine_profiles", defaults.get("machine_profiles", {}))
    machine_profiles: dict[str, dict[str, Any]] = {}
    if isinstance(raw_machine_profiles, dict):
        for machine_key, machine_profile in raw_machine_profiles.items():
            normalized_key = str(machine_key or "").strip()
            machine_item = machine_profile if isinstance(machine_profile, dict) else {}
            if not normalized_key:
                continue
            machine_profiles[normalized_key] = {
                "probe_command_template": str(machine_item.get("probe_command_template", normalized["probe_command_template"])).strip(),
                "install_template": str(machine_item.get("install_template", normalized["install_template"])).strip()
                or normalized["install_template"],
                "start_command": str(machine_item.get("start_command", normalized["start_command"])).strip(),
                "health_command": str(machine_item.get("health_command", normalized["health_command"])).strip(),
                "rollback_template": str(machine_item.get("rollback_template", normalized["rollback_template"])).strip(),
                "auto_rollback": bool(machine_item.get("auto_rollback", normalized["auto_rollback"])),
            }
    if machine_profiles:
        normalized["machine_profiles"] = machine_profiles
    return normalized


class DeployConfigStore:
    def __init__(self, config_path: Path, defaults: dict[str, dict[str, Any]]) -> None:
        self.config_path = config_path
        self.defaults = defaults
        self.lock = threading.Lock()

    def ensure_exists(self) -> None:
        with self.lock:
            if not self.config_path.exists():
                self._write(self.defaults)

    def get_profile(self, deploy_mode: str = "package", machine_type: str = "", *, auto_select_default: bool = True) -> dict[str, Any]:
        from ...core.models import ApiError

        mode = str(deploy_mode or "package").strip().lower()
        config = self.load()
        if mode not in config:
            raise ApiError(f"当前不支持的部署模式: {mode}")
        profile = config.get(mode)
        if profile is None:
            raise ApiError(f"部署配置中缺少 {mode} 配置")
        machine_options = profile.get("machine_options", [])
        option_values = [str(option.get("value") or "").strip() for option in machine_options if isinstance(option, dict)]
        resolved_machine_type = str(machine_type or "").strip()
        if auto_select_default and not resolved_machine_type and option_values:
            resolved_machine_type = option_values[0]
        resolved_profile = dict(profile)
        machine_profiles = profile.get("machine_profiles", {})
        if resolved_machine_type and isinstance(machine_profiles, dict):
            resolved_profile.update(machine_profiles.get(resolved_machine_type, {}))
        resolved_profile["machine_type"] = resolved_machine_type
        resolved_profile["deploy_mode"] = mode
        return resolved_profile

    def get_machine_options(self, deploy_mode: str = "package") -> list[dict[str, str]]:
        mode = str(deploy_mode or "package").strip().lower()
        profile = self.load().get(mode, {})
        options = profile.get("machine_options", [])
        return [option for option in options if isinstance(option, dict) and str(option.get("value") or "").strip()]

    def load(self) -> dict[str, dict[str, Any]]:
        from ...core.models import ApiError

        with self.lock:
            if not self.config_path.exists():
                self._write(self.defaults)
                return {key: dict(value) for key, value in self.defaults.items()}
            try:
                raw = self.config_path.read_text(encoding="utf-8")
                parsed = json.loads(raw or "{}")
            except json.JSONDecodeError as exc:
                raise ApiError(f"{self.config_path.name} 格式错误: {exc}") from exc
            except OSError as exc:
                raise ApiError(f"读取 {self.config_path.name} 失败: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ApiError(f"{self.config_path.name} 顶层必须是对象")
            return {key: normalize_deploy_profile(parsed.get(key), defaults) for key, defaults in self.defaults.items()}

    def _write(self, payload: dict[str, dict[str, Any]]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.config_path.with_suffix(f"{self.config_path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.config_path)
