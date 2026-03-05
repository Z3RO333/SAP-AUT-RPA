from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime import appdata_dir, ensure_dir, expand_path


DEFAULT_CONFIG = {
    "sapLogonPath": None,
    "outputRoot": r"%USERPROFILE%\Documents\SAP Robots\Saidas",
    "layoutOverridesDir": r"%APPDATA%\Robos SAP\layouts",
    "defaultSessionSelection": "prompt",
    "diagnosticsEnabled": True,
}


@dataclass(slots=True)
class AppConfig:
    sap_logon_path: Path | None
    output_root: Path
    layout_overrides_dir: Path
    default_session_selection: str
    diagnostics_enabled: bool

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppConfig":
        sap_logon_raw = payload.get("sapLogonPath")
        return cls(
            sap_logon_path=expand_path(sap_logon_raw) if sap_logon_raw else None,
            output_root=expand_path(payload.get("outputRoot", DEFAULT_CONFIG["outputRoot"])),
            layout_overrides_dir=expand_path(
                payload.get("layoutOverridesDir", DEFAULT_CONFIG["layoutOverridesDir"])
            ),
            default_session_selection=str(payload.get("defaultSessionSelection", "prompt")).strip() or "prompt",
            diagnostics_enabled=bool(payload.get("diagnosticsEnabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sapLogonPath": str(self.sap_logon_path) if self.sap_logon_path else None,
            "outputRoot": str(self.output_root),
            "layoutOverridesDir": str(self.layout_overrides_dir),
            "defaultSessionSelection": self.default_session_selection,
            "diagnosticsEnabled": self.diagnostics_enabled,
        }


def config_path() -> Path:
    return appdata_dir() / "config.json"


def load_config() -> AppConfig:
    path = config_path()
    if not path.exists():
        return AppConfig.from_dict(DEFAULT_CONFIG)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("config invalida")
    except Exception:
        payload = {}
    merged = DEFAULT_CONFIG.copy()
    merged.update(payload)
    return AppConfig.from_dict(merged)


def ensure_config_exists() -> Path:
    path = config_path()
    if path.exists():
        return path
    ensure_dir(path.parent)
    path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    return path

