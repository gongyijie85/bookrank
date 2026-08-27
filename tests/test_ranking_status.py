from app.utils.ranking import classify_listing


def test_first_appearance_is_new_listing():
    status = classify_listing(rank_last_week='0', weeks_on_list=1)

    assert status.is_new is True
    assert status.is_returning is False
    assert status.previous_rank == 0


def test_book_with_prior_appearances_is_returning_not_new():
    status = classify_listing(rank_last_week='0', weeks_on_list=84)

    assert status.is_new is False
    assert status.is_returning is True


def test_ranked_last_issue_is_neither_new_nor_returning():
    status = classify_listing(rank_last_week='7', weeks_on_list=12)

    assert status.is_new is False
    assert status.is_returning is False
    assert status.previous_rank == 7


def test_unknown_zero_weeks_is_not_promoted_to_new():
    status = classify_listing(rank_last_week=None, weeks_on_list=0)

    assert status.is_new is False
    assert status.is_returning is False
