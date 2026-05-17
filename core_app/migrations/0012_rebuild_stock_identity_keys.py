import re
import unicodedata

from django.db import migrations


def _normalize_text(value):
    text = (value or "").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = " ".join(text.split())
    return text


def rebuild_stock_identity_keys(apps, schema_editor):
    Stock = apps.get_model("core_app", "Stock")

    for stock in Stock.objects.all().iterator():
        normalized_name = _normalize_text(stock.name)
        normalized_subgroup = _normalize_text(stock.subgroup)
        normalized_sku = _normalize_text(stock.sku)

        if normalized_sku:
            identity_key = f"sku:{normalized_sku}|name:{normalized_name}|sub:{normalized_subgroup}"
        else:
            identity_key = f"name:{normalized_name}|sub:{normalized_subgroup}"

        stock.normalized_name = normalized_name
        stock.identity_key = identity_key
        stock.save(update_fields=["normalized_name", "identity_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("core_app", "0011_transaction_header_fields"),
    ]

    operations = [
        migrations.RunPython(rebuild_stock_identity_keys, migrations.RunPython.noop),
    ]
