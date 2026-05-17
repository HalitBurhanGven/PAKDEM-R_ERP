from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_app", "0009_stocktransaction_source_links"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockTransactionDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation_type", models.CharField(choices=[("sale", "Satış"), ("return", "İade")], default="sale", max_length=10)),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                ("source_transaction_id", models.IntegerField(blank=True, null=True)),
                ("rows", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
            },
        ),
    ]
