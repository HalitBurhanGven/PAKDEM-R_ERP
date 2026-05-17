from django.test import TestCase

from core_app.models import PriceItem, PriceList, Stock
from core_app.services.pricelist_service import (
    build_stock_draft_from_price_item,
    find_existing_stock_for_identity,
    sync_price_list_items_to_stock,
)


class PriceListSyncTests(TestCase):
    def setUp(self):
        self.price_list = PriceList.objects.create(title="Nisan Liste", sheet_name="HIRDAVAT")

    def test_find_existing_stock_matches_legacy_subgroup_mapping(self):
        legacy_stock = Stock.objects.create(
            name="MASKE CAMI",
            sku="",
            subgroup="KANCALI SARYO",
            quantity=0,
            unit="adet",
        )

        existing = find_existing_stock_for_identity("MASKE CAMI", "KANCALI SARYO")

        self.assertIsNotNone(existing)
        self.assertEqual(existing.id, legacy_stock.id)

    def test_sync_price_list_to_stock_skips_existing_exact_identity(self):
        PriceItem.objects.create(price_list=self.price_list, name="MASKE CAMI", group="KANCALI SARYO", price=10)
        Stock.objects.create(name="MASKE CAMI", sku="KANCALI SARYO", quantity=0, unit="adet")

        result = sync_price_list_items_to_stock(self.price_list)

        self.assertEqual(result, {"created": 0, "skipped": 1})
        self.assertEqual(Stock.objects.count(), 1)

    def test_sync_price_list_to_stock_skips_legacy_subgroup_duplicate(self):
        PriceItem.objects.create(price_list=self.price_list, name="MASKE CAMI", group="KANCALI SARYO", price=10)
        Stock.objects.create(
            name="MASKE CAMI",
            sku="",
            subgroup="KANCALI SARYO",
            category="HIRDAVAT",
            quantity=0,
            unit="adet",
        )

        result = sync_price_list_items_to_stock(self.price_list)

        self.assertEqual(result, {"created": 0, "skipped": 1})
        self.assertEqual(Stock.objects.count(), 1)

    def test_sync_price_list_to_stock_creates_missing_items_once(self):
        PriceItem.objects.create(price_list=self.price_list, name="MASKE CAMI", group="KANCALI SARYO", price=10)

        first_result = sync_price_list_items_to_stock(self.price_list)
        second_result = sync_price_list_items_to_stock(self.price_list)

        self.assertEqual(first_result, {"created": 1, "skipped": 0})
        self.assertEqual(second_result, {"created": 0, "skipped": 1})
        self.assertEqual(Stock.objects.count(), 1)

    def test_profile_sheet_sync_creates_meter_unit_stock(self):
        profile_list = PriceList.objects.create(title="Profil Liste", sheet_name="PROFİL10 İSK")
        PriceItem.objects.create(price_list=profile_list, name="20x20x1,20", group="", price=10)

        result = sync_price_list_items_to_stock(profile_list)

        self.assertEqual(result, {"created": 1, "skipped": 0})
        stock = Stock.objects.get(name="20x20x1,20")
        self.assertEqual(stock.unit, "mt")

    def test_profile_sheet_stock_draft_defaults_to_meter_unit(self):
        profile_list = PriceList.objects.create(title="Profil Liste", sheet_name="PROFİL10 İSK")
        item = PriceItem.objects.create(price_list=profile_list, name="20x20x1,20", group="", price=10)

        draft = build_stock_draft_from_price_item(item, profile_list)

        self.assertEqual(draft.unit, "mt")
