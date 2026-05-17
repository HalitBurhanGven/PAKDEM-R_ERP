from django.test import TestCase
from django.urls import reverse

from core_app.models import Stock
from core_app.services.stock_identity import create_or_merge_stock


class CreateOrMergeStockTests(TestCase):
    def test_same_name_same_sku_merges_and_increases_quantity(self):
        create_or_merge_stock(
            name="Pul",
            sku="SKU-1",
            subgroup="A",
            category="HIRDAVAT",
            quantity=5,
        )

        result = create_or_merge_stock(
            name="Pul",
            sku="SKU-1",
            subgroup="A",
            category="HIRDAVAT",
            quantity=3,
        )

        self.assertFalse(result.created)
        self.assertTrue(result.merged)
        self.assertEqual(Stock.objects.count(), 1)
        self.assertEqual(result.stock.quantity, 8)

    def test_same_name_same_sku_different_subgroup_does_not_merge(self):
        create_or_merge_stock(
            name="Pul",
            sku="SKU-1",
            subgroup="A",
            quantity=5,
        )

        result = create_or_merge_stock(
            name="Pul",
            sku="SKU-1",
            subgroup="B",
            quantity=3,
        )

        self.assertTrue(result.created)
        self.assertFalse(result.merged)
        self.assertEqual(Stock.objects.count(), 2)

    def test_same_name_different_sku_creates_new_stock(self):
        create_or_merge_stock(
            name="Pul",
            sku="SKU-1",
            subgroup="A",
            quantity=5,
        )

        result = create_or_merge_stock(
            name="Pul",
            sku="SKU-2",
            subgroup="A",
            quantity=3,
        )

        self.assertTrue(result.created)
        self.assertFalse(result.merged)
        self.assertEqual(Stock.objects.count(), 2)

    def test_same_name_same_subgroup_without_sku_merges(self):
        create_or_merge_stock(
            name="Vida",
            sku="",
            subgroup="YSB",
            quantity=4,
        )

        result = create_or_merge_stock(
            name="Vida",
            sku="",
            subgroup="YSB",
            quantity=6,
        )

        self.assertEqual(Stock.objects.count(), 1)
        self.assertFalse(result.created)
        self.assertEqual(result.stock.quantity, 10)

    def test_same_name_different_subgroup_without_sku_creates_new_stock(self):
        create_or_merge_stock(
            name="Vida",
            sku="",
            subgroup="YSB",
            quantity=4,
        )

        result = create_or_merge_stock(
            name="Vida",
            sku="",
            subgroup="Sunta",
            quantity=6,
        )

        self.assertTrue(result.created)
        self.assertEqual(Stock.objects.count(), 2)

    def test_blank_fields_do_not_overwrite_existing_values(self):
        create_or_merge_stock(
            name="Somun",
            sku="SKU-9",
            subgroup="Alt Grup",
            category="HIRDAVAT",
            quantity=2,
        )

        result = create_or_merge_stock(
            name="Somun",
            sku="SKU-9",
            subgroup="",
            category="",
            quantity=1,
        )

        result.stock.refresh_from_db()
        self.assertEqual(result.stock.subgroup, "Alt Grup")
        self.assertEqual(result.stock.category, "HIRDAVAT")
        self.assertEqual(result.stock.quantity, 3)

    def test_new_stock_sets_normalized_fields(self):
        result = create_or_merge_stock(
            name="Çelik Dübel",
            sku="DBL-1",
            subgroup="Montaj",
            quantity=7,
        )

        self.assertEqual(result.stock.normalized_name, "celik dubel")
        self.assertEqual(result.stock.identity_key, "sku:dbl 1|name:celik dubel|sub:montaj")

    def test_same_sku_different_product_name_creates_new_stock(self):
        create_or_merge_stock(
            name="30X40X1,5ml",
            sku="kirmizi_boyali",
            subgroup="Profil",
            quantity=7000,
        )

        result = create_or_merge_stock(
            name="30X40X2ml",
            sku="kirmizi_boyali",
            subgroup="Profil",
            quantity=7000,
        )

        self.assertTrue(result.created)
        self.assertFalse(result.merged)
        self.assertEqual(Stock.objects.count(), 2)
        self.assertEqual(Stock.objects.get(name="30X40X1,5ml").quantity, 7000)
        self.assertEqual(Stock.objects.get(name="30X40X2ml").quantity, 7000)

    def test_stock_list_post_same_sku_different_product_name_creates_new_row(self):
        response_one = self.client.post(reverse("stock_list"), {
            "name": "30X40X1,5ml",
            "category": "DEMIR",
            "subgroup": "Profil",
            "unit": "mt",
            "sku": "kirmizi_boyali",
            "quantity": 7000,
        })
        response_two = self.client.post(reverse("stock_list"), {
            "name": "30X40X2ml",
            "category": "DEMIR",
            "subgroup": "Profil",
            "unit": "mt",
            "sku": "kirmizi_boyali",
            "quantity": 7000,
        })

        self.assertEqual(response_one.status_code, 302)
        self.assertEqual(response_two.status_code, 302)
        self.assertEqual(Stock.objects.count(), 2)
        self.assertEqual(Stock.objects.get(name="30X40X1,5ml").quantity, 7000)
        self.assertEqual(Stock.objects.get(name="30X40X2ml").quantity, 7000)

    def test_category_bulk_subgroup_refreshes_identity_key(self):
        stock = Stock.objects.create(
            name="Vida",
            category="HIRDAVAT",
            subgroup="YSB",
            quantity=4,
        )

        response = self.client.post(
            reverse("category_bulk_subgroup", args=["HIRDAVAT"]),
            {
                "stock_ids": [str(stock.id)],
                "subgroup_new": "Sunta",
                "next": reverse("category_detail", args=["HIRDAVAT"]),
            },
        )

        self.assertEqual(response.status_code, 302)
        stock.refresh_from_db()
        self.assertEqual(stock.subgroup, "Sunta")
        self.assertEqual(stock.identity_key, "name:vida|sub:sunta")
