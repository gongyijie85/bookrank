"""推荐服务测试"""

from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import AwardBook
from app.services.recommendation_service import RecommendationService


@pytest.fixture
def rec_service():
    return RecommendationService(categories={'fiction': '小说', 'nonfiction': '非虚构'})


@pytest.fixture
def sample_books(app, db):
    with app.app_context():
        books = [
            AwardBook(
                award_id=1,
                year=2024,
                category='fiction',
                rank=1,
                title='The Great Novel',
                author='Jane Author',
                isbn13='9780000000001',
                is_displayable=True,
                cover_original_url='https://example.com/cover1.jpg',
            ),
            AwardBook(
                award_id=1,
                year=2023,
                category='nonfiction',
                rank=2,
                title='Amazing Science',
                author='John Scientist',
                isbn13='9780000000002',
                is_displayable=True,
                cover_original_url='https://example.com/cover2.jpg',
            ),
            AwardBook(
                award_id=2,
                year=2024,
                category='fiction',
                rank=3,
                title='Another Story',
                author='Jane Author',
                isbn13='9780000000003',
                is_displayable=True,
            ),
        ]
        for b in books:
            db.session.add(b)
        db.session.commit()
        return [b.id for b in books]


class TestExtractKeywords:
    """测试 _extract_keywords"""

    def test_normal_text(self, rec_service):
        result = rec_service._extract_keywords('The Great Gatsby Novel')
        assert 'great' in result
        assert 'gatsby' in result
        assert 'novel' in result

    def test_empty_text(self, rec_service):
        assert rec_service._extract_keywords('') == []

    def test_stop_words_filtered(self, rec_service):
        result = rec_service._extract_keywords('The Cat and the Dog')
        assert 'the' not in result
        assert 'and' not in result
        assert 'cat' in result
        assert 'dog' in result

    def test_short_words_filtered(self, rec_service):
        result = rec_service._extract_keywords('I Am A Go')
        assert result == []

    def test_mixed_filters(self, rec_service):
        result = rec_service._extract_keywords('A Story Of Love and War')
        assert 'story' in result
        assert 'love' in result
        assert 'war' in result
        assert 'the' not in result
        assert 'a' not in result
        assert 'of' not in result


class TestGenerateRecommendationReason:
    """测试 _generate_recommendation_reason"""

    def test_with_authors(self, rec_service):
        interests = {'authors': ['Author A', 'Author B'], 'categories': []}
        reason = rec_service._generate_recommendation_reason(interests)
        assert 'Author A' in reason
        assert 'Author B' in reason
        assert '关注了作者' in reason

    def test_with_categories(self, rec_service):
        interests = {'authors': [], 'categories': ['fiction']}
        reason = rec_service._generate_recommendation_reason(interests)
        assert '小说' in reason
        assert '兴趣' in reason

    def test_with_both(self, rec_service):
        interests = {'authors': ['Author A'], 'categories': ['fiction']}
        reason = rec_service._generate_recommendation_reason(interests)
        assert 'Author A' in reason
        assert '小说' in reason
        assert '，' in reason

    def test_with_neither(self, rec_service):
        interests = {'authors': [], 'categories': []}
        reason = rec_service._generate_recommendation_reason(interests)
        assert reason == '根据热门获奖图书推荐'


class TestGetSmartRecommendations:
    """测试 get_smart_recommendations"""

    def test_with_session_id(self, app, db, rec_service, sample_books):
        with app.app_context(), patch.object(rec_service, 'get_personalized_recommendations') as mock_p:
            mock_p.return_value = {
                'recommendations': [{'id': 1}],
                'reason': 'test',
                'based_on': 'personalized',
            }
            result = rec_service.get_smart_recommendations(session_id='test')
            assert result['strategy'] == 'hybrid'
            mock_p.assert_called_once_with('test', 10)

    def test_without_session_id(self, app, db, rec_service, sample_books):
        with app.app_context():
            result = rec_service.get_smart_recommendations()
            assert result['strategy'] == 'popular_fallback'
            assert result['based_on'] == 'popular'

    def test_limit_max_clamp(self, rec_service):
        with patch.object(rec_service, '_get_popular_recommendations') as mock_pop:
            mock_pop.return_value = {'recommendations': [], 'reason': '', 'based_on': 'popular'}
            rec_service.get_smart_recommendations(limit=100)
            assert mock_pop.call_args[0][0] == 50

    def test_limit_min_clamp(self, rec_service):
        with patch.object(rec_service, '_get_popular_recommendations') as mock_pop:
            mock_pop.return_value = {'recommendations': [], 'reason': '', 'based_on': 'popular'}
            rec_service.get_smart_recommendations(limit=-5)
            assert mock_pop.call_args[0][0] == 1

    def test_session_with_empty_personalized_falls_back(self, app, db, rec_service, sample_books):
        with app.app_context(), patch.object(rec_service, 'get_personalized_recommendations') as mock_p:
            mock_p.return_value = {'recommendations': [], 'reason': '', 'based_on': 'personalized'}
            result = rec_service.get_smart_recommendations(session_id='test')
            assert result['strategy'] == 'popular_fallback'


