"""图书验证服务测试"""

from unittest.mock import MagicMock, patch

import pytest

from app.models.database import db
from app.models.schemas import AwardBook
from app.services.book_verification_service import BookVerificationService


@pytest.fixture
def verification_service():
    return BookVerificationService()


@pytest.fixture
def valid_book(app, db):
    """创建一本完整有效的获奖图书"""
    with app.app_context():
        book = AwardBook(
            award_id=1,
            year=2024,
            category='fiction',
            rank=1,
            title='The Great Gatsby',
            author='F. Scott Fitzgerald',
            description='A classic American novel set in the Jazz Age',
            isbn13='9780743273565',
            isbn10='0743273567',
            publisher='Scribner',
            publication_year=1925,
            cover_local_path='/covers/gatsby.jpg',
            verification_status='pending',
        )
        db.session.add(book)
        db.session.commit()
        return book.id


@pytest.fixture
def minimal_book(app, db):
    """创建一本只有必填字段的图书"""
    with app.app_context():
        book = AwardBook(
            award_id=1,
            year=2024,
            category='fiction',
            title='AB',
            author='CD',
            verification_status='pending',
        )
        db.session.add(book)
        db.session.commit()
        return book.id


def _get_book(app, book_id):
    with app.app_context():
        return db.session.get(AwardBook, book_id)


