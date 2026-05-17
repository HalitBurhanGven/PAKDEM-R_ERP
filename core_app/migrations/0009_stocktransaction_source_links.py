from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core_app", "0008_stocktransaction_stocktransactionline"),
    ]

    operations = [
        migrations.AddField(
            model_name="stocktransaction",
            name="source_transaction",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="derived_transactions", to="core_app.stocktransaction"),
        ),
        migrations.AddField(
            model_name="stocktransactionline",
            name="source_line",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="derived_lines", to="core_app.stocktransactionline"),
        ),
    ]