class TestGetSimilarityRecommendations:
    """测试 get_similarity_recommendations"""

    def test_by_book_id(self, app, db, rec_service, sample_books):
        with app.app_context():
            result = rec_service.get_similarity_recommendations(book_id=sample_books[0])
            assert 'recommendations' in result
            assert result['based_on'] == 'similarity'
            assert 'reference_book' in result

    def test_by_isbn(self, app, db, rec_service, sample_books):
        with app.app_context():
            result = rec_service.get_similarity_recommendations(isbn='9780000000001')
            assert 'recommendations' in result
            assert result['based_on'] == 'similarity'

    def test_by_award_id(self, app, db, rec_service, sample_books):
        with app.app_context():
            result = rec_service.get_similarity_recommendations(award_id=1)
            assert 'recommendations' in result
            assert result['based_on'] == 'award_similarity'

    def test_by_category(self, app, db, rec_service, sample_books):
        with app.app_context():
            result = rec_service.get_similarity_recommendations(category='fiction')
            assert 'recommendations' in result
            assert result['based_on'] == 'category'

    def test_no_params_returns_popular(self, app, db, rec_service, sample_books):
        with app.app_context():
            result = rec_service.get_similarity_recommendations()
            assert result['based_on'] == 'popular'


class TestGetPersonalizedRecommendations:
    """测试 get_personalized_recommendations"""

    @patch.object(RecommendationService, '_get_viewed_books', return_value=[])
    def test_no_history_returns_popular(self, mock_viewed, app, db, rec_service, sample_books):
        with app.app_context():
            result = rec_service.get_personalized_recommendations('test-session')
            assert result['based_on'] == 'popular'

    @patch.object(RecommendationService, '_get_viewed_books')
    @patch.object(RecommendationService, '_analyze_user_interests')
    @patch.object(RecommendationService, '_recommend_by_interests')
    def test_with_history(self, mock_rec, mock_interests, mock_viewed, app, db, rec_service):
        mock_viewed.return_value = [MagicMock(isbn='9780000000001')]
        mock_interests.return_value = {'authors': ['Jane Author'], 'keywords': [], 'categories': []}
        mock_rec.return_value = [{'id': 1, 'title': 'Book', 'type': 'award_book'}]

        with app.app_context():
            result = rec_service.get_personalized_recommendations('test-session')
            assert result['based_on'] == 'personalized'
            assert result['recommendations'][0]['id'] == 1
            mock_rec.assert_called_once()

    @patch.object(RecommendationService, '_get_viewed_books')
    @patch.object(RecommendationService, '_analyze_user_interests')
    @patch.object(RecommendationService, '_recommend_by_interests', return_value=[])
    def test_insufficient_results_fills_with_popular(
        self, mock_rec, mock_interests, mock_viewed, app, db, rec_service, sample_books
    ):
        mock_viewed.return_value = [MagicMock(isbn='9780000000001')]
        mock_interests.return_value = {'authors': [], 'keywords': [], 'categories': []}

        with app.app_context():
            result = rec_service.get_personalized_recommendations('test-session', limit=5)
            assert 'recommendations' in result
            assert result['based_on'] == 'personalized'


class TestFormatAwardBook:
    """测试 _format_award_book"""

    def test_format(self, app, db, rec_service, sample_books):
        with app.app_context():
            book = db.session.get(AwardBook, sample_books[0])
            result = rec_service._format_award_book(book)
            assert result['type'] == 'award_book'
            assert result['title'] == 'The Great Novel'
            assert result['author'] == 'Jane Author'
            assert result['isbn13'] == '9780000000001'
            assert 'reason' in result

    def test_format_with_no_category(self, app, db, rec_service):
        with app.app_context():
            book = AwardBook(
                award_id=1,
                year=2024,
                category=None,
                rank=1,
                title='No Category Book',
                author='Author',
                isbn13='9780000000099',
                is_displayable=True,
            )
            db.session.add(book)
            db.session.commit()
            result = rec_service._format_award_book(book)
            assert '获奖作品' in result['reason']


class TestGetPopularRecommendations:
    """测试 _get_popular_recommendations"""

    def test_with_data(self, app, db, rec_service, sample_books):
        with app.app_context():
            result = rec_service._get_popular_recommendations(limit=5)
            assert 'recommendations' in result
            assert result['based_on'] == 'popular'
            assert len(result['recommendations']) >= 1

    def test_empty_db(self, app, db, rec_service):
        with app.app_context():
            result = rec_service._get_popular_recommendations(limit=5)
            assert result['recommendations'] == []