class TestVerifyBook:
    """测试 verify_book 主方法"""

    def test_valid_book_passes(self, app, verification_service, valid_book):
        book = _get_book(app, valid_book)
        with app.app_context(), patch.object(verification_service, '_verify_external_api') as mock_ext:
            mock_ext.return_value = {'name': '外部API验证', 'passed': True, 'details': ['✅ Open Library 验证通过']}
            passed, result = verification_service.verify_book(book)

        assert passed is True
        assert result['status'] == 'verified'
        assert result['checks']['basic_info']['passed'] is True
        assert result['checks']['isbn']['passed'] is True

    def test_book_with_errors_fails(self, app, verification_service, minimal_book):
        book = _get_book(app, minimal_book)
        with app.app_context():
            passed, result = verification_service.verify_book(book)

        assert passed is False
        assert result['status'] == 'failed'

    def test_result_contains_book_info(self, app, verification_service, valid_book):
        book = _get_book(app, valid_book)
        with app.app_context(), patch.object(verification_service, '_verify_external_api') as mock_ext:
            mock_ext.return_value = {'name': '外部API验证', 'passed': True, 'details': []}
            _, result = verification_service.verify_book(book)

        assert result['book_id'] == book.id
        assert result['title'] == 'The Great Gatsby'
        assert result['isbn13'] == '9780743273565'

    def test_no_isbn_skips_external_api(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(
                award_id=1,
                year=2024,
                title='No ISBN Book',
                author='Some Author',
                description='A book without ISBN',
                publisher='Test Pub',
                publication_year=2020,
            )
            _passed, result = verification_service.verify_book(book)

        assert 'external_api' not in result['checks']


class TestVerifyBasicInfo:
    """测试 _verify_basic_info"""

    def test_valid_basic_info(self, app, verification_service, valid_book):
        book = _get_book(app, valid_book)
        with app.app_context():
            check = verification_service._verify_basic_info(book)

        assert check['passed'] is True

    def test_empty_title(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='', author='Author')
            check = verification_service._verify_basic_info(book)

        assert check['passed'] is False
        assert '书名不能为空或太短' in verification_service.errors

    def test_short_title(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='A', author='Author')
            check = verification_service._verify_basic_info(book)

        assert check['passed'] is False

    def test_empty_author(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Good Title', author='X')
            check = verification_service._verify_basic_info(book)

        assert check['passed'] is False
        assert '作者不能为空或太短' in verification_service.errors

    def test_short_description_warning(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Good Title', author='Good Author', description='Short')
            verification_service._verify_basic_info(book)

        assert '简介为空或太短' in verification_service.warnings

    def test_none_description_warning(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Good Title', author='Good Author', description=None)
            verification_service._verify_basic_info(book)

        assert '简介为空或太短' in verification_service.warnings


class TestVerifyISBN:
    """测试 _verify_isbn"""

    def test_valid_isbn13(self, app, verification_service, valid_book):
        book = _get_book(app, valid_book)
        with app.app_context():
            check = verification_service._verify_isbn(book)

        assert check['passed'] is True

    def test_missing_isbn13(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13=None)
            check = verification_service._verify_isbn(book)

        assert check['passed'] is False
        assert 'ISBN-13 不能为空' in verification_service.errors

    def test_wrong_length_isbn13(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9781234')
            check = verification_service._verify_isbn(book)

        assert check['passed'] is False
        assert any('长度不正确' in e for e in verification_service.errors)

    def test_non_digit_isbn13(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='abcdefghijklm')
            check = verification_service._verify_isbn(book)

        assert check['passed'] is False
        assert any('数字' in e for e in verification_service.errors)

    def test_bad_checksum(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273560')
            check = verification_service._verify_isbn(book)

        assert check['passed'] is False
        assert any('校验位' in e for e in verification_service.errors)

    def test_isbn_with_dashes(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='978-0-7432-7356-5')
            check = verification_service._verify_isbn(book)

        assert check['passed'] is True

    def test_isbn10_wrong_length_warning(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273565', isbn10='123')
            verification_service._verify_isbn(book)

        assert any('ISBN-10' in w for w in verification_service.warnings)

    def test_isbn10_valid(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(
                award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273565', isbn10='0743273567'
            )
            check = verification_service._verify_isbn(book)

        assert check['passed'] is True


class TestValidateISBN13Checksum:
    """测试 _validate_isbn13_checksum"""

    def test_valid_checksum(self, verification_service):
        assert verification_service._validate_isbn13_checksum('9780743273565') is True

    def test_invalid_checksum(self, verification_service):
        assert verification_service._validate_isbn13_checksum('9780743273560') is False

    def test_short_isbn(self, verification_service):
        assert verification_service._validate_isbn13_checksum('978') is False

    def test_non_digit_isbn(self, verification_service):
        assert verification_service._validate_isbn13_checksum('978abcdefghijk') is False

    def test_another_valid_isbn(self, verification_service):
        assert verification_service._validate_isbn13_checksum('9780143127550') is True


class TestVerifyCover:
    """测试 _verify_cover"""

    def test_local_cover(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', cover_local_path='/covers/book.jpg')
            check = verification_service._verify_cover(book)

        assert check['passed'] is True

    def test_original_url_cover(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(
                award_id=1, year=2024, title='Book', author='Author', cover_original_url='https://example.com/cover.jpg'
            )
            check = verification_service._verify_cover(book)

        assert check['passed'] is True

    @patch('app.services.book_verification_service.requests.head')
    def test_open_library_cover_available(self, mock_head, app, db, verification_service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response

        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273565')
            check = verification_service._verify_cover(book)

        assert check['passed'] is True
        mock_head.assert_called_once()

    @patch('app.services.book_verification_service.requests.head')
    def test_open_library_cover_unavailable(self, mock_head, app, db, verification_service):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_head.return_value = mock_response

        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273565')
            check = verification_service._verify_cover(book)

        assert check['passed'] is False
        assert '封面不可用' in verification_service.warnings[0]

    @patch('app.services.book_verification_service.requests.head')
    def test_open_library_timeout(self, mock_head, app, db, verification_service):
        mock_head.side_effect = Exception('timeout')

        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273565')
            check = verification_service._verify_cover(book)

        assert check['passed'] is False

    def test_no_cover_no_isbn(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author')
            check = verification_service._verify_cover(book)

        assert check['passed'] is False


class TestVerifyMetadata:
    """测试 _verify_metadata"""

    def test_complete_metadata(self, app, verification_service, valid_book):
        book = _get_book(app, valid_book)
        with app.app_context():
            check = verification_service._verify_metadata(book)

        assert check['passed'] is True

    def test_missing_publisher_warning(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', publisher=None)
            verification_service._verify_metadata(book)

        assert any('出版社' in w for w in verification_service.warnings)

    def test_missing_publication_year_warning(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', publication_year=None)
            verification_service._verify_metadata(book)

        assert any('出版年份缺失' in w for w in verification_service.warnings)

    def test_abnormal_publication_year(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', publication_year=2500)
            verification_service._verify_metadata(book)

        assert any('出版年份异常' in w for w in verification_service.warnings)

    def test_missing_award_year(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=None, title='Book', author='Author')
            check = verification_service._verify_metadata(book)

        assert check['passed'] is False
        assert any('获奖年份' in e for e in verification_service.errors)


class TestVerifyExternalAPI:
    """测试 _verify_external_api"""

    @patch('app.services.book_verification_service.requests.get')
    def test_open_library_success(self, mock_get, app, db, verification_service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'title': 'The Great Gatsby'}
        mock_get.return_value = mock_response

        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='The Great Gatsby', author='Author', isbn13='9780743273565')
            check = verification_service._verify_external_api(book)

        assert check['passed'] is True

    @patch('app.services.book_verification_service.requests.get')
    def test_open_library_title_mismatch_warning(self, mock_get, app, db, verification_service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'title': 'Completely Different Title'}
        mock_get.return_value = mock_response

        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='The Great Gatsby', author='Author', isbn13='9780743273565')
            verification_service._verify_external_api(book)

        assert any('书名可能不匹配' in w for w in verification_service.warnings)

    @patch('app.services.book_verification_service.requests.get')
    def test_open_library_fail_google_success(self, mock_get, app, db, verification_service):
        openlib_response = MagicMock()
        openlib_response.status_code = 404

        google_response = MagicMock()
        google_response.status_code = 200
        google_response.json.return_value = {'totalItems': 1}

        mock_get.side_effect = [openlib_response, google_response]

        with app.app_context():
            app.config['GOOGLE_API_KEY'] = 'test-key'
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273565')
            check = verification_service._verify_external_api(book)

        assert check['passed'] is True

    @patch('app.services.book_verification_service.requests.get')
    def test_google_books_no_results(self, mock_get, app, db, verification_service):
        openlib_response = MagicMock()
        openlib_response.status_code = 404

        google_response = MagicMock()
        google_response.status_code = 200
        google_response.json.return_value = {'totalItems': 0}

        mock_get.side_effect = [openlib_response, google_response]

        with app.app_context():
            app.config['GOOGLE_API_KEY'] = 'test-key'
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273565')
            check = verification_service._verify_external_api(book)

        assert check['passed'] is False

    @patch('app.services.book_verification_service.requests.get')
    def test_google_rate_limit(self, mock_get, app, db, verification_service):
        openlib_response = MagicMock()
        openlib_response.status_code = 404

        google_response = MagicMock()
        google_response.status_code = 429

        mock_get.side_effect = [openlib_response, google_response]

        with app.app_context():
            app.config['GOOGLE_API_KEY'] = 'test-key'
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273565')
            check = verification_service._verify_external_api(book)

        assert check['passed'] is False

    def test_no_isbn_skips(self, app, db, verification_service):
        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13=None)
            check = verification_service._verify_external_api(book)

        assert check['passed'] is False

    @patch('app.services.book_verification_service.requests.get')
    def test_all_apis_fail(self, mock_get, app, db, verification_service):
        mock_get.side_effect = Exception('Network error')

        with app.app_context():
            book = AwardBook(award_id=1, year=2024, title='Book', author='Author', isbn13='9780743273565')
            check = verification_service._verify_external_api(book)

        assert check['passed'] is False
        assert any('外部 API' in w for w in verification_service.warnings)


class TestVerifyAllPending:
    """测试 verify_all_pending"""

    def test_verify_pending_books(self, app, db, verification_service):
        with app.app_context():
            book1 = AwardBook(
                award_id=1,
                year=2024,
                title='Good Book',
                author='Good Author',
                description='A nice description here',
                isbn13='9780743273565',
                publisher='Pub',
                publication_year=2020,
                cover_local_path='/c.jpg',
                verification_status='pending',
            )
            db.session.add(book1)
            db.session.commit()

            with patch.object(verification_service, '_verify_external_api') as mock_ext:
                mock_ext.return_value = {'name': '外部API验证', 'passed': True, 'details': []}
                results = verification_service.verify_all_pending(limit=10)

        assert len(results) >= 1
        assert results[0]['status'] in ('verified', 'failed', 'pending')

    def test_verify_with_exception(self, app, db, verification_service):
        with app.app_context():
            book1 = AwardBook(
                award_id=1,
                year=2024,
                title='Bad Book',
                author='Author',
                verification_status='pending',
            )
            db.session.add(book1)
            db.session.commit()

            with patch.object(verification_service, 'verify_book', side_effect=Exception('DB error')):
                results = verification_service.verify_all_pending(limit=10)

        assert len(results) >= 1
        assert results[0]['status'] == 'error'


class TestGetVerificationSummary:
    """测试 get_verification_summary"""

    def test_summary_with_data(self, app, db, verification_service):
        with app.app_context():
            book1 = AwardBook(
                award_id=1,
                year=2024,
                title='V Book',
                author='Author',
                verification_status='verified',
                is_displayable=True,
            )
            book2 = AwardBook(
                award_id=1,
                year=2024,
                title='P Book',
                author='Author',
                verification_status='pending',
                is_displayable=False,
            )
            db.session.add_all([book1, book2])
            db.session.commit()

            summary = verification_service.get_verification_summary()

        assert summary['total'] == 2
        assert summary['verified'] == 1
        assert summary['pending'] == 1

    def test_summary_empty_db(self, app, db, verification_service):
        with app.app_context():
            summary = verification_service.get_verification_summary()

        assert summary['total'] == 0
        assert summary['verification_rate'] == 0
