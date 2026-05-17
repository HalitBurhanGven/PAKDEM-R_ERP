from decimal import Decimal

from django.test import TestCase

from core_app.models import PriceItem, PriceList
from core_app.services.matching_service import build_price_match_data
from core_app.services.stock_identity import create_or_merge_stock
from core_app.services.stock_service import get_stock_list_data


class PriceMatchingConsistencyTests(TestCase):
    def test_exact_match_uses_same_logic_in_stock_list_and_report(self):
        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        PriceItem.objects.create(price_list=price_list, name="Pul", group="SKU-1", price=Decimal("10.00"))

        create_or_merge_stock(name="Pul", sku="SKU-1", subgroup="A", quantity=5)

        stock_data = get_stock_list_data(active_price_list_id=price_list.id)
        report_data = build_price_match_data(price_list.id)

        stock = stock_data["stocks"][0]
        self.assertEqual(stock.last_price, Decimal("10.00"))
        self.assertEqual(stock.stock_value, Decimal("50.00"))
        self.assertEqual(stock_data["total_stock_value"], Decimal("50.00"))
        self.assertEqual(report_data["counts"]["stocks_without_price"], 0)
        self.assertEqual(report_data["counts"]["priceitems_without_stock"], 0)

    def test_grouped_price_does_not_name_match_sku_empty_stock_in_stock_value_or_report(self):
        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        PriceItem.objects.create(price_list=price_list, name="Pul", group="SKU-1", price=Decimal("10.00"))

        create_or_merge_stock(name="Pul", sku="", subgroup="A", quantity=5)

        stock_data = get_stock_list_data(active_price_list_id=price_list.id)
        report_data = build_price_match_data(price_list.id)

        stock = stock_data["stocks"][0]
        self.assertIsNone(stock.last_price)
        self.assertIsNone(stock.stock_value)
        self.assertEqual(stock_data["total_stock_value"], Decimal("0.00"))
        self.assertEqual(report_data["counts"]["suspects"], 1)
        self.assertEqual(report_data["counts"]["stocks_without_price"], 1)
        self.assertEqual(report_data["counts"]["priceitems_without_stock"], 1)

    def test_name_only_price_matches_sku_empty_stock_and_values_inventory(self):
        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        PriceItem.objects.create(price_list=price_list, name="Pul", group="", price=Decimal("12.00"))

        create_or_merge_stock(name="Pul", sku="", subgroup="A", quantity=4)

        stock_data = get_stock_list_data(active_price_list_id=price_list.id)
        report_data = build_price_match_data(price_list.id)

        stock = stock_data["stocks"][0]
        self.assertEqual(stock.last_price, Decimal("12.00"))
        self.assertEqual(stock.stock_value, Decimal("48.00"))
        self.assertEqual(report_data["counts"]["stocks_without_price"], 0)
        self.assertEqual(report_data["counts"]["priceitems_without_stock"], 0)

    def test_meter_unit_stock_list_hides_last_price_and_value(self):
        price_list = PriceList.objects.create(title="Liste 1", sheet_name="PROFİL10 İSK")
        PriceItem.objects.create(price_list=price_list, name="20x20x1,20", group="", price=Decimal("12.00"))

        create_or_merge_stock(name="20x20x1,20", sku="", subgroup="", unit="mt", quantity=4)

        stock_data = get_stock_list_data(active_price_list_id=price_list.id)

        stock = stock_data["stocks"][0]
        self.assertIsNone(stock.last_price)
        self.assertIsNone(stock.stock_value)
        self.assertEqual(stock_data["total_stock_value"], Decimal("0.00"))
