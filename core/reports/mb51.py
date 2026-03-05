from __future__ import annotations

from core.common.layout_maps import field_candidates
from core.common.sap_actions import press
from core.reports.common import execute_alv_transaction_with_profile, grid_to_dataframe, load_report_profile


COLUNAS_DESEJADAS = ["MBLNR", "EBELN", "MATNR", "MAKTX", "WERKS", "LIFNR", "BWART", "BUDAT", "BLDAT", "MENGE", "MEINS", "DMBTR"]
NOMES_COLUNAS = {
    "MBLNR": "DOC. MATERIAL",
    "EBELN": "PEDIDO",
    "MATNR": "MATERIAL",
    "MAKTX": "DESCRICAO",
    "WERKS": "CENTRO",
    "LIFNR": "FORNECEDOR",
    "BWART": "TP. MOV.",
    "BUDAT": "DT. LANCAMENTO",
    "BLDAT": "DT. DOCUMENTO",
    "MENGE": "QTDE",
    "MEINS": "UM",
    "DMBTR": "VALOR",
}


def executar_mb51(
    session,
    centro: str = "",
    fornecedor: str = "",
    tipo_movimento: str = "",
    data_ini: str | None = None,
    data_fim: str | None = None,
    callback_log=None,
):
    if callback_log:
        callback_log("Abrindo MB51.")
    _profile_name, profile = load_report_profile("MB51")

    def _extra_actions():
        try:
            radio = field_candidates(profile, "buttons", "listDisplay")
            if radio:
                press(session, radio)
        except Exception:
            return

    grid = execute_alv_transaction_with_profile(
        session,
        "MB51",
        profile,
        {
            "centro": centro,
            "fornecedor": fornecedor,
            "tipoMovimento": tipo_movimento,
            "dateFrom": data_ini or "",
            "dateTo": data_fim or "",
        },
        extra_actions=_extra_actions,
    )
    return grid_to_dataframe(grid, COLUNAS_DESEJADAS, NOMES_COLUNAS)
