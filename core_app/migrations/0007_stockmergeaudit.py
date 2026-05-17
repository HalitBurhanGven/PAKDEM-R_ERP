from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core_app", "0006_stock_identity_key_stock_is_active_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockMergeAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("removed_stock_id", models.IntegerField()),
                ("merged_at", models.DateTimeField(auto_now_add=True)),
                ("left_snapshot", models.JSONField(default=dict)),
                ("right_snapshot", models.JSONField(default=dict)),
                ("field_sources", models.JSONField(default=dict)),
                ("merged_quantity", models.IntegerField(default=0)),
                ("surviving_stock", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="merge_audits", to="core_app.stock")),
            ],
            options={
                "ordering": ["-merged_at", "-id"],
            },
        ),
    ]
