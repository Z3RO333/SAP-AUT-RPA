from __future__ import annotations

import json
from pathlib import Path

from .models import PurchaseOrderPayload


def payload_to_json(payload: PurchaseOrderPayload) -> dict:
    return payload.to_dict()


def write_payload(payload: PurchaseOrderPayload, path: Path) -> Path:
    path.write_text(json.dumps(payload_to_json(payload), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
