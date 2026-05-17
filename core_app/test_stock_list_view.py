from django.test import TestCase
from django.urls import reverse

from core_app.models import Stock


class StockListViewTests(TestCase):
    def test_stock_list_groups_rows_by_category_and_subgroup(self):
        lock = Stock.objects.create(
            name="Asma Kilit",
            category="HIRDAVAT",
            subgroup="Kilitler",
            sku="KLT-01",
            quantity=12,
            unit="adet",
        )
        Stock.objects.create(
            name="Surgu",
            category="HIRDAVAT",
            subgroup="Surguler",
            sku="SRG-01",
            quantity=5,
            unit="adet",
        )
        Stock.objects.create(
            name="Cati Sacı",
            category="DEMIR",
            subgroup="Cati Malzemeleri",
            sku="DMR-01",
            quantity=20,
            unit="mt",
        )

        response = self.client.get(reverse("stock_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HIRDAVAT")
        self.assertContains(response, "Kilitler")
        self.assertContains(response, "Surguler")
        self.assertContains(response, "DEMIR")
        self.assertContains(response, "Cati Malzemeleri")
        self.assertContains(response, "KLT-01")
        self.assertContains(response, reverse("stock_edit", args=[lock.id]))
        self.assertContains(response, "Alt Kategori")

        stock_groups = response.context["stock_groups"]
        self.assertEqual(stock_groups[0]["label"], "DEMIR")
        self.assertEqual(stock_groups[1]["label"], "HIRDAVAT")
        self.assertEqual(stock_groups[1]["subgroups"][0]["label"], "Kilitler")

    def test_stock_list_groups_blank_values_under_fallback_labels(self):
        Stock.objects.create(
            name="Tanimsiz Urun",
            category="",
            subgroup="",
            sku="",
            quantity=3,
            unit="adet",
        )

        response = self.client.get(reverse("stock_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kategorisiz")
        self.assertContains(response, "Diğer / Alt kategori yok")

    def test_stock_list_empty_state_still_renders_cleanly(self):
        response = self.client.get(reverse("stock_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Henüz stok yok.")
