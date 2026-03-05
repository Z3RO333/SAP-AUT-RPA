from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import load_config
from .runtime import LAYOUTS_DIR


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Arquivo JSON invalido: {path}")
    return payload


def layout_map_path(transaction: str) -> Path:
    config = load_config()
    override_path = config.layout_overrides_dir / f"{transaction.lower()}.json"
    if override_path.exists():
        return override_path
    default_path = LAYOUTS_DIR / f"{transaction.lower()}.json"
    if not default_path.exists():
        raise FileNotFoundError(f"Layout map nao encontrado para {transaction}")
    return default_path


def load_layout_map(transaction: str) -> dict[str, Any]:
    payload = _read_json(layout_map_path(transaction))
    if payload.get("transaction", "").upper() != transaction.upper():
        raise ValueError(f"Layout map {transaction} possui transaction invalida")
    return payload


def resolve_profile(layout_map: dict[str, Any], profile_name: str | None = None) -> tuple[str, dict[str, Any]]:
    profiles = layout_map.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("Layout map sem profiles")
    selected_name = profile_name or layout_map.get("defaultProfile")
    if not selected_name:
        raise ValueError("Layout map sem defaultProfile")
    if selected_name not in profiles:
        raise ValueError(f"Profile de layout nao encontrado: {selected_name}")
    return selected_name, profiles[selected_name]


def field_candidates(profile: dict[str, Any], section: str, field_name: str) -> list[str]:
    section_data = profile.get(section, {})
    if not isinstance(section_data, dict):
        return []
    candidates = section_data.get(field_name, [])
    if isinstance(candidates, str):
        return [candidates]
    return [str(item) for item in candidates]

