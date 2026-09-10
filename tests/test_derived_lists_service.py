"""派生榜单服务测试：跨榜现象级 / 长销常青榜 / 厂牌榜 / 遗珠榜"""

from app.services.derived_lists_service import (
    COVER_PLACEHOLDER,
    build_cross_list_entries,
    build_longevity_entries,
    build_overlooked_entries,
    build_publisher_entries,
    normalize_publisher,
)
from app.utils.book_keys import book_match_key, normalize_text


def _book(title: str, author: str, **overrides):
    data = {
        'title': title,
        'author': author,
        'publisher': 'Test Publisher',
        'rank': 1,
        'weeks_on_list': 1,
        'isbn13': '',
        'isbn10': '',
        'cover': '',
        'title_zh': '',
        'category_name': '',
    }
    data.update(overrides)
    return data


def _award(title: str, author: str, **overrides):
    data = {
        'id': 1,
        'title': title,
        'author': author,
        'title_zh': '',
        'publisher': 'Test Publisher',
        'isbn13': '',
        'year': 2026,
        'category': '小说',
        'award_name': '布克奖',
        'award_name_en': 'Booker Prize',
        'cover_local_path': '',
        'cover_original_url': '',
    }
    data.update(overrides)
    return data


class TestNormalizeText:
    def test_lowercases_and_strips_punctuation(self):
        assert normalize_text("Don't Shoot the Dog!") == 'dont shoot the dog'

    def test_apostrophe_spelling_variants_share_a_key(self):
        assert normalize_text("The Handmaid's Tale") == normalize_text('Handmaids Tale')

    def test_strips_dijuacritics(self):
        assert normalize_text('László Krasznahorkai') == 'laszlo krasznahorkai'

    def test_drops_leading_article(self):
        assert normalize_text('The Tainted Cup') == 'tainted cup'
        assert normalize_text('A New Earth') == 'new earth'

    def test_keeps_cjk(self):
        assert normalize_text('撒旦探戈') == '撒旦探戈'

    def test_empty(self):
        assert normalize_text('') == ''
        assert normalize_text(None) == ''

    def test_match_key_needs_title(self):
        assert book_match_key('', 'Author') == ''
        assert book_match_key('Title', '') == 'title|'


class TestCrossListEntries:
    def test_matches_across_categories_even_with_different_isbn(self):
        """NYT 精装/平装用不同 ISBN，跨榜匹配必须按书名+作者。"""
        books_by_category = {
            'hardcover-fiction': [
                _book(
                    'My Friends',
                    'Fredrik Backman',
                    isbn13='9781510783408',
                    rank=3,
                    weeks_on_list=4,
                    category_name='精装小说',
                )
            ],
            'trade-fiction-paperback': [
                _book(
                    'My Friends',
                    'Fredrik Backman',
                    isbn13='9781443462229',
                    rank=1,
                    weeks_on_list=6,
                    category_name='平装小说',
                )
            ],
        }

        entries = build_cross_list_entries(books_by_category)

        assert len(entries) == 1
        entry = entries[0]
        assert entry.category_count == 2
        assert entry.best_rank == 1
        assert entry.total_weeks == 10
        assert [listing['category_id'] for listing in entry.listings] == [
            'trade-fiction-paperback',
            'hardcover-fiction',
        ]

    def test_deduplicates_editions_within_one_category(self):
        books_by_category = {
            'hardcover-fiction': [
                _book('Flesh', 'David Szalay', rank=9),
                _book('Flesh', 'David Szalay', rank=2),
            ],
            'business-books': [_book('Flesh', 'David Szalay', rank=5, category_name='商业')],
        }

        entries = build_cross_list_entries(books_by_category)

        assert len(entries) == 1
        assert entries[0].category_count == 2
        hardcover = next(item for item in entries[0].listings if item['category_id'] == 'hardcover-fiction')
        assert hardcover['rank'] == 2

    def test_single_category_book_is_excluded(self):
        books_by_category = {'hardcover-fiction': [_book('Solo', 'Author')]}
        assert build_cross_list_entries(books_by_category) == []

    def test_min_categories_is_configurable(self):
        books_by_category = {
            'hardcover-fiction': [_book('Trio', 'Author')],
            'business-books': [_book('Trio', 'Author')],
            'picture-books': [_book('Trio', 'Author')],
        }

        assert len(build_cross_list_entries(books_by_category)) == 1
        assert len(build_cross_list_entries(books_by_category, min_categories=3)) == 1
        assert build_cross_list_entries(books_by_category, min_categories=4) == []

    def test_sorted_by_category_count_then_best_rank(self):
        books_by_category = {
            'hardcover-fiction': [
                _book('Two Lists', 'A', rank=1),
                _book('Three Lists', 'B', rank=20),
            ],
            'business-books': [
                _book('Two Lists', 'A', rank=2),
                _book('Three Lists', 'B', rank=4),
            ],
            'picture-books': [_book('Three Lists', 'B', rank=6)],
        }

        entries = build_cross_list_entries(books_by_category)

        assert [entry.title for entry in entries] == ['Three Lists', 'Two Lists']

    def test_ignores_books_without_title(self):
        books_by_category = {
            'hardcover-fiction': [_book('', 'Ghost Author'), _book('Real', 'Author')],
            'business-books': [_book('', 'Ghost Author'), _book('Real', 'Author')],
        }

        entries = build_cross_list_entries(books_by_category)

        assert [entry.title for entry in entries] == ['Real']

    def test_placeholder_cover_falls_back_to_original_url(self):
        books_by_category = {
            'hardcover-fiction': [
                _book('Covered', 'A', cover=COVER_PLACEHOLDER, _original_cover='https://static01.nyt.com/x.jpg')
            ],
            'business-books': [_book('Covered', 'A', cover='https://other/y.jpg')],
        }

        assert build_cross_list_entries(books_by_category)[0].cover == 'https://static01.nyt.com/x.jpg'

    def test_cover_backfilled_from_later_category(self):
        books_by_category = {
            'hardcover-fiction': [_book('Late Cover', 'A', cover=COVER_PLACEHOLDER)],
            'business-books': [_book('Late Cover', 'A', cover='/cache/images/z.jpg')],
        }

        assert build_cross_list_entries(books_by_category)[0].cover == '/cache/images/z.jpg'


