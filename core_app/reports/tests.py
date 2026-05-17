from django.test import TestCase
from django.urls import reverse

from core_app.models import Stock, StockMergeAudit, StockMovement
from core_app.services.data_quality_service import (
    build_data_quality_overview,
    build_same_name_identity_data,
    build_same_name_identity_detail,
)
from core_app.services.duplicate_sku_service import (
    build_duplicate_sku_data,
    classify_duplicate_sku,
    cleanup_group_code_misuse_sku,
)
from core_app.services.matching_service import build_price_match_data


class DuplicateSkuReportTests(TestCase):
    def test_classify_duplicate_sku_as_merge_candidate_for_same_name(self):
        records = [
            {"name": "Urun A", "subgroup": "", "quantity": 2},
            {"name": "Urun A", "subgroup": "", "quantity": 3},
        ]

        strategy = classify_duplicate_sku(records)

        self.assertEqual(strategy["code"], "merge_candidates")

    def test_classify_duplicate_sku_as_group_code_misuse_for_distinct_names(self):
        records = [
            {"name": "Urun A", "subgroup": "", "quantity": 0},
            {"name": "Urun B", "subgroup": "", "quantity": 0},
        ]

        strategy = classify_duplicate_sku(records)

        self.assertEqual(strategy["code"], "group_code_misuse")

    def test_classify_duplicate_sku_as_manual_review_when_subgroups_exist(self):
        records = [
            {"name": "Urun A", "subgroup": "Alt 1", "quantity": 5},
            {"name": "Urun B", "subgroup": "Alt 2", "quantity": 1},
        ]

        strategy = classify_duplicate_sku(records)

        self.assertEqual(strategy["code"], "manual_review")

    def test_build_duplicate_sku_data_returns_only_duplicate_skus(self):
        Stock.objects.create(name="Urun A", sku="SKU-1", quantity=2, unit="adet", category="A")
        Stock.objects.create(name="Urun B", sku="SKU-1", quantity=3, unit="adet", category="B")
        Stock.objects.create(name="Urun C", sku="SKU-2", quantity=4, unit="adet", category="B")

        data = build_duplicate_sku_data()

        self.assertEqual(data["duplicate_count"], 1)
        self.assertEqual(data["rows"][0]["sku"], "SKU-1")
        self.assertEqual(data["rows"][0]["record_count"], 2)
        self.assertEqual(data["rows"][0]["total_quantity"], 5)
        self.assertEqual(data["summary"]["group_code_misuse"], 1)

    def test_duplicate_sku_report_page_renders_duplicate_skus(self):
        Stock.objects.create(name="Urun A", sku="SKU-1", quantity=2, unit="adet", subgroup="Alt 1")
        Stock.objects.create(name="Urun B", sku="SKU-1", quantity=3, unit="adet", subgroup="Alt 2")

        response = self.client.get(reverse("reports:duplicate_sku_report"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SKU-1")
        self.assertContains(response, "Urun A")
        self.assertContains(response, "Urun B")
        self.assertContains(response, reverse("stock_edit", args=[1]))
        self.assertContains(response, reverse("stock_movement", args=[1]))
        self.assertContains(response, reverse("reports:stock_merge_assistant") + "?left=1&right=2")

    def test_cleanup_group_code_misuse_sku_moves_value_to_subgroup_and_clears_sku(self):
        stock_a = Stock.objects.create(name="Urun A", sku="GRUP-1", quantity=2, unit="adet", subgroup="")
        stock_b = Stock.objects.create(name="Urun B", sku="GRUP-1", quantity=3, unit="adet", subgroup="")

        result = cleanup_group_code_misuse_sku("GRUP-1")

        stock_a.refresh_from_db()
        stock_b.refresh_from_db()
        self.assertEqual(result["cleaned_groups"], 1)
        self.assertEqual(result["cleaned_rows"], 2)
        self.assertEqual(stock_a.sku, "")
        self.assertEqual(stock_b.sku, "")
        self.assertEqual(stock_a.subgroup, "GRUP-1")
        self.assertEqual(stock_b.subgroup, "GRUP-1")

    def test_cleanup_group_code_misuse_sku_skips_manual_review_groups(self):
        stock_a = Stock.objects.create(name="Urun A", sku="SKU-1", quantity=2, unit="adet", subgroup="Alt 1")
        stock_b = Stock.objects.create(name="Urun B", sku="SKU-1", quantity=3, unit="adet", subgroup="Alt 2")

        result = cleanup_group_code_misuse_sku("SKU-1")

        stock_a.refresh_from_db()
        stock_b.refresh_from_db()
        self.assertEqual(result["cleaned_groups"], 0)
        self.assertEqual(result["skipped_groups"], 1)
        self.assertEqual(stock_a.sku, "SKU-1")
        self.assertEqual(stock_b.sku, "SKU-1")

    def test_cleanup_duplicate_sku_report_post_runs(self):
        Stock.objects.create(name="Urun A", sku="GRUP-1", quantity=2, unit="adet", subgroup="")
        Stock.objects.create(name="Urun B", sku="GRUP-1", quantity=3, unit="adet", subgroup="")

        response = self.client.post(reverse("reports:cleanup_duplicate_sku_report"), {"sku": "GRUP-1"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Stock.objects.filter(sku="GRUP-1").count(), 0)

    def test_same_name_identity_data_flags_same_name_different_identity(self):
        Stock.objects.create(name="Pul", sku="SKU-1", quantity=2, unit="adet", subgroup="A")
        Stock.objects.create(name="Pul", sku="SKU-2", quantity=3, unit="adet", subgroup="B")

        data = build_same_name_identity_data()

        self.assertEqual(data["count"], 1)
        self.assertEqual(data["rows"][0]["issue"]["code"], "same_name_different_identity")

    def test_data_quality_overview_matches_duplicate_summary(self):
        Stock.objects.create(name="Urun A", sku="SKU-1", quantity=2, unit="adet", subgroup="Alt 1")
        Stock.objects.create(name="Urun B", sku="SKU-1", quantity=3, unit="adet", subgroup="Alt 2")

        overview = build_data_quality_overview()
        duplicate_data = build_duplicate_sku_data()

        self.assertEqual(overview["duplicate_sku_groups"], duplicate_data["duplicate_count"])
        self.assertEqual(overview["manual_review"], duplicate_data["summary"]["manual_review"])

    def test_price_match_data_assigns_distinct_issue_classes(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        PriceItem.objects.create(price_list=price_list, name="Pul", group="SKU-1", price=Decimal("10.00"))
        PriceItem.objects.create(price_list=price_list, name="Vida", group="", price=Decimal("5.00"))

        Stock.objects.create(name="Pul", sku="", quantity=2, unit="adet")

        data = build_price_match_data(price_list.id)

        self.assertEqual(data["suspects"][0]["issue"]["code"], "name_only_match")
        self.assertEqual(data["stocks_without_price"][0]["issue"]["code"], "stock_without_price")
        self.assertEqual(data["priceitems_without_stock"][0]["issue"]["code"], "price_without_stock")

    def test_price_match_report_renders_manual_action_links(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        PriceItem.objects.create(price_list=price_list, name="Pul", group="SKU-1", price=Decimal("10.00"))
        PriceItem.objects.create(price_list=price_list, name="Vida", group="", price=Decimal("5.00"))
        Stock.objects.create(name="Pul", sku="", quantity=2, unit="adet")

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.get(reverse("reports:price_match_report") + "?tab=priceitems_without_stock")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("reports:create_stock_from_price_match", args=[2]))
        self.assertContains(response, reverse("stock_list") + "?q=Vida")
        self.assertContains(response, reverse("price_list_detail", args=[price_list.id]))

    def test_create_stock_from_unmatched_price_item_creates_stock(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        item = PriceItem.objects.create(price_list=price_list, name="Vida", group="SKU-NEW", price=Decimal("5.00"))

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.post(reverse("reports:create_stock_from_price_match", args=[item.id]), {
            "name": "Vida",
            "sku": "SKU-NEW",
            "category": "HIRDAVAT",
            "unit": "adet",
            "quantity": 0,
        })

        self.assertEqual(response.status_code, 302)
        stock = Stock.objects.get(name="Vida", sku="SKU-NEW")
        self.assertEqual(stock.category, "HIRDAVAT")
        self.assertEqual(stock.quantity, 0)

    def test_create_stock_from_price_item_get_prefills_form(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        item = PriceItem.objects.create(price_list=price_list, name="Vida", group="SKU-NEW", price=Decimal("5.00"))

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.get(reverse("reports:create_stock_from_price_match", args=[item.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Vida"')
        self.assertContains(response, 'value="SKU-NEW"')
        self.assertContains(response, 'value="HIRDAVAT"')
        self.assertContains(response, 'value="0"')

    def test_create_stock_from_price_item_allows_editable_form_create(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        item = PriceItem.objects.create(price_list=price_list, name="Vida", group="SKU-NEW", price=Decimal("5.00"))

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.post(reverse("reports:create_stock_from_price_match", args=[item.id]), {
            "name": "Vida Sarjli",
            "sku": "SKU-REV",
            "category": "EL ALETLERI",
            "unit": "kg",
            "quantity": 4,
        })

        self.assertEqual(response.status_code, 302)
        stock = Stock.objects.get(name="Vida Sarjli", sku="SKU-REV")
        self.assertEqual(stock.category, "EL ALETLERI")
        self.assertEqual(stock.unit, "kg")
        self.assertEqual(stock.quantity, 4)

    def test_create_stock_from_price_item_rejects_missing_name(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        item = PriceItem.objects.create(price_list=price_list, name="", group="SKU-NEW", price=Decimal("5.00"))

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.post(reverse("reports:create_stock_from_price_match", args=[item.id]), {
            "name": "V",
            "sku": "SKU-NEW",
            "category": "HIRDAVAT",
            "unit": "adet",
            "quantity": 0,
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Stock.objects.filter(sku="SKU-NEW").exists())
        self.assertContains(response, "Ürün adı en az 2 karakter olmalı.")

    def test_create_stock_from_price_item_prevents_duplicate_create(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        item = PriceItem.objects.create(price_list=price_list, name="Vida", group="SKU-NEW", price=Decimal("5.00"))
        existing_stock = Stock.objects.create(name="Vida", sku="SKU-NEW", quantity=0, unit="adet", category="HIRDAVAT")

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.post(reverse("reports:create_stock_from_price_match", args=[item.id]), {
            "name": "Vida",
            "sku": "SKU-NEW",
            "category": "HIRDAVAT",
            "unit": "adet",
            "quantity": 0,
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Stock.objects.filter(name="Vida", sku="SKU-NEW").count(), 1)
        self.assertContains(response, "Yeni Stok Kartı Oluşturulamadı")
        self.assertContains(response, f"#{existing_stock.id} - Vida")
        self.assertContains(response, reverse("stock_edit", args=[existing_stock.id]))
        self.assertContains(response, reverse("stock_movement", args=[existing_stock.id]))
        self.assertContains(response, "Çakışma kararında kullanıldı")

    def test_create_stock_from_price_item_duplicate_get_shows_explanation(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        item = PriceItem.objects.create(price_list=price_list, name="Vida", group="SKU-NEW", price=Decimal("5.00"))
        existing_stock = Stock.objects.create(name="Vida", sku="SKU-NEW", quantity=7, unit="adet", category="HIRDAVAT")

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.get(reverse("reports:create_stock_from_price_match", args=[item.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bu varsayılan kimlikte stok kartı zaten mevcut.")
        self.assertContains(response, reverse("stock_edit", args=[existing_stock.id]))
        self.assertContains(response, reverse("stock_movement", args=[existing_stock.id]))

    def test_create_stock_from_price_item_duplicate_allows_return_to_edit_mode(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        item = PriceItem.objects.create(price_list=price_list, name="Vida", group="SKU-NEW", price=Decimal("5.00"))
        Stock.objects.create(name="Vida", sku="SKU-NEW", quantity=7, unit="adet", category="HIRDAVAT")

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.get(
            reverse("reports:create_stock_from_price_match", args=[item.id]) +
            "?edit=1&name=Vida+Yeni&sku=SKU-ALT&category=HIRDAVAT&unit=adet&quantity=3"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Vida Yeni"')
        self.assertContains(response, 'value="SKU-ALT"')
        self.assertContains(response, 'value="3"')

    def test_same_name_conflict_detail_page_renders_records_and_links(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        PriceItem.objects.create(price_list=price_list, name="Pul", group="SKU-1", price=Decimal("10.00"))
        first = Stock.objects.create(name="Pul", sku="SKU-1", quantity=2, unit="adet", category="HIRDAVAT", subgroup="A")
        second = Stock.objects.create(name="Pul", sku="SKU-2", quantity=3, unit="adet", category="HIRDAVAT", subgroup="B")

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.get(reverse("reports:same_name_conflict_detail") + "?name=pul")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pul")
        self.assertContains(response, reverse("stock_edit", args=[first.id]))
        self.assertContains(response, reverse("stock_movement", args=[first.id]))
        self.assertContains(response, reverse("stock_edit", args=[second.id]))
        self.assertContains(response, "10.00")
        self.assertContains(response, reverse("reports:stock_merge_assistant") + f"?left={first.id}&right={second.id}")

    def test_same_name_conflict_detail_redirects_safely_when_missing_or_invalid(self):
        response_missing = self.client.get(reverse("reports:same_name_conflict_detail"))
        response_invalid = self.client.get(reverse("reports:same_name_conflict_detail") + "?name=olmayan")

        self.assertEqual(response_missing.status_code, 302)
        self.assertEqual(response_missing.url, reverse("reports:duplicate_sku_report"))
        self.assertEqual(response_invalid.status_code, 302)
        self.assertEqual(response_invalid.url, reverse("reports:duplicate_sku_report"))

    def test_same_name_conflict_detail_helper_returns_none_for_invalid_input(self):
        Stock.objects.create(name="Pul", sku="SKU-1", quantity=2, unit="adet", subgroup="A")
        Stock.objects.create(name="Pul", sku="SKU-2", quantity=3, unit="adet", subgroup="B")

        self.assertIsNone(build_same_name_identity_detail(""))
        self.assertIsNone(build_same_name_identity_detail("olmayan"))

    def test_stock_merge_preview_page_opens(self):
        left = Stock.objects.create(name="Pul", sku="SKU-1", quantity=2, unit="adet", category="A", subgroup="Alt 1")
        right = Stock.objects.create(name="Pul", sku="SKU-1", quantity=3, unit="kg", category="B", subgroup="Alt 2")

        response = self.client.get(reverse("reports:stock_merge_assistant") + f"?left={left.id}&right={right.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Çakışan Stok Birleştirme Asistanı")
        self.assertContains(response, reverse("stock_edit", args=[left.id]))
        self.assertContains(response, reverse("stock_edit", args=[right.id]))
        self.assertContains(response, "5")

    def test_stock_merge_assistant_rejects_same_record_pair(self):
        stock = Stock.objects.create(name="Pul", sku="SKU-1", quantity=2, unit="adet")

        response = self.client.get(reverse("reports:stock_merge_assistant") + f"?left={stock.id}&right={stock.id}")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("reports:duplicate_sku_report"))

    def test_stock_merge_assistant_merges_with_selected_fields(self):
        left = Stock.objects.create(name="Pul Sol", sku="SKU-L", quantity=2, unit="adet", category="HIRDAVAT", subgroup="Alt L")
        right = Stock.objects.create(name="Pul Sag", sku="SKU-R", quantity=3, unit="kg", category="BOYA", subgroup="Alt R")
        StockMovement.objects.create(stock=left, movement_type=StockMovement.IN, quantity=2, note="left")
        StockMovement.objects.create(stock=right, movement_type=StockMovement.IN, quantity=3, note="right")

        response = self.client.post(reverse("reports:stock_merge_assistant"), {
            "left_id": left.id,
            "right_id": right.id,
            "survivor_side": "left",
            "name_source": "right",
            "sku_source": "left",
            "category_source": "right",
            "subgroup_source": "right",
            "unit_source": "right",
            "confirm": "on",
        })

        self.assertEqual(response.status_code, 302)
        left.refresh_from_db()
        self.assertEqual(left.name, "Pul Sag")
        self.assertEqual(left.sku, "SKU-L")
        self.assertEqual(left.category, "BOYA")
        self.assertEqual(left.subgroup, "Alt R")
        self.assertEqual(left.unit, "kg")
        self.assertEqual(left.quantity, 5)
        self.assertFalse(Stock.objects.filter(id=right.id).exists())
        self.assertTrue(left.is_active)
        self.assertEqual(StockMovement.objects.count(), 2)
        self.assertEqual(StockMovement.objects.filter(stock=left).count(), 2)
        audit = StockMergeAudit.objects.get(surviving_stock=left)
        self.assertEqual(audit.removed_stock_id, right.id)
        self.assertEqual(audit.field_sources["survivor_side"], "left")
        self.assertEqual(audit.field_sources["name_source"], "right")
        self.assertEqual(audit.field_sources["sku_source"], "left")
        self.assertEqual(audit.merged_quantity, 5)
        self.assertEqual(audit.left_snapshot["name"], "Pul Sol")
        self.assertEqual(audit.right_snapshot["name"], "Pul Sag")
        self.assertEqual(response.url, reverse("stock_edit", args=[left.id]))

    def test_stock_merge_assistant_does_not_merge_without_confirmation(self):
        left = Stock.objects.create(name="Pul Sol", sku="SKU-L", quantity=2, unit="adet")
        right = Stock.objects.create(name="Pul Sag", sku="SKU-R", quantity=3, unit="kg")

        response = self.client.post(reverse("reports:stock_merge_assistant"), {
            "left_id": left.id,
            "right_id": right.id,
            "survivor_side": "left",
            "name_source": "left",
            "sku_source": "left",
            "category_source": "left",
            "subgroup_source": "left",
            "unit_source": "left",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Stock.objects.filter(id__in=[left.id, right.id]).count(), 2)
        self.assertEqual(StockMergeAudit.objects.count(), 0)
        self.assertContains(response, "This field is required.")

    def test_stock_merge_assistant_redirects_safely_for_invalid_ids(self):
        response = self.client.get(reverse("reports:stock_merge_assistant") + "?left=999&right=1000")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("reports:duplicate_sku_report"))

    def test_stock_edit_shows_merge_audit_history(self):
        left = Stock.objects.create(name="Pul Sol", sku="SKU-L", quantity=2, unit="adet", category="HIRDAVAT", subgroup="Alt L")
        right = Stock.objects.create(name="Pul Sag", sku="SKU-R", quantity=3, unit="kg", category="BOYA", subgroup="Alt R")

        self.client.post(reverse("reports:stock_merge_assistant"), {
            "left_id": left.id,
            "right_id": right.id,
            "survivor_side": "left",
            "name_source": "left",
            "sku_source": "left",
            "category_source": "left",
            "subgroup_source": "left",
            "unit_source": "left",
            "confirm": "on",
        })

        response = self.client.get(reverse("stock_edit", args=[left.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Merge Audit Geçmişi")
        self.assertContains(response, f"Kaldırılan Kayıt:</strong> #{right.id}")

    def test_duplicate_report_filters_without_breaking_totals(self):
        for index in range(6):
            sku = f"SKU-{index}"
            Stock.objects.create(name=f"Urun {index} A", sku=sku, quantity=1, unit="adet", subgroup="Alt A")
            Stock.objects.create(name=f"Urun {index} B", sku=sku, quantity=2, unit="adet", subgroup="Alt B")

        response = self.client.get(reverse("reports:duplicate_sku_report") + "?q=Urun+1+A&severity=high&issue_code=manual_review")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Toplam çakışan SKU sayısı: <strong>6</strong>", html=True)
        self.assertContains(response, "Filtreli çakışan grup sayısı: <strong>1</strong>", html=True)
        self.assertContains(response, "SKU-1")
        self.assertNotContains(response, "SKU-0")

    def test_same_name_conflict_list_paginates(self):
        for index in range(6):
            Stock.objects.create(name=f"Pul {index}", sku=f"SKU-L-{index}", quantity=1, unit="adet", subgroup="A")
            Stock.objects.create(name=f"Pul {index}", sku=f"SKU-R-{index}", quantity=2, unit="adet", subgroup="B")

        response = self.client.get(reverse("reports:duplicate_sku_report") + "?issue_code=same_name_different_identity&same_page=2")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aynı isim sayfası 2 / 2")
        self.assertContains(response, "Pul 5")
        self.assertNotContains(response, "Pul 0 #")

    def test_price_match_report_filters_and_paginates(self):
        from decimal import Decimal
        from core_app.models import PriceItem, PriceList

        price_list = PriceList.objects.create(title="Liste 1", sheet_name="HIRDAVAT")
        for index in range(11):
            PriceItem.objects.create(
                price_list=price_list,
                name=f"Urun {index}",
                group=f"SKU-{index}",
                price=Decimal("10.00"),
            )

        session = self.client.session
        session["active_price_list_id"] = price_list.id
        session.save()

        response = self.client.get(
            reverse("reports:price_match_report") +
            "?tab=priceitems_without_stock&issue_code=price_without_stock&page=2"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fiyatta var / stok yok:</b> 11", html=False)
        self.assertContains(response, "Sayfa 2 / 2")
        self.assertContains(response, "Urun 10")
        self.assertNotContains(response, "Urun 0")
