from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


APP_NAME = "Robos SAP"
DEFAULT_OUTPUT_ROOT = r"%USERPROFILE%\Documents\SAP Robots\Saidas"
DEFAULT_LAYOUT_OVERRIDE_DIR = r"%APPDATA%\Robos SAP\layouts"
REPO_ROOT = Path(__file__).resolve().parents[2]
LAYOUTS_DIR = REPO_ROOT / "sap" / "layouts"


def expand_path(raw_path: str | os.PathLike[str]) -> Path:
    return Path(os.path.expandvars(str(raw_path))).expanduser()


def appdata_dir() -> Path:
    return expand_path(r"%APPDATA%\Robos SAP")


def local_app_dir() -> Path:
    return expand_path(r"%LOCALAPPDATA%\Programs\Robos SAP")


def default_output_root() -> Path:
    return expand_path(DEFAULT_OUTPUT_ROOT)


def default_layout_override_dir() -> Path:
    return expand_path(DEFAULT_LAYOUT_OVERRIDE_DIR)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_name(value: str, fallback: str = "SEM_NOME") -> str:
    text = (value or "").strip() or fallback
    for ch in '<>:"/\\|?*':
        text = text.replace(ch, "_")
    return text


def run_output_dir(robot_name: str, business_key: str | None = None, run_id: str | None = None) -> Path:
    robot_dir = safe_name(robot_name)
    key_dir = safe_name(business_key or "GERAL")
    try:
        from .config import load_config

        output_root = load_config().output_root
    except Exception:
        output_root = default_output_root()
    return output_root / robot_dir / key_dir / (run_id or timestamp_id())


def frozen() -> bool:
    return getattr(sys, "frozen", False)
