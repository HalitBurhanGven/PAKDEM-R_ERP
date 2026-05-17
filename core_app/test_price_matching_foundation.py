from decimal import Decimal

from django.test import TestCase

from core_app.models import PriceItem, PriceList
from core_app.reports.views import build_price_match_data
from core_app.services.stock_identity import create_or_merge_stock


class PriceMatchingFoundationTests(TestCase):
    def test_price_match_respects_sku_based_identity(self):
        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")

        PriceItem.objects.create(
            price_list=price_list,
            name="Pul",
            group="SKU-1",
            price=Decimal("10.00"),
        )

        create_or_merge_stock(
            name="Pul",
            sku="SKU-1",
            subgroup="A",
            quantity=5,
        )

        data = build_price_match_data(price_list.id)
        self.assertEqual(data["counts"]["stocks_without_price"], 0)
        self.assertEqual(data["counts"]["priceitems_without_stock"], 0)

    def test_price_match_flags_missing_match_when_sku_differs(self):
        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")

        PriceItem.objects.create(
            price_list=price_list,
            name="Pul",
            group="SKU-1",
            price=Decimal("10.00"),
        )

        create_or_merge_stock(
            name="Pul",
            sku="SKU-2",
            subgroup="A",
            quantity=5,
        )

        data = build_price_match_data(price_list.id)
        self.assertGreaterEqual(data["counts"]["stocks_without_price"], 1)
        self.assertGreaterEqual(data["counts"]["priceitems_without_stock"], 1)
