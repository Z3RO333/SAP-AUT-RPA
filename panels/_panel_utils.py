from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def ensure_repo_root() -> Path:
    repo_root = str(REPO_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return REPO_ROOT


def open_path(path: str) -> None:
    os.startfile(path)
