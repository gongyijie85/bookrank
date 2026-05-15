import pytest

from app.models.schemas import SearchHistory, UserCategory, UserPreference, UserViewedBook
from app.services.user_service import UserService


@pytest.fixture
def user_service():
    return UserService()


@pytest.fixture
def session_id():
    return 'test-session-123'


class TestUserServiceSaveCategories:
    def test_save_categories_creates_new(self, app, db, user_service, session_id):
        user_service.save_user_categories(session_id, ['hardcover-fiction', 'hardcover-nonfiction'])
        categories = UserCategory.query.filter_by(session_id=session_id).all()
        assert len(categories) == 2
        assert categories[0].category_id == 'hardcover-fiction'

    def test_save_categories_replaces_existing(self, app, db, user_service, session_id):
        user_service.save_user_categories(session_id, ['hardcover-fiction'])
        user_service.save_user_categories(session_id, ['hardcover-nonfiction'])
        categories = UserCategory.query.filter_by(session_id=session_id).all()
        assert len(categories) == 1
        assert categories[0].category_id == 'hardcover-nonfiction'

    def test_save_categories_empty_list(self, app, db, user_service, session_id):
        user_service.save_user_categories(session_id, [])
        categories = UserCategory.query.filter_by(session_id=session_id).all()
        assert len(categories) == 0


class TestUserServiceSaveViewedBooks:
    def test_save_viewed_books(self, app, db, user_service, session_id):
        user_service.save_viewed_books(session_id, ['9780143127550', '9780062796200'])
        viewed = UserViewedBook.query.filter_by(session_id=session_id).all()
        assert len(viewed) == 2

    def test_save_viewed_books_dedup(self, app, db, user_service, session_id):
        user_service.save_viewed_books(session_id, ['9780143127550'])
        user_service.save_viewed_books(session_id, ['9780143127550', '9780062796200'])
        viewed = UserViewedBook.query.filter_by(session_id=session_id).all()
        assert len(viewed) == 2


class TestUserServiceSearchHistory:
    def test_save_search_history(self, app, db, user_service, session_id):
        user_service.save_search_history(session_id, 'python', 10)
        history = SearchHistory.query.filter_by(session_id=session_id).first()
        assert history is not None
        assert history.keyword == 'python'
        assert history.result_count == 10

    def test_get_search_history(self, app, db, user_service, session_id):
        user_service.save_search_history(session_id, 'python', 10)
        user_service.save_search_history(session_id, 'flask', 5)
        history = user_service.get_search_history(session_id, limit=5)
        assert len(history) == 2
        assert history[0]['keyword'] in ('python', 'flask')

    def test_get_search_history_limit(self, app, db, user_service, session_id):
        for i in range(10):
            user_service.save_search_history(session_id, f'keyword{i}', i)
        history = user_service.get_search_history(session_id, limit=3)
        assert len(history) <= 3


class TestUserServicePreferences:
    def test_get_preferences_no_data(self, app, db, user_service, session_id):
        prefs = user_service.get_preferences(session_id)
        assert prefs is not None

    def test_get_preferences_with_data(self, app, db, user_service, session_id):
        pref = UserPreference(session_id=session_id, view_mode='grid')
        db.session.add(pref)
        db.session.commit()
        prefs = user_service.get_preferences(session_id)
        assert prefs['view_mode'] == 'grid'
