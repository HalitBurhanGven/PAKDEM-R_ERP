from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core_app", "0007_stockmergeaudit"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation_type", models.CharField(choices=[("sale", "Satış"), ("return", "İade")], max_length=10)),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                ("total_quantity", models.IntegerField(default=0)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="StockTransactionLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stock_name", models.CharField(max_length=120)),
                ("stock_sku", models.CharField(blank=True, default="", max_length=50)),
                ("stock_category", models.CharField(blank=True, default="", max_length=80)),
                ("stock_subgroup", models.CharField(blank=True, default="", max_length=80)),
                ("description", models.CharField(blank=True, default="", max_length=200)),
                ("quantity", models.IntegerField()),
                ("unit", models.CharField(choices=[("adet", "Adet"), ("kg", "Kg"), ("mt", "Metre")], default="adet", max_length=10)),
                ("unit_price", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("line_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("stock", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transaction_lines", to="core_app.stock")),
                ("transaction", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="core_app.stocktransaction")),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
