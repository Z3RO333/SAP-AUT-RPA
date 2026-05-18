import unittest
from pathlib import Path
from unittest.mock import ANY, call, patch

from core.common.logging import ExecutionLogger
from core.common.run_context import RunContext
from core.zme62.avaliacao import (
    _confirm_send_popup,
    _fill_responses,
    _press_email_button,
    _save_and_confirm,
    _send_email_from_grid,
    validate_responses_by_question,
)


QUESTION_OPTIONS = [
    ["SIM, MELHORES CONDICOES", "SIM, MESMAS CONDICOES", "NAO"],
    ["NAO", "PARCIALMENTE", "SIM"],
    ["NAO", "PARCIALMENTE", "SIM"],
    ["NAO", "PARCIALMENTE", "SIM"],
]


class _FakeGrid:
    def __init__(self):
        self.firstVisibleRow = 0
        self.visibleRowCount = 33
        self.values = {}
        self.calls = []

    def setColumnWidth(self, column_id, width):
        self.calls.append(("setColumnWidth", column_id, width))

    def modifyCell(self, row, column_id, value):
        self.calls.append(("modifyCell", row, column_id, value))
        self.values[(row, column_id)] = value

    def setCurrentCell(self, row, column_id):
        self.calls.append(("setCurrentCell", row, column_id))

    def pressEnter(self):
        self.calls.append(("pressEnter",))

    def GetCellValue(self, row, column_id):
        return self.values.get((row, column_id), "")


