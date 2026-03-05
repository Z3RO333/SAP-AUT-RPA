from __future__ import annotations

import re


PURCHASE_ORDER_PATTERNS = [
    re.compile(r"Documento de compras (\d+) criado", re.IGNORECASE),
    re.compile(r"Documento de compras n[ou]mero (\d+) criado", re.IGNORECASE),
    re.compile(r"Pedido de compra (\d+) criado", re.IGNORECASE),
    re.compile(r"Purchase order (\d+) created", re.IGNORECASE),
]


def parse_purchase_order_number(status_text: str, status_type: str) -> str | None:
    text = status_text or ""
    for pattern in PURCHASE_ORDER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    if status_type == "S":
        generic = re.search(r"(\d{6,})", text)
        if generic:
            return generic.group(1)
    return None
