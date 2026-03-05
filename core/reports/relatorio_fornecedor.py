from __future__ import annotations

import pandas as pd


def load_report(path: str) -> pd.DataFrame:
    return pd.read_excel(path)


def apply_filters(df: pd.DataFrame, fornecedor: str = "", centro: str = "", period_start: str = "", period_end: str = "") -> pd.DataFrame:
    filtered = df.copy()
    if fornecedor:
        fornecedor_lower = fornecedor.lower()
        filtered = filtered[filtered.astype(str).apply(lambda row: fornecedor_lower in " ".join(row).lower(), axis=1)]
    if centro:
        centro_lower = centro.lower()
        filtered = filtered[filtered.astype(str).apply(lambda row: centro_lower in " ".join(row).lower(), axis=1)]
    date_col = next((column for column in filtered.columns if "data" in str(column).lower()), None)
    if date_col:
        parsed = pd.to_datetime(filtered[date_col], errors="coerce")
        if period_start:
            filtered = filtered[parsed >= pd.Timestamp(period_start)]
        if period_end:
            filtered = filtered[parsed <= pd.Timestamp(period_end)]
    return filtered
