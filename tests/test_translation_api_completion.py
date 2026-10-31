"""Book translation responses describe durable results, using only fake translation."""

import pytest

ISBN = '9780143127550'


@pytest.fixture
def translation_api(app, db, client, monkeypatch):
    from app.models.schemas import BookMetadata
    from app.services.book_service import BookService

    class FakeBookService:
        _app = app
        book = {'title': 'Original title', 'description': 'Original description', 'isbn13': ISBN}
        saves = []
        save_result = True

        def get_book_by_isbn(self, isbn):
            return dict(self.book) if self.book else None

        def save_book_translation(self, **values):
            self.saves.append(values)
            if self.save_result is not True:
                if isinstance(self.save_result, Exception):
                    raise self.save_result
                return self.save_result
            return BookService.save_book_translation(self, **values)

    class FakeTranslator:
        inputs = []
        result = {'title_zh': '中文书名', 'description_zh': '中文简介'}

        def translate_book_info(self, book_data):
            self.inputs.append(book_data)
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    service = FakeBookService()
    translator = FakeTranslator()
    monkeypatch.setattr('app.routes.api.translation.get_service', lambda name: service)
    monkeypatch.setattr('app.services.zhipu_translation_service.get_translation_service', lambda: translator)

    def post():
        response = client.get('/api/csrf-token')
        token = response.get_json()['data']['csrf_token']
        return client.post(f'/api/translate/book/{ISBN}', headers={'X-CSRF-Token': token})

    return service, translator, post, BookMetadata


def test_saves_complete_result_and_duplicate_request_uses_metadata(app, db, translation_api):
    service, translator, post, model = translation_api
    response = post()
    assert response.status_code == 200
    assert response.get_json()['data']['translation_status'] == 'complete'
    with app.app_context():
        saved = db.session.get(model, ISBN)
        assert saved.title_zh == '中文书名'
        assert saved.description_zh == '中文简介'
    assert post().status_code == 200
    assert len(translator.inputs) == 1
    assert len(service.saves) == 1


def test_preserves_chinese_and_translates_only_missing_fields(app, db, translation_api):
    service, translator, post, model = translation_api
    service.book.update(title_zh='原有中文书名', details='详情原文已经是中文')
    response = post()
    assert response.status_code == 200
    assert response.get_json()['data']['book']['title_zh'] == '原有中文书名'
    assert translator.inputs[0]['title'] == ''
    assert translator.inputs[0]['details'] == ''
    assert service.saves == [{'isbn': ISBN, 'description_zh': '中文简介'}]


def test_preserves_existing_metadata_missing_from_ranking_cache(app, db, translation_api):
    service, translator, post, model = translation_api
    with app.app_context():
        db.session.add(model(isbn=ISBN, title='Original title', author='Author', title_zh='数据库已有中文'))
        db.session.commit()
    response = post()
    assert response.get_json()['data']['book']['title_zh'] == '数据库已有中文'
    assert service.saves == [{'isbn': ISBN, 'description_zh': '中文简介'}]
    assert translator.inputs[0]['title'] == ''


@pytest.mark.parametrize('result', [None, {}, {'title_zh': 'Original title'}, RuntimeError('unavailable')])
def test_no_translation_is_retryable_failure(translation_api, result):
    service, translator, post, _ = translation_api
    translator.result = result
    response = post()
    assert response.status_code == 503
    assert response.get_json()['success'] is False
    assert response.get_json()['errors']['retryable'] is True
    assert service.saves == []


@pytest.mark.parametrize('result', [False, RuntimeError('save failed')])
def test_failed_persistence_is_not_reported_as_success(translation_api, result):
    service, _, post, _ = translation_api
    service.save_result = result
    response = post()
    assert response.status_code == 503
    assert response.get_json()['success'] is False