def test_similar_whole_author_then_award_then_other(app, db, rec_service):
    from app.models.schemas import Award

    with app.app_context():
        award_a, award_b = Award(name='Award A'), Award(name='Award B')
        db.session.add_all([award_a, award_b])
        db.session.flush()
        target = AwardBook(
            award_id=award_a.id,
            year=2026,
            category='Fiction',
            rank=1,
            title='Target',
            author='Ada Author',
            isbn13='9780000000100',
            is_displayable=True,
        )
        older = AwardBook(
            award_id=award_b.id,
            year=2010,
            category='Poetry',
            rank=1,
            title='Older',
            author=' ada author ',
            isbn13='9780000000101',
            is_displayable=True,
        )
        same = AwardBook(
            award_id=award_a.id,
            year=2026,
            category='Essay',
            rank=2,
            title='SameAw',
            author='Else',
            isbn13='9780000000102',
            is_displayable=True,
        )
        near = AwardBook(
            award_id=award_b.id,
            year=2027,
            category='Fiction',
            rank=1,
            title='Near',
            author='Other',
            isbn13='9780000000103',
            is_displayable=True,
        )
        hidden = AwardBook(
            award_id=award_a.id,
            year=2028,
            category='Fiction',
            rank=1,
            title='Hidden',
            author='Ada Author',
            isbn13='9780000000104',
            is_displayable=False,
        )
        partial = AwardBook(
            award_id=award_b.id,
            year=1999,
            category='Zed',
            rank=1,
            title='Part',
            author='Ada',
            isbn13='9780000000107',
            is_displayable=True,
        )
        db.session.add_all([target, older, same, near, hidden, partial])
        db.session.commit()
        top = rec_service._recommend_similar_books(target, 2)['recommendations']
        assert [r['id'] for r in top] == [older.id, same.id]
        assert [r['related_reason'] for r in top] == ['same_author', 'same_award']
        env = rec_service._recommend_similar_books(target, 3)
        three = env['recommendations']
        assert [r['id'] for r in three] == [older.id, same.id, near.id]
        assert [r['related_reason'] for r in three] == ['same_author', 'same_award', 'other_award']
        assert (three[0]['author'], three[0]['year'], three[0]['category'], three[0]['title']) == (
            ' ada author ',
            2010,
            'Poetry',
            'Older',
        )
        assert (three[2]['title'], three[2]['author'], three[2]['year'], three[2]['category']) == (
            'Near',
            'Other',
            2027,
            'Fiction',
        )
        assert three[0]['type'] == 'award_book' and three[0]['id'] == older.id and 'reason' in three[0]
        got = {r['id'] for r in three}
        assert len(got) == 3 and target.id not in got and hidden.id not in got and partial.id not in got
        assert env['based_on'] == 'similarity' and env['reference_book'] == {
            'id': target.id,
            'title': target.title,
            'author': target.author,
        }
        blank = AwardBook(
            award_id=award_a.id,
            year=2026,
            category='Fiction',
            rank=8,
            title='Blank',
            author='  ',
            isbn13='9780000000105',
            is_displayable=True,
        )
        spaces = AwardBook(
            award_id=award_b.id,
            year=1990,
            category='Nope',
            rank=1,
            title='Spaces',
            author='',
            isbn13='9780000000106',
            is_displayable=True,
        )
        db.session.add_all([blank, spaces])
        db.session.commit()
        blank_recs = rec_service._recommend_similar_books(blank, 10)['recommendations']
        assert blank_recs and all(r['related_reason'] != 'same_author' for r in blank_recs)


@pytest.mark.parametrize('pad', [2, 20])
def test_similar_candidate_select_is_one(app, db, rec_service, pad):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    from app.models.schemas import Award

    with app.app_context():
        award_a, award_b = Award(name=f'Pad A {pad}'), Award(name=f'Pad B {pad}')
        db.session.add_all([award_a, award_b])
        db.session.flush()
        target = AwardBook(
            award_id=award_a.id,
            year=2026,
            category='Fiction',
            rank=1,
            title='T',
            author='Ada Author',
            isbn13=f'97800000002{pad:02d}',
            is_displayable=True,
        )
        pads = [
            AwardBook(
                award_id=award_b.id,
                year=1900,
                category=f'C{pad}_{i}',
                rank=1,
                title=f'P{i}',
                author=f'Author{pad}_{i}',
                isbn13=f'978{pad:02d}0000{i:04d}',
                is_displayable=True,
            )
            for i in range(pad)
        ]
        db.session.add_all([target, *pads])
        db.session.commit()
        _ = (target.id, target.award_id, target.author, target.category, target.year, target.title)
        seen = []

        def heard(conn, cursor, statement, parameters, context, executemany):
            return seen.append(1) if statement.lstrip()[:6].upper() == 'SELECT' else None

        event.listen(Engine, 'before_cursor_execute', heard)
        try:
            rec_service._recommend_similar_books(target, 5)
        finally:
            event.remove(Engine, 'before_cursor_execute', heard)
        assert len(seen) == 1


