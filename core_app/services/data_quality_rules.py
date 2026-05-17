ISSUE_DEFINITIONS = {
    "merge_candidates": {
        "label": "Birleştirme Adayı",
        "severity": "medium",
        "severity_label": "Orta",
        "summary_label": "Aynı SKU / aynı ürün",
    },
    "group_code_misuse": {
        "label": "SKU Alanında Grup Kullanımı",
        "severity": "high",
        "severity_label": "Yüksek",
        "summary_label": "SKU alanı yanlış kullanımı",
    },
    "manual_review": {
        "label": "Manuel İnceleme",
        "severity": "high",
        "severity_label": "Yüksek",
        "summary_label": "Çakışmalı SKU",
    },
    "sku_group_conflict": {
        "label": "SKU/Grup Çakışması",
        "severity": "high",
        "severity_label": "Yüksek",
        "summary_label": "Şüpheli eşleşme",
    },
    "name_only_match": {
        "label": "Yalnızca Ad Eşleşmesi",
        "severity": "medium",
        "severity_label": "Orta",
        "summary_label": "Ad var, SKU boş",
    },
    "stock_without_price": {
        "label": "Stokta Var / Fiyat Yok",
        "severity": "medium",
        "severity_label": "Orta",
        "summary_label": "Fiyatı eksik stok",
    },
    "price_without_stock": {
        "label": "Fiyat Listesinde Var / Stokta Yok",
        "severity": "medium",
        "severity_label": "Orta",
        "summary_label": "Eksik stok kartı",
    },
    "same_name_different_identity": {
        "label": "Aynı İsim / Farklı Kimlik",
        "severity": "medium",
        "severity_label": "Orta",
        "summary_label": "İsim çakışması",
    },
}


def get_issue_definition(code):
    default = {
        "label": code,
        "severity": "medium",
        "severity_label": "Orta",
        "summary_label": code,
    }
    return ISSUE_DEFINITIONS.get(code, default)
