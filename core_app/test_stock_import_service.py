from io import BytesIO

from django.test import TestCase
from openpyxl import Workbook

from core_app.models import Stock
from core_app.services.stock_import_service import StockImportError, import_stock_rows, parse_stock_workbook


class StockImportServiceTests(TestCase):
    def _build_workbook_file(self, rows):
        workbook = Workbook()
        worksheet = workbook.active
        for row in rows:
            worksheet.append(row)

        file_obj = BytesIO()
        workbook.save(file_obj)
        file_obj.seek(0)
        return file_obj

    def test_parse_stock_workbook_reports_missing_headers(self):
        file_obj = self._build_workbook_file([
            ["name", "category", "sku"],
            ["Vida", "HIRDAVAT", "SKU-1"],
        ])

        parsed = parse_stock_workbook(file_obj)

        self.assertEqual(parsed["missing_headers"], ["quantity"])

    def test_parse_stock_workbook_skips_blank_rows_and_counts_errors(self):
        file_obj = self._build_workbook_file([
            ["name", "category", "unit", "sku", "quantity"],
            ["Vida", "HIRDAVAT", "metre", "SKU-1", "3"],
            [None, None, None, None, None],
            ["Pul", "HIRDAVAT", "koli", "SKU-2", "x"],
            ["", "HIRDAVAT", "adet", "", "5"],
        ])

        parsed = parse_stock_workbook(file_obj)

        self.assertEqual(parsed["processed_rows"], 3)
        self.assertEqual(parsed["blank_rows"], 1)
        self.assertEqual(len(parsed["valid_rows"]), 1)
        self.assertEqual(parsed["error_count"], 2)
        self.assertEqual(parsed["error_reasons"]["quantity geçersiz"], 1)
        self.assertEqual(parsed["error_reasons"]["name boş"], 1)

    def test_import_stock_rows_returns_summary_with_error_breakdown(self):
        file_obj = self._build_workbook_file([
            ["name", "category", "unit", "sku", "quantity"],
            ["Pul", "HIRDAVAT", "adet", "P-1", "2"],
            [None, None, None, None, None],
            ["Pul", "HIRDAVAT", "adet", "P-1", "3"],
            ["Vida", "HIRDAVAT", "adet", "", "x"],
        ])

        parsed = parse_stock_workbook(file_obj)
        summary = import_stock_rows(parsed)

        self.assertEqual(summary.created, 1)
        self.assertEqual(summary.updated, 1)
        self.assertEqual(summary.total, 4)
        self.assertEqual(summary.processed, 3)
        self.assertEqual(summary.skipped, 2)
        self.assertEqual(summary.errors, 1)
        self.assertEqual(summary.error_reasons["quantity geçersiz"], 1)
        self.assertEqual(Stock.objects.get(sku="P-1").quantity, 5)

    def test_parse_stock_workbook_rejects_broken_file(self):
        file_obj = BytesIO(b"not-an-excel-file")

        with self.assertRaises(StockImportError):
            parse_stock_workbook(file_obj)
