import unittest
from decimal import Decimal

from core.common.excel_utils import as_decimal, normalize_column_name


class ExcelUtilsTests(unittest.TestCase):
    def test_normalize_column_name(self):
        self.assertEqual(normalize_column_name("Data Entrega"), "DATAENTREGA")
        self.assertEqual(normalize_column_name("Refrigeração"), "REFRIGERACAO")

    def test_as_decimal_accepts_brazilian_and_dot_formats(self):
        self.assertEqual(as_decimal("1.234,56"), Decimal("1234.56"))
        self.assertEqual(as_decimal("1234.56"), Decimal("1234.56"))


if __name__ == "__main__":
    unittest.main()
