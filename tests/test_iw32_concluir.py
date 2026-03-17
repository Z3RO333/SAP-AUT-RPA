import unittest
from pathlib import Path
from unittest.mock import call, patch

from core.common.logging import ExecutionLogger
from core.common.run_context import RunContext
from core.iw32.concluir import concluir_ordem


class Iw32ConcluirTests(unittest.TestCase):
    def setUp(self):
        logger = ExecutionLogger(Path("logs/test-iw32-concluir.log"))
        self.context = RunContext(logger=logger)
        self.profile = {
            "fields": {
                "matricula": ["matricula_field"],
                "nota": ["nota_combo"],
            },
            "buttons": {
                "exec": ["exec_button"],
                "avex": ["avex_button"],
                "conc": ["conc_button"],
                "save": ["save_button"],
            },
        }
        self.session = object()

    @patch("core.iw32.concluir.read_statusbar", side_effect=[("Conclusao OK", "S"), ("Salvo", "S")])
    @patch("core.iw32.concluir.close_popup_ok", side_effect=[True, False, True, False])
    @patch("core.iw32.concluir.press")
    @patch("core.iw32.concluir.set_combo_value")
    @patch("core.iw32.concluir.set_text")
    @patch("core.iw32.concluir.select_cuk_tab")
    @patch("core.iw32.concluir.open_order_iw32")
    def test_concluir_ordem_uses_combo_for_nota_and_saves(
        self,
        open_order_mock,
        select_tab_mock,
        set_text_mock,
        set_combo_value_mock,
        press_mock,
        close_popup_ok_mock,
        _read_statusbar_mock,
    ):
        result = concluir_ordem(self.session, "500001", "12345", "3", self.profile, self.context)

        open_order_mock.assert_called_once_with(self.session, "500001", self.profile, context=self.context)
        select_tab_mock.assert_called_once_with(self.session, self.profile, context=self.context)
        set_text_mock.assert_called_once_with(self.session, ["matricula_field"], "12345", context=self.context)
        set_combo_value_mock.assert_called_once_with(self.session, ["nota_combo"], "3", context=self.context)
        self.assertEqual(
            [call.args[1] for call in press_mock.call_args_list],
            [["exec_button"], ["avex_button"], ["conc_button"], ["save_button"]],
        )
        self.assertEqual(close_popup_ok_mock.call_count, 4)
        self.assertTrue(result["success"])
        self.assertEqual(result["statusBar"], "Salvo")

    @patch("core.iw32.concluir.read_statusbar", return_value=("Nota obrigatoria", "E"))
    @patch("core.iw32.concluir.close_popup_ok", return_value=False)
    @patch("core.iw32.concluir.press")
    @patch("core.iw32.concluir.set_combo_value")
    @patch("core.iw32.concluir.set_text")
    @patch("core.iw32.concluir.select_cuk_tab")
    @patch("core.iw32.concluir.open_order_iw32")
    def test_concluir_ordem_stops_before_save_when_conc_returns_error(
        self,
        _open_order_mock,
        _select_tab_mock,
        _set_text_mock,
        _set_combo_value_mock,
        press_mock,
        _close_popup_ok_mock,
        _read_statusbar_mock,
    ):
        with self.assertRaisesRegex(RuntimeError, "Nota obrigatoria"):
            concluir_ordem(self.session, "500001", "12345", "3", self.profile, self.context)

        self.assertEqual([call.args[1] for call in press_mock.call_args_list], [["exec_button"], ["avex_button"], ["conc_button"]])


if __name__ == "__main__":
    unittest.main()
