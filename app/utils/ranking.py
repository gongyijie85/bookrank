from dataclasses import dataclass
from typing import Any

_NO_PREVIOUS_RANK = {'', '0', 'none', '无'}


@dataclass(frozen=True)
class ListingStatus:
    previous_rank: int | None
    is_new: bool
    is_returning: bool


def classify_listing(rank_last_week: Any, weeks_on_list: Any) -> ListingStatus:
    """Classify a list appearance without conflating a return with a debut."""
    raw_previous_rank = str(rank_last_week or '').strip().lower()
    if raw_previous_rank in _NO_PREVIOUS_RANK:
        previous_rank: int | None = 0
    else:
        try:
            previous_rank = int(raw_previous_rank)
        except (TypeError, ValueError):
            previous_rank = None

    try:
        cumulative_weeks = max(0, int(weeks_on_list or 0))
    except (TypeError, ValueError):
        cumulative_weeks = 0

    has_no_previous_rank = previous_rank == 0
    return ListingStatus(
        previous_rank=previous_rank,
        is_new=has_no_previous_rank and cumulative_weeks == 1,
        is_returning=has_no_previous_rank and cumulative_weeks > 1,
    )