class TestLongevityEntries:
    def test_includes_books_on_a_single_category_list(self):
        books_by_category = {
            'hardcover-fiction': [_book('One List Only', 'A', weeks_on_list=30)],
        }

        entries = build_longevity_entries(books_by_category, limit=None)

        assert [entry.title for entry in entries] == ['One List Only']
        assert entries[0].total_weeks == 30

    def test_sorts_by_total_weeks_across_lists(self):
        books_by_category = {
            'hardcover-fiction': [
                _book('Steady', 'A', weeks_on_list=20),
                _book('Split', 'B', weeks_on_list=12),
            ],
            'business-books': [_book('Split', 'B', weeks_on_list=12)],
        }

        entries = build_longevity_entries(books_by_category, limit=None)

        assert [(entry.title, entry.total_weeks) for entry in entries] == [('Split', 24), ('Steady', 20)]

    def test_drops_books_with_unknown_weeks(self):
        books_by_category = {
            'hardcover-fiction': [_book('Fresh', 'A', weeks_on_list=0)],
            'business-books': [_book('Proven', 'B', weeks_on_list=5)],
        }

        assert [entry.title for entry in build_longevity_entries(books_by_category, limit=None)] == ['Proven']

    def test_limit_caps_entries(self):
        books_by_category = {
            'hardcover-fiction': [
                _book('Long', 'A', weeks_on_list=40),
                _book('Short', 'B', weeks_on_list=4),
            ],
        }

        assert [entry.title for entry in build_longevity_entries(books_by_category, limit=1)] == ['Long']


class TestNormalizePublisher:
    def test_strips_trailing_parenthetical(self):
        assert normalize_publisher('Penguin Random House (Hybrid)') == 'Penguin Random House'

    def test_groups_big_five_by_containment(self):
        assert normalize_publisher('Pan Macmillan') == 'Macmillan'
        assert normalize_publisher('HarperCollins') == 'HarperCollins'
        assert normalize_publisher('Simon & Schuster') == 'Simon & Schuster'
        assert normalize_publisher('Hachette Book Group') == 'Hachette'

    def test_does_not_guess_imprint_ownership(self):
        assert normalize_publisher('Scribner') == 'Scribner'
        assert normalize_publisher('Grove Atlantic') == 'Grove Atlantic'

    def test_unknown_publishers_are_dropped(self):
        assert normalize_publisher('Unknown') == ''
        assert normalize_publisher('Unknown Publisher') == ''
        assert normalize_publisher('') == ''
        assert normalize_publisher(None) == ''


