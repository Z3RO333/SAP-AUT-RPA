from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_report(path: str) -> pd.DataFrame:
    return pd.read_excel(path)


def apply_filters(df: pd.DataFrame, centro: str = "", date_from: str = "", date_to: str = "", statuses: list[str] | None = None) -> pd.DataFrame:
    filtered = df.copy()
    if centro:
        filtered = filtered[filtered.astype(str).apply(lambda row: centro.lower() in " ".join(row).lower(), axis=1)]
    if statuses:
        statuses_set = {item.lower() for item in statuses}
        status_col = next((column for column in filtered.columns if "status" in str(column).lower()), None)
        if status_col:
            filtered = filtered[filtered[status_col].astype(str).str.lower().isin(statuses_set)]
    if date_from or date_to:
        date_col = next((column for column in filtered.columns if "data" in str(column).lower()), None)
        if date_col:
            parsed = pd.to_datetime(filtered[date_col], errors="coerce")
            if date_from:
                filtered = filtered[parsed >= pd.Timestamp(date_from)]
            if date_to:
                filtered = filtered[parsed <= pd.Timestamp(date_to)]
    return filtered