class Zme62AvaliacaoTests(unittest.TestCase):
    def setUp(self):
        logger = ExecutionLogger(Path("logs/test-zme62-avaliacao.log"))
        self.context = RunContext(logger=logger)
        self.session = object()

    @patch("core.zme62.avaliacao.close_popup_ok")
    @patch("core.zme62.avaliacao.popup_exists", return_value=False)
    @patch("core.zme62.avaliacao.wait_not_busy")
    @patch("core.zme62.avaliacao.wait")
    def test_fill_responses_confirms_before_scrolling_to_last_row(
        self,
        _wait_mock,
        _wait_not_busy_mock,
        _popup_exists_mock,
        _close_popup_ok_mock,
    ):
        grid = _FakeGrid()

        _fill_responses(
            self.session,
            grid,
            editable_rows=[10, 16, 22, 28],
            respostas=["SIM, MELHORES CONDICOES", "SIM", "SIM", "SIM"],
            response_col="VALOR_OBTIDO",
            context=self.context,
            question_options=QUESTION_OPTIONS,
        )

        self.assertEqual(
            grid.calls,
            [
                ("setColumnWidth", "VALOR_OBTIDO", 20),
                ("modifyCell", 10, "VALOR_OBTIDO", "SIM, MELHORES CONDICOES"),
                ("modifyCell", 16, "VALOR_OBTIDO", "SIM"),
                ("modifyCell", 22, "VALOR_OBTIDO", "SIM"),
                ("setCurrentCell", 22, "VALOR_OBTIDO"),
                ("pressEnter",),
                ("pressEnter",),
                ("modifyCell", 28, "VALOR_OBTIDO", "SIM"),
                ("setCurrentCell", 28, "VALOR_OBTIDO"),
                ("pressEnter",),
            ],
        )
        self.assertEqual(grid.firstVisibleRow, 6)

    @patch("core.zme62.avaliacao.close_popup_ok")
    @patch("core.zme62.avaliacao.popup_exists", return_value=False)
    @patch("core.zme62.avaliacao.wait_not_busy")
    @patch("core.zme62.avaliacao.wait")
    def test_fill_responses_translates_legacy_panel_values_by_question(
        self,
        _wait_mock,
        _wait_not_busy_mock,
        _popup_exists_mock,
        _close_popup_ok_mock,
    ):
        grid = _FakeGrid()

        _fill_responses(
            self.session,
            grid,
            editable_rows=[10, 16, 22, 28],
            respostas=["SIM", "NAO", "SIM", "TALVEZ"],
            response_col="VALOR_OBTIDO",
            context=self.context,
            question_options=QUESTION_OPTIONS,
        )

        self.assertEqual(
            grid.calls,
            [
                ("setColumnWidth", "VALOR_OBTIDO", 20),
                ("modifyCell", 10, "VALOR_OBTIDO", "SIM, MESMAS CONDICOES"),
                ("modifyCell", 16, "VALOR_OBTIDO", "NAO"),
                ("modifyCell", 22, "VALOR_OBTIDO", "SIM"),
                ("setCurrentCell", 22, "VALOR_OBTIDO"),
                ("pressEnter",),
                ("pressEnter",),
                ("modifyCell", 28, "VALOR_OBTIDO", "PARCIALMENTE"),
                ("setCurrentCell", 28, "VALOR_OBTIDO"),
                ("pressEnter",),
            ],
        )
        self.assertEqual(grid.GetCellValue(16, "VALOR_OBTIDO"), "NAO")
        self.assertEqual(grid.GetCellValue(28, "VALOR_OBTIDO"), "PARCIALMENTE")

    @patch("core.zme62.avaliacao.close_popup_ok")
    @patch("core.zme62.avaliacao.popup_exists", return_value=False)
    @patch("core.zme62.avaliacao.wait_not_busy")
    @patch("core.zme62.avaliacao.wait")
    def test_fill_responses_maps_all_nao_directly(
        self,
        _wait_mock,
        _wait_not_busy_mock,
        _popup_exists_mock,
        _close_popup_ok_mock,
    ):
        grid = _FakeGrid()

        _fill_responses(
            self.session,
            grid,
            editable_rows=[10, 16, 22, 28],
            respostas=["SIM, MELHORES CONDICOES", "NAO", "SIM", "NAO"],
            response_col="VALOR_OBTIDO",
            context=self.context,
            question_options=QUESTION_OPTIONS,
        )

        self.assertIn(("modifyCell", 16, "VALOR_OBTIDO", "NAO"), grid.calls)
        self.assertIn(("modifyCell", 28, "VALOR_OBTIDO", "NAO"), grid.calls)
        self.assertEqual(grid.GetCellValue(16, "VALOR_OBTIDO"), "NAO")
        self.assertEqual(grid.GetCellValue(28, "VALOR_OBTIDO"), "NAO")

    @patch("core.zme62.avaliacao.close_popup_ok")
    @patch("core.zme62.avaliacao.popup_exists", return_value=False)
    @patch("core.zme62.avaliacao.wait_not_busy")
    @patch("core.zme62.avaliacao.wait")
    def test_fill_responses_raises_when_grid_value_does_not_match(
        self,
        _wait_mock,
        _wait_not_busy_mock,
        _popup_exists_mock,
        _close_popup_ok_mock,
    ):
        class _MismatchGrid(_FakeGrid):
            def GetCellValue(self, row, column_id):
                if row == 16:
                    return ""
                return super().GetCellValue(row, column_id)

        grid = _MismatchGrid()

        with self.assertRaisesRegex(RuntimeError, "linha 16"):
            _fill_responses(
                self.session,
                grid,
                editable_rows=[10, 16, 22, 28],
                respostas=["SIM, MELHORES CONDICOES", "SIM", "SIM", "SIM"],
                response_col="VALOR_OBTIDO",
                context=self.context,
                question_options=QUESTION_OPTIONS,
            )

    def test_validate_responses_by_question_accepts_legacy_aliases_and_blocks_wrong_question(self):
        self.assertEqual(
            validate_responses_by_question(
                ["SIM", "NAO", "TALVEZ", "SIM"],
                QUESTION_OPTIONS,
            ),
            [],
        )
        self.assertEqual(
            validate_responses_by_question(
                ["SIM, MELHORES CONDICOES", "NAO", "SIM", "SIM, MELHORES CONDICOES"],
                QUESTION_OPTIONS,
            ),
            ["Pergunta 4: 'SIM, MELHORES CONDICOES'"],
        )

    @patch("core.zme62.avaliacao._wait_for_status_message")
    @patch("core.zme62.avaliacao.close_popup_ok")
    @patch("core.zme62.avaliacao.press")
    def test_save_and_confirm_retries_when_status_bar_is_blank(
        self,
        press_mock,
        _close_popup_ok_mock,
        wait_status_mock,
    ):
        wait_status_mock.side_effect = [("", ""), ("Avaliacao 123 salva com sucesso", "S")]

        status_text, status_type = _save_and_confirm(
            self.session,
            {"buttons": {"salvar": ["wnd[0]/tbar[0]/btn[11]"]}},
            "33",
            self.context,
        )

        self.assertEqual((status_text, status_type), ("Avaliacao 123 salva com sucesso", "S"))
        self.assertEqual(press_mock.call_count, 2)

    @patch("core.zme62.avaliacao._wait_for_status_message", return_value=("Emails enviados", "S"))
    @patch("core.zme62.avaliacao._confirm_send_popup")
    @patch("core.zme62.avaliacao._wait_for_status_without_touching_popups")
    @patch("core.zme62.avaliacao._press_email_button")
    @patch("core.zme62.avaliacao.wait")
    def test_send_email_from_grid_runs_vbs_sequence(
        self,
        _wait_mock,
        press_email_mock,
        wait_without_popup_mock,
        confirm_popup_mock,
        wait_status_mock,
    ):
        grid = _FakeGrid()
        profile = {
            "buttons": {
                "enviarEmail": ["wnd[0]/tbar[1]/btn[7]"],
                "confirmarEnvioInicial": ["wnd[1]/usr/btnBUTTON_1"],
                "confirmarEnvioFinal": ["wnd[1]/tbar[0]/btn[8]"],
            },
            "grid": {"responseColumn": "VALOR_OBTIDO"},
        }
        wait_without_popup_mock.side_effect = [("", ""), ("", "")]

        status_text, status_type = _send_email_from_grid(self.session, grid, profile, "33", self.context)

        self.assertEqual((status_text, status_type), ("Emails enviados", "S"))
        self.assertEqual(press_email_mock.call_count, 2)
        self.assertEqual(
            confirm_popup_mock.call_args_list,
            [
                call(self.session, profile, self.context, timeout=8.0),
                call(self.session, profile, self.context, timeout=8.0),
            ],
        )
        self.assertIn(("setCurrentCell", 10, "VALOR_OBTIDO"), grid.calls)

    @patch("core.zme62.avaliacao._wait_for_status_message", return_value=("Email enviado com sucesso", "S"))
    @patch("core.zme62.avaliacao._confirm_send_popup")
    @patch("core.zme62.avaliacao._select_first_existing_evaluation")
    @patch("core.zme62.avaliacao._wait_for_status_without_touching_popups", return_value=("Já existe avaliação criada pelo usuário 21664 para o ano 2025.", "E"))
    @patch("core.zme62.avaliacao._press_email_button")
    def test_send_email_from_grid_uses_existing_evaluation_branch_when_status_indicates_existing(
        self,
        press_email_mock,
        _wait_without_popup_mock,
        select_existing_mock,
        confirm_popup_mock,
        _wait_status_mock,
    ):
        profile = {
            "buttons": {
                "enviarEmail": ["wnd[0]/tbar[1]/btn[7]"],
                "confirmarEnvioInicial": ["wnd[1]/usr/btnBUTTON_1"],
                "confirmarEnvioFinal": ["wnd[1]/tbar[0]/btn[8]"],
            },
            "grid": {"responseColumn": "VALOR_OBTIDO"},
        }

        status_text, status_type = _send_email_from_grid(self.session, None, profile, "17162", self.context)

        self.assertEqual((status_text, status_type), ("Email enviado com sucesso", "S"))
        self.assertEqual(press_email_mock.call_count, 2)
        select_existing_mock.assert_called_once_with(self.session, profile, "17162", self.context)
        confirm_popup_mock.assert_called_once_with(self.session, profile, self.context, timeout=4.0)

    @patch("core.zme62.avaliacao._email_recipients_grid_exists", return_value=True)
    @patch("core.zme62.avaliacao._press_candidates", return_value="wnd[1]/tbar[0]/btn[8]")
    @patch("core.zme62.avaliacao._select_all_email_recipients", return_value=True)
    def test_confirm_send_popup_uses_final_button_when_recipient_grid_is_open(
        self,
        select_all_mock,
        press_candidates_mock,
        _grid_exists_mock,
    ):
        profile = {
            "buttons": {
                "confirmarEnvioInicial": ["wnd[1]/usr/btnBUTTON_1"],
                "confirmarEnvioFinal": ["wnd[1]/tbar[0]/btn[8]"],
            }
        }

        resolved = _confirm_send_popup(self.session, profile, self.context, timeout=8.0)

        self.assertEqual(resolved, "wnd[1]/tbar[0]/btn[8]")
        select_all_mock.assert_called_once_with(self.session, profile, self.context)
        press_candidates_mock.assert_called_once_with(
            self.session,
            ["wnd[1]/tbar[0]/btn[8]"],
            context=self.context,
            timeout=8.0,
        )

    @patch("core.zme62.avaliacao._wait_for_email_recipient_grid", return_value=True)
    @patch("core.zme62.avaliacao._email_recipients_grid_exists", return_value=False)
    @patch("core.zme62.avaliacao._press_candidates")
    @patch("core.zme62.avaliacao._select_all_email_recipients", return_value=True)
    @patch("core.zme62.avaliacao.wait")
    def test_confirm_send_popup_advances_initial_popup_then_sends_from_recipient_grid(
        self,
        _wait_mock,
        select_all_mock,
        press_candidates_mock,
        _grid_exists_mock,
        _wait_grid_mock,
    ):
        profile = {
            "buttons": {
                "confirmarEnvioInicial": ["wnd[1]/usr/btnBUTTON_1"],
                "confirmarEnvioFinal": ["wnd[1]/tbar[0]/btn[8]"],
            }
        }
        press_candidates_mock.side_effect = ["wnd[1]/usr/btnBUTTON_1", "wnd[1]/tbar[0]/btn[8]"]

        resolved = _confirm_send_popup(self.session, profile, self.context, timeout=8.0)

        self.assertEqual(resolved, "wnd[1]/tbar[0]/btn[8]")
        select_all_mock.assert_called_once_with(self.session, profile, self.context)
        self.assertEqual(
            press_candidates_mock.call_args_list,
            [
                call(self.session, ["wnd[1]/usr/btnBUTTON_1"], context=self.context, timeout=8.0),
                call(self.session, ["wnd[1]/tbar[0]/btn[8]"], context=self.context, timeout=ANY),
            ],
        )

    @patch("core.zme62.avaliacao._wait_for_status_message", return_value=("", ""))
    @patch("core.zme62.avaliacao._confirm_send_popup")
    @patch("core.zme62.avaliacao._wait_for_status_without_touching_popups")
    @patch("core.zme62.avaliacao._press_email_button")
    @patch("core.zme62.avaliacao.wait")
    def test_send_email_from_grid_requires_sap_status_confirmation(
        self,
        _wait_mock,
        _press_email_mock,
        wait_without_popup_mock,
        _confirm_popup_mock,
        _wait_status_mock,
    ):
        profile = {
            "buttons": {
                "enviarEmail": ["wnd[0]/tbar[1]/btn[7]"],
                "confirmarEnvioInicial": ["wnd[1]/usr/btnBUTTON_1"],
                "confirmarEnvioFinal": ["wnd[1]/tbar[0]/btn[8]"],
            },
            "grid": {"responseColumn": "VALOR_OBTIDO"},
        }
        wait_without_popup_mock.side_effect = [("", ""), ("", "")]

        with self.assertRaisesRegex(RuntimeError, "SAP nao confirmou o envio"):
            _send_email_from_grid(self.session, None, profile, "33", self.context)

    @patch("core.zme62.avaliacao.send_vkey")
    @patch("core.zme62.avaliacao._find_toolbar_button_by_hints", side_effect=RuntimeError("toolbar sem email"))
    @patch("core.zme62.avaliacao._press_candidates", side_effect=RuntimeError("btn[7] ausente"))
    def test_press_email_button_falls_back_to_f7_when_selector_and_toolbar_fail(
        self,
        _press_candidates_mock,
        _find_toolbar_mock,
        send_vkey_mock,
    ):
        profile = {"buttons": {"enviarEmail": ["wnd[0]/tbar[1]/btn[7]"]}}

        resolved = _press_email_button(self.session, profile, self.context)

        self.assertEqual(resolved, "vkey:7")
        send_vkey_mock.assert_called_once_with(self.session, 7)


if __name__ == "__main__":
    unittest.main()
