from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core_app.models import PriceList
from core_app.price_forms import PriceImportForm
from core_app.services.price_import import (
    PriceImportError,
    import_price_list_workbook,
    preview_price_list_workbook,
)
from core_app.services.pricelist_service import (
    get_price_list_detail_data,
    get_price_list_list_data,
    sync_price_list_items_to_stock,
)


def import_price_list(request):
    if request.method == "POST":
        form = PriceImportForm(request.POST, request.FILES)
        if form.is_valid():
            action = (request.POST.get("action") or "preview").strip()
            sheet_input = (form.cleaned_data.get("sheet") or "").strip()
            title = (form.cleaned_data.get("title") or "").strip()

            try:
                if action == "preview":
                    preview = preview_price_list_workbook(
                        file_obj=form.cleaned_data["file"],
                        sheet_input=sheet_input,
                        title=title,
                    )
                    return render(request, "core_app/price_import.html", {
                        "form": form,
                        "preview": preview,
                    })

                result = import_price_list_workbook(
                    file_obj=form.cleaned_data["file"],
                    sheet_input=sheet_input,
                    title=title,
                )
            except PriceImportError as exc:
                messages.error(request, str(exc))
                return render(request, "core_app/price_import.html", {"form": form})

            request.session["active_price_list_id"] = result.price_list.id
            messages.success(request, f"Fiyat listesi içe aktarıldı. Kalem sayısı: {result.created_count}")
            return redirect("price_list_detail", pk=result.price_list.id)
    else:
        form = PriceImportForm()

    return render(request, "core_app/price_import.html", {"form": form})


def price_list_detail(request, pk):
    get_object_or_404(PriceList, pk=pk)
    return render(request, "core_app/price_list_detail.html", get_price_list_detail_data(pk))


def price_list_list(request):
    q = (request.GET.get("q") or "").strip()
    context = get_price_list_list_data(q=q, active_id=request.session.get("active_price_list_id"))
    return render(request, "core_app/price_list_list.html", context)


def set_active_price_list(request, pk):
    price_list = get_object_or_404(PriceList, pk=pk)
    request.session["active_price_list_id"] = price_list.id
    messages.success(request, f"Aktif fiyat listesi seçildi: {price_list.title}")
    return redirect("price_list_list")


def price_list_delete(request, pk):
    price_list = get_object_or_404(PriceList, pk=pk)
    if request.method == "POST":
        if request.session.get("active_price_list_id") == price_list.id:
            request.session.pop("active_price_list_id", None)
        title = price_list.title
        price_list.delete()
        messages.success(request, f"Silindi: {title}")
    return redirect("price_list_list")


@require_POST
def sync_price_list_to_stock(request):
    active_id = request.session.get("active_price_list_id")
    if not active_id:
        messages.error(request, "Aktif fiyat listesi seçili değil.")
        return redirect("price_list_list")

    price_list = PriceList.objects.filter(id=active_id).first()
    if not price_list:
        messages.error(request, "Aktif fiyat listesi bulunamadı.")
        request.session.pop("active_price_list_id", None)
        return redirect("price_list_list")

    result = sync_price_list_items_to_stock(price_list)
    messages.success(
        request,
        f"Aktif fiyat listesinden stoğa aktarıldı. Yeni={result['created']}, Zaten vardı={result['skipped']}",
    )
    return redirect("stock_list")