class TestPublisherEntries:
    def test_counts_distinct_books_and_categories(self):
        books_by_category = {
            'hardcover-fiction': [
                _book('Alpha', 'A', publisher='Knopf'),
                _book('Beta', 'B', publisher='Knopf', rank=4),
            ],
            'business-books': [_book('Gamma', 'C', publisher='Knopf', rank=2)],
        }

        entries = build_publisher_entries(books_by_category)

        assert len(entries) == 1
        assert entries[0].name == 'Knopf'
        assert entries[0].book_count == 3
        assert entries[0].category_count == 2
        assert entries[0].best_rank == 1

    def test_skips_unknown_publisher(self):
        books_by_category = {'hardcover-fiction': [_book('Alpha', 'A', publisher='Unknown')]}
        assert build_publisher_entries(books_by_category) == []

    def test_sorted_by_book_count_then_best_rank(self):
        books_by_category = {
            'hardcover-fiction': [
                _book('Small A', 'A', publisher='Small Press', rank=1),
                _book('Big A', 'B', publisher='Big Press', rank=5),
                _book('Big B', 'C', publisher='Big Press', rank=6),
            ],
        }

        entries = build_publisher_entries(books_by_category)

        assert [entry.name for entry in entries] == ['Big Press', 'Small Press']

    def test_books_sorted_by_rank_and_limited(self):
        books_by_category = {
            'hardcover-fiction': [
                _book('Third', 'C', publisher='Press', rank=9),
                _book('First', 'A', publisher='Press', rank=1),
                _book('Second', 'B', publisher='Press', rank=4),
            ],
        }

        entry = build_publisher_entries(books_by_category)[0]

        assert [book['title'] for book in entry.books] == ['First', 'Second', 'Third']

    def test_limit_caps_entries(self):
        books_by_category = {
            'hardcover-fiction': [
                _book('One', 'A', publisher='Press One'),
                _book('Two', 'B', publisher='Press Two'),
            ],
        }

        assert len(build_publisher_entries(books_by_category, limit=1)) == 1


class TestOverlookedEntries:
    def test_excludes_books_currently_on_any_list(self):
        """获奖书与在榜书 ISBN 常不同，必须按书名+作者排除。"""
        books_by_category = {
            'hardcover-fiction': [_book('James', 'Percival Everett', isbn13='9780385550369')],
        }
        award_books = [_award('James', 'Percival Everett', isbn13='9781447257989')]

        assert build_overlooked_entries(award_books, books_by_category) == []

    def test_keeps_award_winner_that_is_not_listed(self):
        award_books = [_award('Satantango', 'László Krasznahorkai', title_zh='撒旦探戈')]

        entries = build_overlooked_entries(award_books, {})

        assert len(entries) == 1
        assert entries[0].title_zh == '撒旦探戈'
        assert entries[0].award_count == 1
        assert entries[0].awards[0]['award_name_en'] == 'Booker Prize'

    def test_groups_multiple_awards_for_one_book(self):
        award_books = [
            _award('The Body', 'Author', award_name='布克奖', award_name_en='Booker Prize', year=2025, category='小说'),
            _award(
                'The Body', 'Author', award_name='普利策奖', award_name_en='Pulitzer Prize', year=2026, category='小说'
            ),
        ]

        entries = build_overlooked_entries(award_books, {})

        assert len(entries) == 1
        assert entries[0].award_count == 2
        assert entries[0].latest_year == 2026
        assert [award['award_name_en'] for award in entries[0].awards] == ['Pulitzer Prize', 'Booker Prize']

    def test_sorted_by_year_then_award_count(self):
        award_books = [
            _award('Old Winner', 'A', year=2024),
            _award('New Winner', 'B', year=2026),
            _award('Popular Winner', 'C', year=2025),
            _award('Popular Winner', 'C', year=2025, award_name='国家图书奖', award_name_en='NBA'),
        ]

        entries = build_overlooked_entries(award_books, {})

        assert [entry.title for entry in entries] == ['New Winner', 'Popular Winner', 'Old Winner']

    def test_skips_records_without_title(self):
        assert build_overlooked_entries([_award('', 'Author')], {}) == []
