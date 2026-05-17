from dataclasses import dataclass
from functools import lru_cache
from math import ceil


@dataclass(frozen=True)
class CutRequest:
    cut_length: int
    requested_quantity: int


@dataclass(frozen=True)
class SingleCutPlanResult:
    standard_length: int
    cut_length: int
    requested_quantity: int
    pieces_per_stock: int
    waste_per_full_stock: int
    required_stock_count: int
    full_stock_count: int
    partial_stock_count: int
    partial_stock_used_pieces: int
    partial_stock_waste: int
    total_waste: int
    total_produced_pieces: int
    overproduced_pieces: int

    @property
    def has_partial_stock(self):
        return self.partial_stock_count > 0


@dataclass(frozen=True)
class CutPatternUsage:
    stock_count: int
    counts_by_length: tuple[tuple[int, int], ...]
    cuts: tuple[int, ...]
    used_length: int
    waste: int
    summary: str


@dataclass(frozen=True)
class MultiCutPlanResult:
    standard_length: int
    requests: tuple[CutRequest, ...]
    pattern_usages: tuple[CutPatternUsage, ...]
    total_stock_count: int
    total_waste: int
    total_cut_pieces: int
    total_requested_pieces: int
    total_used_length: int
    waste_ratio: float
    single_request_summary: SingleCutPlanResult | None = None

    @property
    def is_single_request(self):
        return len(self.requests) == 1


def _validate_requests(*, standard_length: int, requests: list[CutRequest]) -> list[CutRequest]:
    if standard_length <= 0:
        raise ValueError("Standart boy 0'dan buyuk olmali.")
    if not requests:
        raise ValueError("En az bir kesim talebi girilmelidir.")

    aggregated_quantities = {}

    for request in requests:
        if request.cut_length <= 0:
            raise ValueError("Kesim boyu 0'dan buyuk olmali.")
        if request.requested_quantity <= 0:
            raise ValueError("Istenen adet 0'dan buyuk olmali.")
        if request.cut_length > standard_length:
            raise ValueError("Kesim boyu standart boydan buyuk olamaz.")

        aggregated_quantities[request.cut_length] = (
            aggregated_quantities.get(request.cut_length, 0) + request.requested_quantity
        )

    normalized_requests = [
        CutRequest(cut_length=cut_length, requested_quantity=requested_quantity)
        for cut_length, requested_quantity in aggregated_quantities.items()
    ]

    return sorted(normalized_requests, key=lambda item: (-item.cut_length, -item.requested_quantity))


