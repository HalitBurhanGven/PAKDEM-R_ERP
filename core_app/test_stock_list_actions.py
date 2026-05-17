from django.test import TestCase
from django.urls import reverse

from core_app.models import Stock


class StockListActionTests(TestCase):
    def test_stock_list_search_matches_sku_and_subgroup_text(self):
        stock_match = Stock.objects.create(
            name="12 MM",
            sku="",
            subgroup="MENTEŞELER",
            quantity=1,
            unit="adet",
        )
        stock_other = Stock.objects.create(
            name="MASKE CAMI",
            sku="KANCALI SARYO",
            quantity=1,
            unit="adet",
        )

        response = self.client.get(reverse("stock_list"), {"q": "menteşeler"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, stock_match.name)
        self.assertNotContains(response, stock_other.name)

    def test_bulk_delete_removes_selected_stocks_only(self):
        stock_a = Stock.objects.create(name="Urun A", quantity=1, unit="adet")
        stock_b = Stock.objects.create(name="Urun B", quantity=1, unit="adet")
        stock_c = Stock.objects.create(name="Urun C", quantity=1, unit="adet")

        response = self.client.post(
            reverse("stock_bulk_delete"),
            {
                "stock_ids": [str(stock_a.id), str(stock_c.id)],
                "next": reverse("stock_list"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Stock.objects.filter(id=stock_a.id).exists())
        self.assertTrue(Stock.objects.filter(id=stock_b.id).exists())
        self.assertFalse(Stock.objects.filter(id=stock_c.id).exists())

    def test_bulk_delete_without_selection_keeps_stocks(self):
        stock = Stock.objects.create(name="Urun A", quantity=1, unit="adet")

        response = self.client.post(
            reverse("stock_bulk_delete"),
            {
                "next": reverse("stock_list"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Stock.objects.filter(id=stock.id).exists())
