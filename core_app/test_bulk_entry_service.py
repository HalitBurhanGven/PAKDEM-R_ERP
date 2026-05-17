from django.test import TestCase
from django.urls import reverse

from core_app.models import PriceItem, PriceList, Stock
from core_app.services.bulk_entry_service import build_bulk_entry_preview


class BulkEntryServiceTests(TestCase):
    def setUp(self):
        self.stock_a = Stock.objects.create(name="100x200 Kum Mozaik", sku="KM-100", quantity=30, unit="adet", category="HIRDAVAT")
        self.stock_b = Stock.objects.create(name="22'lik Menteşe", sku="MNT-22", quantity=15, unit="adet", category="HIRDAVAT")
        self.stock_c = Stock.objects.create(name="G/N Beyaz", sku="GN-BYZ", quantity=8, unit="adet", category="BOYA")

        self.price_list = PriceList.objects.create(title="Perakende", sheet_name="GENEL")
        PriceItem.objects.create(price_list=self.price_list, name="100x200 Kum Mozaik", group="KM-100", price="54.00")
        PriceItem.objects.create(price_list=self.price_list, name="22'lik Menteşe", group="MNT-22", price="6.00")
        PriceItem.objects.create(price_list=self.price_list, name="G/N Beyaz", group="GN-BYZ", price="2.00")

        session = self.client.session
        session["active_price_list_id"] = self.price_list.id
        session.save()

        self.catalog = [
            {
                "id": self.stock_a.id,
                "label": "100x200 Kum Mozaik | KM-100 | HIRDAVAT",
                "name": self.stock_a.name,
                "sku": self.stock_a.sku,
                "category": self.stock_a.category,
                "subgroup": self.stock_a.subgroup,
                "unit": self.stock_a.unit,
                "unit_price": "54.00",
            },
            {
                "id": self.stock_b.id,
                "label": "22'lik Menteşe | MNT-22 | HIRDAVAT",
                "name": self.stock_b.name,
                "sku": self.stock_b.sku,
                "category": self.stock_b.category,
                "subgroup": self.stock_b.subgroup,
                "unit": self.stock_b.unit,
                "unit_price": "6.00",
            },
            {
                "id": self.stock_c.id,
                "label": "G/N Beyaz | GN-BYZ | BOYA",
                "name": self.stock_c.name,
                "sku": self.stock_c.sku,
                "category": self.stock_c.category,
                "subgroup": self.stock_c.subgroup,
                "unit": self.stock_c.unit,
                "unit_price": "2.00",
            },
        ]

    def test_build_bulk_entry_preview_parses_and_matches_lines(self):
        preview = build_bulk_entry_preview(
            "100x200 kum mozaik 12\n22lik menteşe 16\nG/N Beyaz 2",
            self.catalog,
        )

        self.assertEqual(preview["summary"]["total"], 3)
        self.assertEqual(preview["summary"]["matched"], 3)
        self.assertEqual(preview["rows"][0]["quantity"], 12)
        self.assertEqual(str(preview["rows"][1]["matched_stock_id"]), str(self.stock_b.id))
        self.assertEqual(preview["rows"][2]["unit_price"], "2.00")

    def test_build_bulk_entry_preview_marks_unknown_line_with_suggestion(self):
        preview = build_bulk_entry_preview("22lik mentesee 3\nbilinmeyen urun 5", self.catalog)

        self.assertEqual(preview["rows"][0]["status"], "suggested")
        self.assertTrue(preview["rows"][0]["suggestions"])
        self.assertEqual(preview["rows"][1]["status"], "unmatched")

    def test_build_bulk_entry_preview_uses_catalog_price_and_default_unit(self):
        preview = build_bulk_entry_preview("100x200 kum mozaik 12", self.catalog)

        self.assertEqual(preview["rows"][0]["status"], "matched")
        self.assertEqual(preview["rows"][0]["unit"], "adet")
        self.assertEqual(preview["rows"][0]["unit_price"], "54.00")

    def test_build_bulk_entry_preview_preserves_explicit_unit_and_price(self):
        preview = build_bulk_entry_preview("100x200 kum mozaik 5 adet 61", self.catalog)

        self.assertEqual(preview["rows"][0]["status"], "matched")
        self.assertEqual(preview["rows"][0]["quantity"], 5)
        self.assertEqual(preview["rows"][0]["unit"], "adet")
        self.assertEqual(preview["rows"][0]["unit_price"], "61.00")

    def test_bulk_preview_endpoint_returns_json_rows(self):
        response = self.client.post(
            reverse("operation_bulk_preview"),
            {"bulk_text": "100x200 kum mozaik 12\nG/N Beyaz 2"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["total"], 2)
        self.assertEqual(payload["rows"][0]["status"], "matched")
        self.assertEqual(payload["rows"][1]["parsed_name"], "G/N Beyaz")

    def test_bulk_preview_endpoint_blocks_return_mode_in_first_version(self):
        response = self.client.post(
            reverse("operation_bulk_preview"),
            {
                "bulk_text": "100x200 kum mozaik 12",
                "operation_type": "return",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["total"], 0)
        self.assertEqual(payload["rows"], [])
        self.assertIn("satış modunda", payload["message"])