def _build_best_pattern_for_remaining(*, standard_length: int, requests: tuple[CutRequest, ...], remaining: tuple[int, ...]):
    lengths = tuple(request.cut_length for request in requests)
    per_stock_caps = tuple(min(quantity, standard_length // length) for quantity, length in zip(remaining, lengths))

    @lru_cache(maxsize=None)
    def search(index: int, remaining_length: int):
        if index == len(lengths):
            return 0, 0, ()

        best_used = -1
        best_piece_count = -1
        best_counts = ()
        length = lengths[index]
        max_count = min(per_stock_caps[index], remaining_length // length)

        for count in range(max_count, -1, -1):
            child_used, child_piece_count, child_counts = search(index + 1, remaining_length - (count * length))
            used = (count * length) + child_used
            piece_count = count + child_piece_count
            candidate_counts = (count,) + child_counts

            if used > best_used or (used == best_used and piece_count > best_piece_count):
                best_used = used
                best_piece_count = piece_count
                best_counts = candidate_counts

        return best_used, best_piece_count, best_counts

    used_length, _piece_count, counts = search(0, standard_length)
    if not counts or not any(counts):
        raise ValueError("Girilen kesim taleplerinden uygulanabilir desen uretilemedi.")
    return counts, used_length


def _build_pattern_usage(*, counts: tuple[int, ...], requests: tuple[CutRequest, ...], stock_count: int, standard_length: int):
    counts_by_length = tuple(
        (request.cut_length, count)
        for request, count in zip(requests, counts)
        if count > 0
    )
    cuts = tuple(
        request.cut_length
        for request, count in zip(requests, counts)
        for _ in range(count)
    )
    used_length = sum(length * count for length, count in counts_by_length)
    waste = standard_length - used_length
    summary = " + ".join(str(length) for length in cuts) + f" = {used_length} cm"

    return CutPatternUsage(
        stock_count=stock_count,
        counts_by_length=counts_by_length,
        cuts=cuts,
        used_length=used_length,
        waste=waste,
        summary=summary,
    )


def build_multi_cut_plan(*, standard_length: int, requests: list[CutRequest]) -> MultiCutPlanResult:
    normalized_requests = _validate_requests(standard_length=standard_length, requests=requests)
    remaining = [request.requested_quantity for request in normalized_requests]
    selected_patterns: dict[tuple[int, ...], int] = {}

    while any(quantity > 0 for quantity in remaining):
        counts, _used_length = _build_best_pattern_for_remaining(
            standard_length=standard_length,
            requests=tuple(normalized_requests),
            remaining=tuple(remaining),
        )
        selected_patterns[counts] = selected_patterns.get(counts, 0) + 1

        for index, count in enumerate(counts):
            if count:
                remaining[index] -= count

    pattern_usages = tuple(
        _build_pattern_usage(
            counts=counts,
            requests=tuple(normalized_requests),
            stock_count=stock_count,
            standard_length=standard_length,
        )
        for counts, stock_count in sorted(
            selected_patterns.items(),
            key=lambda item: (
                standard_length - sum(
                    request.cut_length * count
                    for request, count in zip(normalized_requests, item[0])
                ),
                -sum(item[0]),
            ),
        )
    )

    total_stock_count = sum(pattern.stock_count for pattern in pattern_usages)
    total_waste = sum(pattern.waste * pattern.stock_count for pattern in pattern_usages)
    total_cut_pieces = sum(request.requested_quantity for request in normalized_requests)
    total_used_length = sum(pattern.used_length * pattern.stock_count for pattern in pattern_usages)
    total_purchased_length = total_stock_count * standard_length
    waste_ratio = (total_waste / total_purchased_length * 100) if total_purchased_length else 0

    single_request_summary = None
    if len(normalized_requests) == 1:
        single_request_summary = build_single_cut_plan(
            standard_length=standard_length,
            cut_length=normalized_requests[0].cut_length,
            requested_quantity=normalized_requests[0].requested_quantity,
        )

    return MultiCutPlanResult(
        standard_length=standard_length,
        requests=tuple(normalized_requests),
        pattern_usages=pattern_usages,
        total_stock_count=total_stock_count,
        total_waste=total_waste,
        total_cut_pieces=total_cut_pieces,
        total_requested_pieces=total_cut_pieces,
        total_used_length=total_used_length,
        waste_ratio=round(waste_ratio, 2),
        single_request_summary=single_request_summary,
    )


def build_single_cut_plan(*, standard_length: int, cut_length: int, requested_quantity: int) -> SingleCutPlanResult:
    if standard_length <= 0:
        raise ValueError("Standart boy 0'dan buyuk olmali.")
    if cut_length <= 0:
        raise ValueError("Kesim boyu 0'dan buyuk olmali.")
    if requested_quantity <= 0:
        raise ValueError("Istenen adet 0'dan buyuk olmali.")
    if cut_length > standard_length:
        raise ValueError("Kesim boyu standart boydan buyuk olamaz.")

    pieces_per_stock = standard_length // cut_length
    if pieces_per_stock <= 0:
        raise ValueError("Bu olcuden standart boy icinden kesim yapilamaz.")

    waste_per_full_stock = standard_length - (pieces_per_stock * cut_length)
    required_stock_count = ceil(requested_quantity / pieces_per_stock)

    partial_stock_used_pieces = requested_quantity % pieces_per_stock
    partial_stock_count = 1 if partial_stock_used_pieces else 0
    full_stock_count = required_stock_count - partial_stock_count

    if partial_stock_count:
        partial_stock_waste = standard_length - (partial_stock_used_pieces * cut_length)
    else:
        partial_stock_waste = waste_per_full_stock

    total_waste = (full_stock_count * waste_per_full_stock) + (
        partial_stock_waste if partial_stock_count else 0
    )
    total_produced_pieces = requested_quantity
    overproduced_pieces = max((required_stock_count * pieces_per_stock) - requested_quantity, 0)

    return SingleCutPlanResult(
        standard_length=standard_length,
        cut_length=cut_length,
        requested_quantity=requested_quantity,
        pieces_per_stock=pieces_per_stock,
        waste_per_full_stock=waste_per_full_stock,
        required_stock_count=required_stock_count,
        full_stock_count=full_stock_count,
        partial_stock_count=partial_stock_count,
        partial_stock_used_pieces=partial_stock_used_pieces,
        partial_stock_waste=partial_stock_waste,
        total_waste=total_waste,
        total_produced_pieces=total_produced_pieces,
        overproduced_pieces=overproduced_pieces,
    )
