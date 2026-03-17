import unittest

from core.iw32.categorias_input import parse_group_orders, parse_manual_rows


class Iw32CategoriasInputTests(unittest.TestCase):
    def test_parse_manual_rows_supports_tab_semicolon_and_comma(self):
        raw = "\n".join(
            [
                "5223882\tEDUCANDOS\t800,00",
                "5223883;COROADO;900,00",
                "5223884, FRANCESES, 1.500,00",
            ]
        )

        rows, errors = parse_manual_rows(
            raw,
            default_tipo="Preventiva",
            default_numero_servico="3000465",
        )

        self.assertEqual(errors, [])
        self.assertEqual([item["ordem"] for item in rows], ["5223882", "5223883", "5223884"])
        self.assertEqual([item["valor"] for item in rows], ["800,00", "900,00", "1.500,00"])
        self.assertEqual([item["categoria"] for item in rows], ["SERVICO DE MANUTENCAO-CONTRATO"] * 3)
        self.assertEqual([item["numero_servico"] for item in rows], ["3000465"] * 3)

    def test_parse_manual_rows_accepts_optional_type_and_service(self):
        rows, errors = parse_manual_rows(
            "5223882;EDUCANDOS;800,00;Corretiva;3000999",
            default_tipo="Preventiva",
            default_numero_servico="3000465",
        )

        self.assertEqual(errors, [])
        self.assertEqual(
            rows,
            [
                {
                    "ordem": "5223882",
                    "nome": "EDUCANDOS",
                    "categoria": "SERVICO DE MANUTENCAO",
                    "valor": "800,00",
                    "numero_servico": "3000999",
                }
            ],
        )

    def test_parse_manual_rows_uses_defaults_when_optional_columns_are_missing(self):
        rows, errors = parse_manual_rows(
            "5223882;EDUCANDOS;800,00",
            default_tipo="Corretiva",
            default_numero_servico="3000465",
        )

        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["categoria"], "SERVICO DE MANUTENCAO")
        self.assertEqual(rows[0]["numero_servico"], "3000465")

    def test_parse_manual_rows_accepts_order_and_value_only_with_pipe_or_spaces(self):
        raw = "\n".join(
            [
                "| 5204714 | R$ 320,00 |",
                "5829327  380",
            ]
        )

        rows, errors = parse_manual_rows(
            raw,
            default_tipo="Corretiva",
            default_numero_servico="3000465",
        )

        self.assertEqual(errors, [])
        self.assertEqual(
            rows,
            [
                {
                    "ordem": "5204714",
                    "nome": "",
                    "categoria": "SERVICO DE MANUTENCAO",
                    "valor": "320,00",
                    "numero_servico": "3000465",
                },
                {
                    "ordem": "5829327",
                    "nome": "",
                    "categoria": "SERVICO DE MANUTENCAO",
                    "valor": "380",
                    "numero_servico": "3000465",
                },
            ],
        )

    def test_parse_manual_rows_skips_markdown_header_and_rejects_invalid_value(self):
        raw = "\n".join(
            [
                "| Ordem | Valor |",
                "| --- | --- |",
                "| 5223138 | Cancelada |",
            ]
        )

        rows, errors = parse_manual_rows(
            raw,
            default_tipo="Corretiva",
            default_numero_servico="3000465",
        )

        self.assertEqual(rows, [])
        self.assertEqual([item["line_number"] for item in errors], [3])
        self.assertIn("Valor invalido", errors[0]["message"])

    def test_parse_manual_rows_rejects_invalid_order_and_missing_value(self):
        rows, errors = parse_manual_rows(
            "\n".join(
                [
                    "ABC;EDUCANDOS;800,00",
                    "5223882;COROADO;",
                ]
            ),
            default_tipo="Corretiva",
            default_numero_servico="3000465",
        )

        self.assertEqual(rows, [])
        self.assertEqual([item["line_number"] for item in errors], [1, 2])
        self.assertIn("apenas numeros", errors[0]["message"])
        self.assertIn("Valor obrigatorio", errors[1]["message"])

    def test_parse_manual_rows_rejects_unconfigured_categories_when_allowed_set_is_provided(self):
        rows, errors = parse_manual_rows(
            "5223882;EDUCANDOS;800,00;AR CONDICIONADO",
            default_tipo="Corretiva",
            default_numero_servico="3000465",
            allowed_categories={"SERVICO DE MANUTENCAO", "SERVICO DE MANUTENCAO-CONTRATO"},
        )

        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("Categoria nao configurada", errors[0]["message"])

    def test_parse_group_orders_preserves_name_and_rejects_invalid_order(self):
        rows, errors = parse_group_orders(
            "\n".join(
                [
                    "5223882, EDUCANDOS",
                    "5223883",
                    "XYZ, INVALIDA",
                ]
            )
        )

        self.assertEqual(
            rows,
            [
                {"ordem": "5223882", "nome": "EDUCANDOS"},
                {"ordem": "5223883", "nome": ""},
            ],
        )
        self.assertEqual([item["line_number"] for item in errors], [3])


if __name__ == "__main__":
    unittest.main()
