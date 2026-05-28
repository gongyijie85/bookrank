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
