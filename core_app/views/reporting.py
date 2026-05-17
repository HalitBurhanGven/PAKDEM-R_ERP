from django.db.models import Q, Sum
from django.shortcuts import render

from core_app.models import StockMovement


def report_home(request):
    return render(request, "core_app/report_home.html")


def movement_report(request):
    rows = (
        StockMovement.objects.exclude(stock__category="")
        .values("stock__category")
        .annotate(
            total_in=Sum("quantity", filter=Q(movement_type=StockMovement.IN)),
            total_out=Sum("quantity", filter=Q(movement_type=StockMovement.OUT)),
        )
        .order_by("stock__category")
    )

    labels = []
    in_data = []
    out_data = []
    for row in rows:
        labels.append(row["stock__category"])
        in_data.append(row["total_in"] or 0)
        out_data.append(row["total_out"] or 0)

    return render(request, "core_app/movement_report.html", {
        "labels": labels,
        "in_data": in_data,
        "out_data": out_data,
    })
