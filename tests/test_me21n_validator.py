import unittest
from decimal import Decimal

from core.me21n.validator import validate_payload


class Me21nValidatorTests(unittest.TestCase):
    def _profile(self):
        return {
            "capabilities": {"requiresPlantOrCenter": True},
            "constraints": {"allowedTaxCodes": ["S1", "S2"]},
        }

    def _header(self):
        return [
            {
                "doc_ref": "DOC-1",
                "tipo_doc": "NB",
                "org_compras": "1000",
                "grupo_compras": "112",
                "empresa": "BEM1",
                "fornecedor": "101",
                "moeda": "BRL",
                "condicao_pagamento": "0001",
            }
        ]

    def _item_f(self):
        return {
            "item_ref": "10",
            "texto_livre": "SUBESTACAO",
            "categoria_item": "D",
            "categoria_classif": "F",
            "grupo_mercadoria": "SERVICOS",
            "conta_razao_default": "5110401",
            "tax_code": "S2",
            "plant_or_center": "101 - BEMOL S/A",
        }

    def _item_k(self):
        return {
            "item_ref": "20",
            "texto_livre": "SERVICO INTERNO",
            "categoria_item": "D",
            "categoria_classif": "K",
            "grupo_mercadoria": "SERVICOS",
            "conta_razao_default": "5110401",
            "tax_code": "S1",
            "plant_or_center": "101 - BEMOL S/A",
        }

    def _service_f(self):
        return {
            "item_ref": "10",
            "line_ref": "10",
            "numero_servico": "3000465",
            "quantidade": "1",
            "preco_bruto": "750,00",
            "ordem": "5221782",
        }

    def _service_k(self):
        return {
            "item_ref": "20",
            "line_ref": "10",
            "numero_servico": "3000465",
            "quantidade": "1",
            "preco_bruto": "650,00",
            "centro_custo": "640800",
        }

    def test_validate_accepts_item_f_with_order(self):
        payload, errors, warnings = validate_payload(
            self._header(),
            [self._item_f()],
            [self._service_f()],
            profile=self._profile(),
        )
        self.assertIsNotNone(payload)
        self.assertFalse(errors)
        self.assertFalse(warnings)
        self.assertEqual(payload.items[0].service_lines[0].ordem, "5221782")
        self.assertEqual(payload.items[0].service_lines[0].conta_razao, "5110401")

    def test_validate_accepts_item_k_with_cost_center(self):
        payload, errors, warnings = validate_payload(
            self._header(),
            [self._item_k()],
            [self._service_k()],
            profile=self._profile(),
        )
        self.assertIsNotNone(payload)
        self.assertFalse(errors)
        self.assertFalse(warnings)
        self.assertEqual(payload.items[0].service_lines[0].centro_custo, "640800")

    def test_validate_groups_service_lines_by_item(self):
        item_f = self._item_f()
        service_a = self._service_f()
        service_b = dict(self._service_f(), line_ref="20", ordem="5222692", preco_bruto="1346,55")
        payload, errors, warnings = validate_payload(
            self._header(),
            [item_f],
            [service_b, service_a],
            profile=self._profile(),
        )
        self.assertIsNotNone(payload)
        self.assertFalse(errors)
        self.assertFalse(warnings)
        self.assertEqual(len(payload.items[0].service_lines), 2)
        self.assertEqual(payload.items[0].service_lines[0].line_ref, "10")
        self.assertEqual(payload.items[0].service_lines[1].line_ref, "20")

    def test_validate_fails_without_services_sheet_rows(self):
        payload, errors, _warnings = validate_payload(self._header(), [self._item_f()], [], profile=self._profile())
        self.assertIsNone(payload)
        self.assertTrue(any(issue.sheet == "SERVICOS" for issue in errors))

    def test_validate_fails_when_item_has_no_service_lines(self):
        payload, errors, _warnings = validate_payload(
            self._header(),
            [self._item_f()],
            [dict(self._service_f(), item_ref="99")],
            profile=self._profile(),
        )
        self.assertIsNone(payload)
        self.assertTrue(any("Item sem linhas de servico" in issue.message for issue in errors))

    def test_validate_fails_when_categoria_item_is_not_d(self):
        item = self._item_f()
        item["categoria_item"] = "B"
        payload, errors, _warnings = validate_payload(self._header(), [item], [self._service_f()], profile=self._profile())
        self.assertIsNone(payload)
        self.assertTrue(any("Categoria_item deve ser D" in issue.message for issue in errors))

    def test_validate_fails_when_categoria_classif_is_invalid(self):
        item = self._item_f()
        item["categoria_classif"] = "A"
        payload, errors, _warnings = validate_payload(self._header(), [item], [self._service_f()], profile=self._profile())
        self.assertIsNone(payload)
        self.assertTrue(any("Categoria_classif deve ser F ou K" in issue.message for issue in errors))

    def test_validate_fails_when_header_missing_payment_terms(self):
        header = self._header()
        del header[0]["condicao_pagamento"]
        payload, errors, _warnings = validate_payload(header, [self._item_f()], [self._service_f()], profile=self._profile())
        self.assertIsNone(payload)
        self.assertTrue(any(issue.column_name == "condicao_pagamento" for issue in errors))

    def test_validate_fails_when_f_line_missing_order(self):
        service = self._service_f()
        service["ordem"] = ""
        payload, errors, _warnings = validate_payload(
            self._header(),
            [self._item_f()],
            [service],
            profile=self._profile(),
        )
        self.assertIsNone(payload)
        self.assertTrue(any(issue.column_name == "ordem" for issue in errors))

    def test_validate_fails_when_k_line_missing_cost_center(self):
        service = self._service_k()
        service["centro_custo"] = ""
        payload, errors, _warnings = validate_payload(
            self._header(),
            [self._item_k()],
            [service],
            profile=self._profile(),
        )
        self.assertIsNone(payload)
        self.assertTrue(any(issue.column_name == "centro_custo" for issue in errors))

    def test_validate_fails_when_line_and_item_have_no_gl_account(self):
        item = self._item_f()
        item["conta_razao_default"] = ""
        payload, errors, _warnings = validate_payload(
            self._header(),
            [item],
            [self._service_f()],
            profile=self._profile(),
        )
        self.assertIsNone(payload)
        self.assertTrue(any(issue.sheet == "SERVICOS" and issue.column_name == "conta_razao" for issue in errors))

    def test_validate_accepts_tax_codes_s1_and_s2(self):
        payload_s2, errors_s2, _warnings_s2 = validate_payload(
            self._header(),
            [self._item_f()],
            [self._service_f()],
            profile=self._profile(),
        )
        self.assertIsNotNone(payload_s2)
        self.assertFalse(errors_s2)

        payload_s1, errors_s1, _warnings_s1 = validate_payload(
            self._header(),
            [self._item_k()],
            [self._service_k()],
            profile=self._profile(),
        )
        self.assertIsNotNone(payload_s1)
        self.assertFalse(errors_s1)

    def test_validate_fails_when_tax_code_is_not_allowed(self):
        item = self._item_f()
        item["tax_code"] = "ZZ"
        payload, errors, _warnings = validate_payload(
            self._header(),
            [item],
            [self._service_f()],
            profile=self._profile(),
        )
        self.assertIsNone(payload)
        self.assertTrue(any(issue.column_name == "tax_code" for issue in errors))

    def test_validate_fails_when_tax_code_is_missing(self):
        item = self._item_f()
        item["tax_code"] = ""
        payload, errors, _warnings = validate_payload(
            self._header(),
            [item],
            [self._service_f()],
            profile=self._profile(),
        )
        self.assertIsNone(payload)
        self.assertTrue(any(issue.column_name == "tax_code" and "obrigatorio" in issue.message.lower() for issue in errors))

    def test_validate_defaults_missing_gross_price_to_zero(self):
        service = self._service_f()
        service["preco_bruto"] = ""
        payload, errors, warnings = validate_payload(
            self._header(),
            [self._item_f()],
            [service],
            profile=self._profile(),
        )
        self.assertIsNotNone(payload)
        self.assertFalse(errors)
        self.assertFalse(warnings)
        self.assertEqual(payload.items[0].service_lines[0].preco_bruto, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
