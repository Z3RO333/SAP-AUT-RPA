from __future__ import annotations

from core.reports.common import execute_alv_transaction_with_profile, grid_to_dataframe, load_report_profile


COLUNAS_DESEJADAS = ["EBELN", "EBELP", "EINDT", "LIFNR", "VENDOR_NAME", "WERKS", "MATNR", "TXZ01", "MENGE", "MEINS", "NETPR", "NETWR"]
NOMES_COLUNAS = {
    "EBELN": "PEDIDO",
    "EBELP": "ITEM",
    "EINDT": "DATA ENTREGA",
    "LIFNR": "FORNECEDOR",
    "VENDOR_NAME": "NOME FORNECEDOR",
    "WERKS": "CENTRO",
    "MATNR": "MATERIAL",
    "TXZ01": "DESCRICAO",
    "MENGE": "QTDE",
    "MEINS": "UM",
    "NETPR": "PRECO LIQ.",
    "NETWR": "VALOR LIQ.",
}


def executar_me2l(session, fornecedor: str, data_ini: str | None, data_fim: str | None, layout: str = "", callback_log=None):
    if callback_log:
        callback_log("Abrindo ME2L.")
    _profile_name, profile = load_report_profile("ME2L")
    grid = execute_alv_transaction_with_profile(
        session,
        "ME2L",
        profile,
        {"fornecedor": fornecedor, "layout": layout, "dateFrom": data_ini or "", "dateTo": data_fim or ""},
    )
    return grid_to_dataframe(grid, COLUNAS_DESEJADAS, NOMES_COLUNAS)
