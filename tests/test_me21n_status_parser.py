import unittest

from core.me21n.status_parser import parse_purchase_order_number


class Me21nStatusParserTests(unittest.TestCase):
    def test_parse_portuguese_message(self):
        self.assertEqual(parse_purchase_order_number("Documento de compras 4500012345 criado", "S"), "4500012345")

    def test_parse_fallback_success_number(self):
        self.assertEqual(parse_purchase_order_number("Processado com sucesso 4500012345", "S"), "4500012345")

    def test_ignore_non_success_generic_number(self):
        self.assertIsNone(parse_purchase_order_number("Erro na ordem 4500012345", "E"))


if __name__ == "__main__":
    unittest.main()
