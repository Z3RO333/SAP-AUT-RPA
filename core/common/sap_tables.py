from __future__ import annotations


def get_displayed_column_ids(grid) -> list[str]:
    column_order = grid.ColumnOrder
    count = int(getattr(column_order, "Count", getattr(column_order, "Length", 0)) or 0)
    values: list[str] = []
    for index in range(count):
        values.append(str(column_order.ElementAt(index)))
    return values


def get_column_title(grid, column_id: str) -> str:
    try:
        title = str(grid.GetDisplayedColumnTitle(column_id) or "").strip()
        if title:
            return title
    except Exception:
        pass
    try:
        titles = grid.GetColumnTitles(column_id)
        count = int(getattr(titles, "Count", getattr(titles, "Length", 0)) or 0)
        if count:
            return str(titles.ElementAt(0) or "").strip()
    except Exception:
        pass
    try:
        tooltip = str(grid.GetColumnTooltip(column_id) or "").strip()
        if tooltip:
            return tooltip
    except Exception:
        pass
    return column_id


def read_grid_cell(grid, row_index: int, column_id: str) -> str:
    try:
        return str(grid.GetCellValue(int(row_index), str(column_id)) or "").strip()
    except Exception:
        return ""


def extract_grid_rows(grid, column_ids: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    total_rows = int(getattr(grid, "RowCount", 0) or 0)
    for row_index in range(total_rows):
        rows.append({column_id: read_grid_cell(grid, row_index, column_id) for column_id in column_ids})
    return rows