def test_metadata_read_failure_does_not_translate_or_write(db, translation_api, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    service, translator, post, _ = translation_api

    def unavailable(*args, **kwargs):
        raise SQLAlchemyError('synthetic database read failure')

    monkeypatch.setattr(db.session, 'get', unavailable)
    response = post()
    assert response.status_code == 503
    assert translator.inputs == []
    assert service.saves == []


def _add_missing_award(app, db):
    from app.models.schemas import Award, AwardBook

    with app.app_context():
        award = Award(name='Synthetic award', country='US')
        db.session.add(award)
        db.session.flush()
        db.session.add(
            AwardBook(
                award_id=award.id,
                year=2026,
                title='Original title',
                description='Original description',
                author='Synthetic author',
                isbn13=ISBN,
            )
        )
        db.session.commit()
    return AwardBook


def test_main_and_award_missing_translations_are_both_saved(app, db, translation_api):
    _, translator, post, _ = translation_api
    award_model = _add_missing_award(app, db)
    response = post()
    assert response.status_code == 200
    assert response.get_json()['data']['translation_status'] == 'complete'
    assert len(translator.inputs) == 1
    with app.app_context():
        saved = award_model.query.filter_by(isbn13=ISBN).one()
        assert saved.title_zh == '中文书名'
        assert saved.description_zh == '中文简介'


def test_existing_main_translation_fills_missing_award_without_translation(app, db, translation_api):
    service, translator, post, model = translation_api
    award_model = _add_missing_award(app, db)
    with app.app_context():
        db.session.add(
            model(
                isbn=ISBN,
                title='Original title',
                author='Synthetic author',
                title_zh='已持久化书名',
                description_zh='已持久化简介',
            )
        )
        db.session.commit()
    response = post()
    assert response.status_code == 200
    assert response.get_json()['data']['translation_status'] == 'complete'
    assert translator.inputs == []
    assert service.saves == []
    with app.app_context():
        saved = award_model.query.filter_by(isbn13=ISBN).one()
        assert saved.title_zh == '已持久化书名'
        assert saved.description_zh == '已持久化简介'


@pytest.mark.parametrize('result', [False, RuntimeError('synthetic award write failure')])
def test_award_save_failure_returns_persisted_main_as_partial(app, db, translation_api, monkeypatch, result):
    from app.services.award_book_service import AwardBookService

    _, translator, post, model = translation_api
    award_model = _add_missing_award(app, db)

    def fail_save(*args, **kwargs):
        if isinstance(result, Exception):
            raise result
        return result

    with monkeypatch.context() as patch:
        patch.setattr(AwardBookService, 'save_award_book_translation', fail_save)
        response = post()
    assert response.status_code == 200
    payload = response.get_json()['data']
    assert payload['translation_status'] == 'partial'
    assert payload['book']['title_zh'] == '中文书名'
    with app.app_context():
        assert db.session.get(model, ISBN).title_zh == '中文书名'
        assert award_model.query.filter_by(isbn13=ISBN).one().title_zh is None
    # A later explicit request reuses the completed main save, rather than
    # repeating the translation API call after this partial persistence.
    assert post().get_json()['data']['translation_status'] == 'complete'
    assert len(translator.inputs) == 1
    with app.app_context():
        assert award_model.query.filter_by(isbn13=ISBN).one().title_zh == '中文书名'


def test_main_save_failure_does_not_write_award(app, db, translation_api):
    service, _, post, _ = translation_api
    award_model = _add_missing_award(app, db)
    service.save_result = False
    assert post().status_code == 503
    with app.app_context():
        assert award_model.query.filter_by(isbn13=ISBN).one().title_zh is None


def test_partial_translation_is_saved_and_reported(app, db, translation_api):
    _, translator, post, model = translation_api
    translator.result = {'title_zh': '只有书名译文'}
    response = post()
    assert response.status_code == 200
    assert response.get_json()['data']['translation_status'] == 'partial'
    assert response.get_json()['data']['book']['title_zh'] == '只有书名译文'
    with app.app_context():
        assert db.session.get(model, ISBN).title_zh == '只有书名译文'
        assert db.session.get(model, ISBN).description_zh is None


def test_award_only_details_are_not_translated_or_claimed_persisted(app, db, translation_api):
    from app.models.schemas import Award, AwardBook

    service, translator, post, _ = translation_api
    service.book = None
    with app.app_context():
        award = Award(name='Synthetic award', country='US')
        db.session.add(award)
        db.session.flush()
        db.session.add(
            AwardBook(
                award_id=award.id,
                year=2026,
                title='Award title',
                author='Synthetic author',
                description='Award description',
                details='Unsupported English details',
                isbn13=ISBN,
            )
        )
        db.session.commit()
    response = post()
    assert response.status_code == 200
    assert response.get_json()['data']['translation_status'] == 'partial'
    assert 'details_zh' not in response.get_json()['data']['book']
    assert translator.inputs[0]['details'] == ''
    assert service.saves == []
    with app.app_context():
        saved = AwardBook.query.filter_by(isbn13=ISBN).one()
        assert saved.title_zh == '中文书名'
        assert saved.description_zh == '中文简介'


def test_dual_store_preserves_existing_award_translation(app, db, translation_api):
    from app.models.schemas import Award, AwardBook

    _, _, post, _ = translation_api
    with app.app_context():
        award = Award(name='Synthetic award', country='US')
        db.session.add(award)
        db.session.flush()
        db.session.add(
            AwardBook(
                award_id=award.id,
                year=2026,
                title='Original title',
                title_zh='获奖书已有中文',
                author='Synthetic author',
                isbn13=ISBN,
            )
        )
        db.session.commit()
    assert post().status_code == 200
    with app.app_context():
        assert AwardBook.query.filter_by(isbn13=ISBN).one().title_zh == '获奖书已有中文'
