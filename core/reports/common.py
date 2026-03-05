from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.common.layout_maps import field_candidates, load_layout_map, resolve_profile
from core.common.sap_actions import press, set_text, tcode
from core.common.sap_tables import extract_grid_rows
from core.common.sap_wait import wait_not_busy


def _walk_children(element, collector: list) -> None:
    try:
        if hasattr(element, "GetCellValue") and hasattr(element, "RowCount"):
            collector.append(element)
    except Exception:
        pass
    try:
        count = int(getattr(element.Children, "Count", 0) or 0)
    except Exception:
        count = 0
    for index in range(count):
        try:
            child = element.Children(index)
            _walk_children(child, collector)
        except Exception:
            continue


def find_first_grid(session):
    root = session.findById("wnd[0]")
    candidates: list = []
    _walk_children(root, candidates)
    if not candidates:
        raise RuntimeError("Nenhuma grade ALV encontrada na tela.")
    return candidates[0]


def execute_alv_transaction(
    session,
    transaction: str,
    field_values: dict[str, str],
    execute_button: str = "wnd[0]/tbar[1]/btn[8]",
    extra_actions=None,
):
    tcode(session, transaction)
    wait_not_busy(session, timeout=60)
    for field_id, value in field_values.items():
        if value:
            set_text(session, field_id, value)
    if extra_actions:
        extra_actions()
    press(session, execute_button)
    return find_first_grid(session)


def load_report_profile(transaction: str, profile_name: str | None = None) -> tuple[str, dict]:
    layout_map = load_layout_map(transaction)
    return resolve_profile(layout_map, profile_name)


def execute_alv_transaction_with_profile(
    session,
    transaction: str,
    profile: dict,
    values: dict[str, str],
    field_section: str = "fields",
    toolbar_section: str = "toolbar",
    extra_actions=None,
):
    tcode(session, transaction)
    wait_not_busy(session, timeout=60)
    for logical_name, value in values.items():
        if value in (None, ""):
            continue
        candidates = field_candidates(profile, field_section, logical_name)
        if not candidates:
            raise RuntimeError(f"Layout {transaction} sem mapeamento para o campo '{logical_name}'.")
        set_text(session, candidates, value)
    if extra_actions:
        extra_actions()
    execute_candidates = field_candidates(profile, toolbar_section, "execute") or ["wnd[0]/tbar[1]/btn[8]"]
    press(session, execute_candidates)
    return find_first_grid(session)


def grid_to_dataframe(grid, column_ids: list[str], rename_map: dict[str, str]) -> pd.DataFrame:
    rows = extract_grid_rows(grid, column_ids)
    df = pd.DataFrame(rows)
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def export_dataframe_excel(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False)
    return path


def export_dataframe_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_dataframe_pdf(df: pd.DataFrame, path: Path, title: str, subtitle: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=landscape(letter), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    elements = [Paragraph(escape(title), styles["Title"])]
    if subtitle:
        elements.append(Paragraph(escape(subtitle), styles["Normal"]))
    elements.append(Spacer(1, 12))

    data = [list(df.columns)] + df.fillna("").astype(str).values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b2a5b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    return path