@pytest.mark.parametrize('candidate_count', [2, 20])
@pytest.mark.parametrize('limit', [1, 3])
def test_recommend_similar_books_isbn_representative_and_one_select(app, db, rec_service, candidate_count, limit):
    """同 ISBN 只留最高优先级代表，理由顺序稳定，且只发一条 SELECT。"""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    from app.models.schemas import Award

    with app.app_context():
        award_a = Award(name=f'Similar A {candidate_count} {limit}')
        award_b = Award(name=f'Similar B {candidate_count} {limit}')
        db.session.add_all([award_a, award_b])
        db.session.flush()
        target = AwardBook(
            award_id=award_a.id,
            year=2026,
            category='Fiction',
            rank=1,
            title='Target Book',
            author='Ada Author',
            isbn13='9780000000099',
            isbn10='0000000099',
            is_displayable=True,
        )
        excluded_same_isbn13 = AwardBook(
            award_id=award_b.id,
            year=2025,
            category='Fiction',
            rank=1,
            title='Same Isbn Other Award',
            author='Ada Author',
            isbn13='9780000000099',
            isbn10='1111111111',
            is_displayable=True,
        )
        excluded_same_isbn10 = AwardBook(
            award_id=award_b.id,
            year=2025,
            category='Fiction',
            rank=1,
            title='Same Isbn10 Only',
            author='Ada Author',
            isbn13='9782222222222',
            isbn10='0000000099',
            is_displayable=True,
        )
        newer_other_dup = AwardBook(
            award_id=award_b.id,
            year=2024,
            category='Fiction',
            rank=1,
            title='Newer Other Award Dup',
            author='Zed Zebra',
            isbn13='9781111111111',
            isbn10='2222222222',
            is_displayable=True,
        )
        oldest_author = AwardBook(
            award_id=award_b.id,
            year=1991,
            category='Fiction',
            rank=9,
            title='Oldest Author Match',
            author='Ada Author',
            isbn13='9781111111111',
            isbn10='3333333333',
            is_displayable=True,
        )
        same_award = AwardBook(
            award_id=award_a.id,
            year=2010,
            category='Fiction',
            rank=2,
            title='Same Award Distinct',
            author='Bea Other',
            isbn13='9783333333333',
            isbn10='4444444444',
            is_displayable=True,
        )
        other_award = AwardBook(
            award_id=award_b.id,
            year=2001,
            category='Fiction',
            rank=1,
            title='Other Award Distinct',
            author='Cara Third',
            isbn13='9784444444444',
            isbn10='5555555555',
            is_displayable=True,
        )
        pads = [
            AwardBook(
                award_id=award_b.id,
                year=1900,
                category=f'Pad{candidate_count}_{i}',
                rank=1,
                title=f'Pad {candidate_count} {limit} {i}',
                author=f'Pad Author {candidate_count} {i}',
                isbn13=f'979{limit}{candidate_count:02d}{i:07d}',
                is_displayable=True,
            )
            for i in range(candidate_count)
        ]
        db.session.add_all(
            [
                target,
                excluded_same_isbn13,
                excluded_same_isbn10,
                newer_other_dup,
                oldest_author,
                same_award,
                other_award,
                *pads,
            ]
        )
        db.session.commit()
        _ = (
            target.id,
            target.award_id,
            target.author,
            target.category,
            target.year,
            target.rank,
            target.title,
            target.isbn13,
            target.isbn10,
            target.is_displayable,
        )
        expected = [
            ('Oldest Author Match', 'same_author'),
            ('Same Award Distinct', 'same_award'),
            ('Other Award Distinct', 'other_award'),
        ][:limit]
        seen = []

        def heard(conn, cursor, statement, parameters, context, executemany):
            return seen.append(1) if statement.lstrip()[:6].upper() == 'SELECT' else None

        event.listen(Engine, 'before_cursor_execute', heard)
        try:
            result = rec_service._recommend_similar_books(target, limit)
        finally:
            event.remove(Engine, 'before_cursor_execute', heard)
        ordered = [(item['title'], item['related_reason']) for item in result['recommendations']]
        assert {'ordered': ordered, 'selects': len(seen)} == {
            'ordered': expected,
            'selects': 1,
        }
