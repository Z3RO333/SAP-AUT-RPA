import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from core.common.logging import ExecutionLogger
from core.common.run_context import RunContext
from core.iw32.categorias import preencher_categoria_ordem


class Iw32CategoriasTests(unittest.TestCase):
    def setUp(self):
        logger = ExecutionLogger(Path("logs/test-iw32-categorias.log"))
        self.context = RunContext(logger=logger)
        self.session = object()
        self.iw32_profile = {
            "tabs": {"cukTab": ["cuk_tab"]},
            "fields": {"serviceNumber": ["service_field"]},
            "buttons": {"save": ["save_button"]},
        }
        self.categorias_profile = {
            "categories": {
                "SERVICO DE MANUTENCAO": {
                    "tabSequence": [["outer_cost_tab_1100"], ["inner_cost_tab_1107"]],
                    "fieldCandidates": ["valor_field"],
                    "confirmFieldCandidates": ["confirm_field"],
                    "serviceNumber": "3000465",
                },
                "SERVICO DE MANUTENCAO-CONTRATO": {
                    "tabSequence": [["outer_cost_tab_1100"], ["inner_cost_tab_1107"]],
                    "fieldCandidates": ["valor_field_preventiva"],
                    "confirmFieldCandidates": ["confirm_field_preventiva"],
                    "serviceNumber": "3000465",
                }
            }
        }

    @patch("core.iw32.categorias.read_statusbar", return_value=("Salvo", "S"))
    @patch("core.iw32.categorias.close_popup_ok", return_value=False)
    @patch("core.iw32.categorias.press")
    @patch("core.iw32.categorias.select")
    @patch("core.iw32.categorias.first_existing")
    @patch("core.iw32.categorias.send_vkey")
    @patch("core.iw32.categorias.set_text")
    @patch("core.iw32.categorias.select_cuk_tab")
    @patch("core.iw32.categorias.open_order_iw32")
    def test_preencher_categoria_preenche_servico_antes_do_valor(
        self,
        open_order_mock,
        select_cuk_tab_mock,
        set_text_mock,
        send_vkey_mock,
        first_existing_mock,
        select_mock,
        press_mock,
        _close_popup_ok_mock,
        _read_statusbar_mock,
    ):
        service_field = Mock()
        service_field.Text = ""
        confirm_field = Mock()
        first_existing_mock.side_effect = [
            (service_field, "service_field"),
            (confirm_field, "confirm_field"),
        ]

        result = preencher_categoria_ordem(
            self.session,
            ordem="5223841",
            categoria="SERVICO DE MANUTENCAO",
            valor="1850,00",
            numero_servico="3000465",
            iw32_profile=self.iw32_profile,
            categorias_profile=self.categorias_profile,
            context=self.context,
        )

        open_order_mock.assert_called_once_with(self.session, "5223841", self.iw32_profile, context=self.context)
        select_cuk_tab_mock.assert_called_once_with(self.session, self.iw32_profile, context=self.context)
        self.assertEqual(
            set_text_mock.call_args_list,
            [
                call(self.session, ["service_field"], "3000465", context=self.context),
                call(self.session, ["valor_field"], "1850,00", context=self.context),
            ],
        )
        self.assertEqual(
            select_mock.call_args_list,
            [
                call(self.session, ["outer_cost_tab_1100"], context=self.context),
                call(self.session, ["inner_cost_tab_1107"], context=self.context),
            ],
        )
        send_vkey_mock.assert_called_once_with(self.session, 0)
        confirm_field.SetFocus.assert_called_once_with()
        press_mock.assert_called_once_with(self.session, ["save_button"], context=self.context)
        self.assertTrue(result["success"])
        self.assertEqual(result["statusBar"], "Salvo")

    @patch("core.iw32.categorias.read_statusbar", return_value=("Salvo", "S"))
    @patch("core.iw32.categorias.close_popup_ok", return_value=False)
    @patch("core.iw32.categorias.press")
    @patch("core.iw32.categorias.select")
    @patch("core.iw32.categorias.first_existing")
    @patch("core.iw32.categorias.send_vkey")
    @patch("core.iw32.categorias.set_text")
    @patch("core.iw32.categorias.select_cuk_tab")
    @patch("core.iw32.categorias.open_order_iw32")
    def test_preencher_categoria_segue_quando_numero_servico_opcional_nao_esta_disponivel(
        self,
        _open_order_mock,
        select_cuk_tab_mock,
        set_text_mock,
        send_vkey_mock,
        first_existing_mock,
        select_mock,
        press_mock,
        _close_popup_ok_mock,
        _read_statusbar_mock,
    ):
        service_field = Mock()
        service_field.Text = ""
        confirm_field = Mock()
        first_existing_mock.side_effect = [
            (service_field, "service_field"),
            (confirm_field, "confirm_field"),
        ]
        set_text_mock.side_effect = [
            RuntimeError("Nenhum elemento encontrado entre os caminhos esperados"),
            None,
        ]

        result = preencher_categoria_ordem(
            self.session,
            ordem="5223841",
            categoria="SERVICO DE MANUTENCAO",
            valor="1850,00",
            numero_servico="3000465",
            iw32_profile=self.iw32_profile,
            categorias_profile=self.categorias_profile,
            context=self.context,
        )

        select_cuk_tab_mock.assert_called_once_with(self.session, self.iw32_profile, context=self.context)
        self.assertEqual(
            set_text_mock.call_args_list,
            [
                call(self.session, ["service_field"], "3000465", context=self.context),
                call(self.session, ["valor_field"], "1850,00", context=self.context),
            ],
        )
        self.assertEqual(
            select_mock.call_args_list,
            [
                call(self.session, ["outer_cost_tab_1100"], context=self.context),
                call(self.session, ["inner_cost_tab_1107"], context=self.context),
            ],
        )
        send_vkey_mock.assert_called_once_with(self.session, 0)
        confirm_field.SetFocus.assert_called_once_with()
        press_mock.assert_called_once_with(self.session, ["save_button"], context=self.context)
        self.assertTrue(result["success"])
        self.assertEqual(len(self.context.messages), 1)
        self.assertIn("Nr. Servico", self.context.messages[0].text)

    @patch("core.iw32.categorias.read_statusbar", return_value=("Salvo", "S"))
    @patch("core.iw32.categorias.close_popup_ok", return_value=False)
    @patch("core.iw32.categorias.press")
    @patch("core.iw32.categorias.select")
    @patch("core.iw32.categorias.first_existing")
    @patch("core.iw32.categorias.send_vkey")
    @patch("core.iw32.categorias.set_text")
    @patch("core.iw32.categorias.select_cuk_tab")
    @patch("core.iw32.categorias.open_order_iw32")
    def test_preencher_categoria_ignora_servico_quando_linha_ja_tem_valor(
        self,
        _open_order_mock,
        select_cuk_tab_mock,
        set_text_mock,
        send_vkey_mock,
        first_existing_mock,
        select_mock,
        press_mock,
        _close_popup_ok_mock,
        _read_statusbar_mock,
    ):
        service_field = Mock()
        service_field.Text = "3000465"
        confirm_field = Mock()
        first_existing_mock.side_effect = [
            (service_field, "service_field"),
            (confirm_field, "confirm_field"),
        ]

        result = preencher_categoria_ordem(
            self.session,
            ordem="5223841",
            categoria="SERVICO DE MANUTENCAO",
            valor="1850,00",
            numero_servico="3000465",
            iw32_profile=self.iw32_profile,
            categorias_profile=self.categorias_profile,
            context=self.context,
        )

        select_cuk_tab_mock.assert_called_once_with(self.session, self.iw32_profile, context=self.context)
        set_text_mock.assert_called_once_with(self.session, ["valor_field"], "1850,00", context=self.context)
        send_vkey_mock.assert_called_once_with(self.session, 0)
        confirm_field.SetFocus.assert_called_once_with()
        press_mock.assert_called_once_with(self.session, ["save_button"], context=self.context)
        self.assertTrue(result["success"])

    @patch("core.iw32.categorias.read_statusbar", return_value=("Salvo", "S"))
    @patch("core.iw32.categorias.close_popup_ok", return_value=False)
    @patch("core.iw32.categorias.press")
    @patch("core.iw32.categorias.select")
    @patch("core.iw32.categorias.first_existing")
    @patch("core.iw32.categorias.send_vkey")
    @patch("core.iw32.categorias.set_text")
    @patch("core.iw32.categorias.select_cuk_tab")
    @patch("core.iw32.categorias.open_order_iw32")
    def test_preencher_categoria_preventiva_usa_linha_6(
        self,
        _open_order_mock,
        _select_cuk_tab_mock,
        set_text_mock,
        send_vkey_mock,
        first_existing_mock,
        select_mock,
        press_mock,
        _close_popup_ok_mock,
        _read_statusbar_mock,
    ):
        service_field = Mock()
        service_field.Text = ""
        confirm_field = Mock()
        first_existing_mock.side_effect = [
            (service_field, "service_field"),
            (confirm_field, "confirm_field_preventiva"),
        ]

        result = preencher_categoria_ordem(
            self.session,
            ordem="5223841",
            categoria="SERVICO DE MANUTENCAO-CONTRATO",
            valor="1850,00",
            numero_servico="3000465",
            iw32_profile=self.iw32_profile,
            categorias_profile=self.categorias_profile,
            context=self.context,
        )

        self.assertEqual(
            set_text_mock.call_args_list,
            [
                call(self.session, ["service_field"], "3000465", context=self.context),
                call(self.session, ["valor_field_preventiva"], "1850,00", context=self.context),
            ],
        )
        self.assertEqual(
            select_mock.call_args_list,
            [
                call(self.session, ["outer_cost_tab_1100"], context=self.context),
                call(self.session, ["inner_cost_tab_1107"], context=self.context),
            ],
        )
        send_vkey_mock.assert_called_once_with(self.session, 0)
        confirm_field.SetFocus.assert_called_once_with()
        press_mock.assert_called_once_with(self.session, ["save_button"], context=self.context)
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
