from __future__ import annotations

from core.reports.common import execute_alv_transaction_with_profile, grid_to_dataframe, load_report_profile


COLUNAS_DESEJADAS = ["AUFNR", "ERDAT", "PLTXT", "KTEXT", "ZZTXT30", "ZZKTEXT", "USER4", "GKSTP", "GKSTI"]
NOMES_COLUNAS = {
    "AUFNR": "ORDEM",
    "ERDAT": "DATA ENTRADA",
    "PLTXT": "UNIDADE",
    "KTEXT": "TEXTO BREVE",
    "ZZTXT30": "STATUS",
    "ZZKTEXT": "FORNECEDOR",
    "USER4": "TOTAL ESTIMADO",
    "GKSTP": "TOTAL MATERIAL",
    "GKSTI": "TOTAL REAL",
}


def executar_iw38(session, code: str, date_from: str, date_to: str, callback_log=None):
    if callback_log:
        callback_log("Abrindo IW38.")
    _profile_name, profile = load_report_profile("IW38")
    grid = execute_alv_transaction_with_profile(
        session,
        "IW38",
        profile,
        {"workCenter": code, "dateFrom": date_from, "dateTo": date_to},
    )
    return grid_to_dataframe(grid, COLUNAS_DESEJADAS, NOMES_COLUNAS)
