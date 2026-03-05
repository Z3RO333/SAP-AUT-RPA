import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from core.common.logging import ExecutionLogger
from core.common.run_context import RunContext
from core.me21n.models import PurchaseOrderHeader, PurchaseOrderItem, PurchaseOrderPayload, PurchaseOrderServiceLine
from core.me21n.sap_driver import (
    _close_value_help_popup,
    _fill_header,
    _handle_account_assignment_popup,
    _save_or_validate,
    execute_purchase_order,
)


class _FakeWindow:
    def maximize(self):
        return None

    def sendVKey(self, _key):
        return None


class _FakeSession:
    def __init__(self):
        self.windows = {"wnd[0]": _FakeWindow()}

    def findById(self, path):
        if path not in self.windows:
            raise RuntimeError(path)
        return self.windows[path]


class Me21nDriverTests(unittest.TestCase):
    def setUp(self):
        logger = ExecutionLogger(Path("logs/test-me21n-driver.log"))
        self.context = RunContext(logger=logger)

    def _payload_f(self):
        return PurchaseOrderPayload(
            header=PurchaseOrderHeader(
                doc_ref="DOC-1",
                tipo_doc="NB",
                org_compras="1000",
                grupo_compras="112",
                empresa="BEM1",
                fornecedor="101",
                moeda="BRL",
                condicao_pagamento="0001",
            ),
            items=[
                PurchaseOrderItem(
                    item_ref="10",
                    texto_livre="CORRETIVAS",
                    categoria_item="D",
                    categoria_classif="F",
                    grupo_mercadoria="SERVICOS",
                    plant_or_center="101 - BEMOL S/A",
                    tax_code="S2",
                    conta_razao_default="5110401",
                    service_lines=[
                        PurchaseOrderServiceLine(
                            item_ref="10",
                            line_ref="10",
                            numero_servico="3000465",
                            quantidade=Decimal("1"),
                            preco_bruto=Decimal("750.00"),
                            ordem="5221782",
                            conta_razao="5110401",
                        )
                    ],
                )
            ],
        )

    def _payload_k(self):
        return PurchaseOrderPayload(
            header=self._payload_f().header,
            items=[
                PurchaseOrderItem(
                    item_ref="20",
                    texto_livre="SERVICO INTERNO",
                    categoria_item="D",
                    categoria_classif="K",
                    grupo_mercadoria="SERVICOS",
                    plant_or_center="101 - BEMOL S/A",
                    tax_code="S1",
                    conta_razao_default="5110401",
                    service_lines=[
                        PurchaseOrderServiceLine(
                            item_ref="20",
                            line_ref="10",
                            numero_servico="3000465",
                            quantidade=Decimal("1"),
                            preco_bruto=Decimal("650.00"),
                            centro_custo="640800",
                            conta_razao="5110401",
                        )
                    ],
                )
            ],
        )

    def _payload_f_without_price(self):
        payload = self._payload_f()
        payload.items[0].service_lines[0].preco_bruto = None
        return payload

    def _profile(self):
        return {
            "header": {
                "supplierTop": ["supplier"],
                "paymentTerms": ["payment"],
                "purchOrg": ["org"],
                "purchGroup": ["group"],
                "companyCode": ["company"],
            },
            "headerTabs": {"commercial": ["tab_commercial"], "orgData": ["tab_org"]},
            "preNavigation": {"expandHeaderButtons": ["expand_header"], "expandItemButtons": ["expand_item"]},
            "itemOverview": {
                "accountAssignmentCategory": ["knttp[{row}]"],
                "itemCategory": ["epstp[{row}]"],
                "shortText": ["short[{row}]"],
                "materialGroup": ["group[{row}]"],
                "plantOrCenter": ["center[{row}]"],
            },
            "itemDetail": {"serviceTab": ["service_tab"], "taxTab": ["tax_tab"], "textTab": ["text_tab"]},
            "serviceLines": {
                "serviceNumber": ["srv[{row}]"],
                "externalText": ["text[{row}]"],
                "quantity": ["qty[{row}]"],
                "grossPrice": ["value[{row}]"],
                "order": ["order[{row}]"],
            },
            "accountPopup": {
                "prePopupOk": ["pre_ok"],
                "glAccountField": ["gl_field"],
                "orderField": ["order_popup"],
                "costCenterField": ["cost_center_popup"],
                "confirm": ["gl_ok"],
            },
            "itemFields": {"taxCode": ["tax_code"], "observation": ["obs"]},
            "toolbar": {"save": ["save"]},
            "validationActions": {"check": ["check"]},
            "popupPolicies": {"saveConfirmationOption2": ["save_confirm"]},
        }

    @patch("core.me21n.sap_driver._handle_account_assignment_popup")
    @patch("core.me21n.sap_driver.wait_not_busy")
    @patch("core.me21n.sap_driver.read_statusbar")
    @patch("core.me21n.sap_driver.send_vkey")
    @patch("core.me21n.sap_driver.select")
    @patch("core.me21n.sap_driver.set_text")
    @patch("core.me21n.sap_driver.press")
    @patch("core.me21n.sap_driver.element_exists", return_value=True)
    @patch("core.me21n.sap_driver.tcode")
    def test_execute_purchase_order_dry_run_does_not_save(
        self,
        _tcode,
        _element_exists,
        press_mock,
        set_text_mock,
        select_mock,
        send_vkey_mock,
        read_statusbar_mock,
        _wait_not_busy,
        _popup_mock,
    ):
        read_statusbar_mock.return_value = ("Validado sem salvar", "S")
        session = _FakeSession()
        result = execute_purchase_order(session, self._payload_f(), self._profile(), dry_run=True, context=self.context)
        self.assertFalse(result["created"])
        self.assertIsNone(result["poNumber"])
        pressed_targets = [call.args[1] for call in press_mock.call_args_list]
        self.assertIn(["check"], pressed_targets)
        self.assertNotIn(["save"], pressed_targets)
        self.assertTrue(set_text_mock.called)
        self.assertTrue(select_mock.called)
        self.assertTrue(send_vkey_mock.called)

    @patch("core.me21n.sap_driver._handle_account_assignment_popup")
    @patch("core.me21n.sap_driver.wait_not_busy")
    @patch("core.me21n.sap_driver.read_statusbar")
    @patch("core.me21n.sap_driver.send_vkey")
    @patch("core.me21n.sap_driver.select")
    @patch("core.me21n.sap_driver.set_text")
    @patch("core.me21n.sap_driver.press")
    @patch("core.me21n.sap_driver.element_exists", return_value=True)
    @patch("core.me21n.sap_driver.tcode")
    def test_execute_purchase_order_skips_gross_price_when_not_in_payload(
        self,
        _tcode,
        _element_exists,
        _press_mock,
        set_text_mock,
        _select_mock,
        _send_vkey_mock,
        read_statusbar_mock,
        _wait_not_busy,
        _popup_mock,
    ):
        read_statusbar_mock.return_value = ("Validado sem salvar", "S")
        session = _FakeSession()
        profile = self._profile()
        profile["serviceLines"].pop("grossPrice", None)
        execute_purchase_order(session, self._payload_f_without_price(), profile, dry_run=True, context=self.context)
        written_targets = [call.args[1] for call in set_text_mock.call_args_list]
        self.assertNotIn(["value[0]"], written_targets)

    @patch("core.me21n.sap_driver._handle_account_assignment_popup")
    @patch("core.me21n.sap_driver.wait_not_busy")
    @patch("core.me21n.sap_driver.read_statusbar")
    @patch("core.me21n.sap_driver.send_vkey")
    @patch("core.me21n.sap_driver.select")
    @patch("core.me21n.sap_driver.set_text")
    @patch("core.me21n.sap_driver.press")
    @patch("core.me21n.sap_driver.element_exists", return_value=True)
    @patch("core.me21n.sap_driver.tcode")
    def test_execute_purchase_order_uses_single_tax_code_value(
        self,
        _tcode,
        _element_exists,
        _press_mock,
        set_text_mock,
        _select_mock,
        _send_vkey_mock,
        read_statusbar_mock,
        _wait_not_busy,
        _popup_mock,
    ):
        read_statusbar_mock.return_value = ("Validado sem salvar", "S")
        session = _FakeSession()
        execute_purchase_order(session, self._payload_f(), self._profile(), dry_run=True, context=self.context)
        tax_values = [call.args[2] for call in set_text_mock.call_args_list if call.args[1] == ["tax_code"]]
        self.assertEqual(tax_values, ["S2"])

    def test_close_value_help_popup_uses_close_popup_ok(self):
        session = _FakeSession()
        with (
            patch("core.me21n.sap_driver._window_exists", side_effect=[True, False]) as window_exists_mock,
            patch("core.me21n.sap_driver.close_popup_ok", return_value=True) as close_popup_ok_mock,
            patch("core.me21n.sap_driver.wait_not_busy") as wait_not_busy_mock,
            patch("core.me21n.sap_driver._send_vkey_to_window") as send_vkey_mock,
            patch("core.me21n.sap_driver._capture_status") as capture_status_mock,
        ):
            _close_value_help_popup(
                session,
                self.context,
                stage="me21n-item-material-group-popup",
                details={"itemRef": "10", "row": 0},
                max_attempts=3,
            )
        self.assertEqual(window_exists_mock.call_count, 2)
        close_popup_ok_mock.assert_called_once_with(session)
        wait_not_busy_mock.assert_called_once_with(session)
        send_vkey_mock.assert_not_called()
        self.assertEqual(capture_status_mock.call_count, 1)
        self.assertEqual(capture_status_mock.call_args.args[2], "me21n-item-material-group-popup")
        self.assertEqual(capture_status_mock.call_args.args[3]["action"], "close_popup_ok")

    def test_close_value_help_popup_raises_when_popup_persists(self):
        session = _FakeSession()
        with (
            patch("core.me21n.sap_driver._window_exists", side_effect=[True, True, True, True]) as window_exists_mock,
            patch("core.me21n.sap_driver.close_popup_ok", return_value=False) as close_popup_ok_mock,
            patch("core.me21n.sap_driver._send_vkey_to_window") as send_vkey_mock,
            patch("core.me21n.sap_driver._capture_status") as capture_status_mock,
        ):
            with self.assertRaisesRegex(RuntimeError, "me21n-item-material-group-popup"):
                _close_value_help_popup(
                    session,
                    self.context,
                    stage="me21n-item-material-group-popup",
                    details={"itemRef": "10", "row": 0},
                    max_attempts=3,
                )
        self.assertEqual(window_exists_mock.call_count, 4)
        self.assertEqual(close_popup_ok_mock.call_count, 3)
        self.assertEqual(send_vkey_mock.call_count, 3)
        self.assertEqual(capture_status_mock.call_count, 3)
        send_vkey_mock.assert_called_with(session, "wnd[1]", 0)

    @patch("core.me21n.sap_driver.select")
    @patch("core.me21n.sap_driver._capture_status", return_value=("", "S"))
    @patch("core.me21n.sap_driver._set_text_and_confirm")
    def test_fill_header_skips_org_data_when_payment_is_enough(self, set_text_mock, _capture_status_mock, select_mock):
        session = _FakeSession()
        _fill_header(session, self._payload_f(), self._profile(), self.context)
        stages = [call.args[4] for call in set_text_mock.call_args_list]
        self.assertIn("me21n-header-fornecedor", stages)
        self.assertIn("me21n-header-payment", stages)
        self.assertNotIn("me21n-header-org", stages)
        self.assertNotIn("me21n-header-group", stages)
        self.assertNotIn("me21n-header-company", stages)
        self.assertNotIn("me21n-header-payment-retry", stages)
        tab_targets = [call.args[1] for call in select_mock.call_args_list]
        self.assertEqual(tab_targets, [["tab_commercial"]])

    @patch("core.me21n.sap_driver.select")
    @patch("core.me21n.sap_driver._capture_status", return_value=("Entrar Org.compras", "E"))
    @patch("core.me21n.sap_driver._set_text_and_confirm")
    def test_fill_header_falls_back_to_org_data_when_required(self, set_text_mock, _capture_status_mock, select_mock):
        session = _FakeSession()
        _fill_header(session, self._payload_f(), self._profile(), self.context)
        stages = [call.args[4] for call in set_text_mock.call_args_list]
        self.assertIn("me21n-header-payment", stages)
        self.assertIn("me21n-header-org", stages)
        self.assertIn("me21n-header-group", stages)
        self.assertIn("me21n-header-company", stages)
        self.assertIn("me21n-header-payment-retry", stages)
        tab_targets = [call.args[1] for call in select_mock.call_args_list]
        self.assertEqual(tab_targets, [["tab_commercial"], ["tab_org"], ["tab_commercial"]])

    @patch("core.me21n.sap_driver.read_statusbar", return_value=("Linha validada", "S"))
    @patch("core.me21n.sap_driver.set_text")
    @patch("core.me21n.sap_driver.press")
    def test_account_popup_sequence_handles_wnd2_then_wnd1_for_f(self, press_mock, set_text_mock, _read_statusbar):
        session = _FakeSession()
        session.windows["wnd[1]"] = _FakeWindow()
        session.windows["wnd[2]"] = _FakeWindow()
        item = self._payload_f().items[0]
        service_line = item.service_lines[0]

        def _press_side_effect(_session, target, context=None):
            if target == ["pre_ok"]:
                session.windows.pop("wnd[2]", None)
            if target == ["gl_ok"]:
                session.windows.pop("wnd[1]", None)

        press_mock.side_effect = _press_side_effect
        _handle_account_assignment_popup(
            session,
            item,
            service_line,
            self._profile(),
            self.context,
            reference_already_filled=True,
        )
        self.assertEqual(press_mock.call_args_list[0].args[1], ["pre_ok"])
        self.assertEqual(set_text_mock.call_args_list[0].args[1], ["gl_field"])
        self.assertEqual(press_mock.call_args_list[1].args[1], ["gl_ok"])

    @patch("core.me21n.sap_driver.read_statusbar", return_value=("Linha validada", "S"))
    @patch("core.me21n.sap_driver.set_text")
    @patch("core.me21n.sap_driver.press")
    def test_account_popup_fills_cost_center_for_k(self, press_mock, set_text_mock, _read_statusbar):
        session = _FakeSession()
        session.windows["wnd[1]"] = _FakeWindow()
        item = self._payload_k().items[0]
        service_line = item.service_lines[0]

        def _press_side_effect(_session, target, context=None):
            if target == ["gl_ok"]:
                session.windows.pop("wnd[1]", None)

        press_mock.side_effect = _press_side_effect
        _handle_account_assignment_popup(
            session,
            item,
            service_line,
            self._profile(),
            self.context,
            reference_already_filled=False,
        )
        written_targets = [call.args[1] for call in set_text_mock.call_args_list]
        self.assertIn(["gl_field"], written_targets)
        self.assertIn(["cost_center_popup"], written_targets)
        self.assertEqual(press_mock.call_args_list[-1].args[1], ["gl_ok"])

    @patch("core.me21n.sap_driver.read_statusbar", return_value=("Documento de compras 4500012345 criado", "S"))
    @patch("core.me21n.sap_driver.press")
    def test_save_handles_confirmation_option2(self, press_mock, _read_statusbar):
        session = _FakeSession()
        session.windows["wnd[1]"] = _FakeWindow()
        result = _save_or_validate(session, self._profile(), dry_run=False, context=self.context)
        self.assertTrue(result["created"])
        self.assertEqual(result["poNumber"], "4500012345")
        self.assertEqual(press_mock.call_args_list[0].args[1], ["save"])
        self.assertEqual(press_mock.call_args_list[1].args[1], ["save_confirm"])


if __name__ == "__main__":
    unittest.main()
