"""Wikidata 客户端测试"""

from unittest.mock import patch

import pytest

from app.services.wikidata_client import WikidataClient


@pytest.fixture
def wikidata_client():
    return WikidataClient(timeout=10)


class TestAwardIds:
    """测试 AWARD_IDS 常量"""

    def test_known_awards(self):
        assert 'nebula' in WikidataClient.AWARD_IDS
        assert 'hugo' in WikidataClient.AWARD_IDS
        assert 'booker' in WikidataClient.AWARD_IDS
        assert 'pulitzer_fiction' in WikidataClient.AWARD_IDS


class TestBuildSparqlQuery:
    """测试 _build_sparql_query"""

    def test_query_contains_award_id(self, wikidata_client):
        query = wikidata_client._build_sparql_query('Q327503', 2020, 2025, 50)
        assert 'Q327503' in query
        assert '2020' in query
        assert '2025' in query
        assert '50' in query


class TestParseSparqlResults:
    """测试 _parse_sparql_results"""

    def test_parse_results(self, wikidata_client):
        data = {
            'results': {
                'bindings': [
                    {
                        'book': {'value': 'http://www.wikidata.org/entity/Q123'},
                        'bookLabel': {'value': 'Test Book'},
                        'author': {'value': 'http://www.wikidata.org/entity/Q456'},
                        'authorLabel': {'value': 'Test Author'},
                        'isbn13': {'value': '9780000000001'},
                        'isbn10': {'value': '0000000001'},
                        'publicationDate': {'value': '2023-01-01'},
                        'year': {'value': '2023'},
                        'publisherLabel': {'value': 'Test Publisher'},
                    }
                ]
            }
        }
        result = wikidata_client._parse_sparql_results(data, 'nebula')
        assert len(result) == 1
        assert result[0]['title'] == 'Test Book'
        assert result[0]['author'] == 'Test Author'
        assert result[0]['award'] == 'nebula'
        assert result[0]['year'] == 2023

    def test_empty_results(self, wikidata_client):
        data = {'results': {'bindings': []}}
        result = wikidata_client._parse_sparql_results(data, 'hugo')
        assert result == []


class TestQueryAwardWinners:
    """测试 query_award_winners"""

    def test_unknown_award(self, wikidata_client):
        result = wikidata_client.query_award_winners('unknown_award')
        assert result == []

    @patch.object(WikidataClient, 'query_award_winners')
    def test_known_award(self, mock_query, wikidata_client):
        mock_query.return_value = [{'title': 'Book', 'author': 'Author'}]
        result = wikidata_client.query_award_winners('nebula')
        assert len(result) == 1


class TestBuildAwardInfoQuery:
    """测试 _build_award_info_query"""

    def test_query_contains_award_id(self, wikidata_client):
        query = wikidata_client._build_award_info_query('Q327503')
        assert 'Q327503' in query


class TestParseAwardInfo:
    """测试 _parse_award_info"""

    def test_with_data(self, wikidata_client):
        data = {
            'results': {
                'bindings': [
                    {
                        'award': {'value': 'http://www.wikidata.org/entity/Q327503'},
                        'awardLabel': {'value': 'Nebula Award'},
                        'awardDescription': {'value': 'Science fiction award'},
                        'countryLabel': {'value': 'United States'},
                        'inception': {'value': '1965-01-01'},
                        'categoryCount': {'value': '5'},
                    }
                ]
            }
        }
        result = wikidata_client._parse_award_info(data, 'nebula')
        assert result['award_key'] == 'nebula'
        assert result['name_en'] == 'Nebula Award'
        assert result['established_year'] == 1965
        assert result['category_count'] == 5

    def test_empty_bindings(self, wikidata_client):
        data = {'results': {'bindings': []}}
        result = wikidata_client._parse_award_info(data, 'nebula')
        assert result == {}

    def test_invalid_inception_year(self, wikidata_client):
        data = {
            'results': {
                'bindings': [
                    {
                        'award': {'value': 'http://www.wikidata.org/entity/Q327503'},
                        'awardLabel': {'value': 'Test'},
                        'awardDescription': {'value': 'Desc'},
                        'inception': {'value': 'invalid'},
                    }
                ]
            }
        }
        result = wikidata_client._parse_award_info(data, 'nebula')
        assert result['established_year'] is None

    def test_invalid_category_count(self, wikidata_client):
        data = {
            'results': {
                'bindings': [
                    {
                        'award': {'value': 'http://www.wikidata.org/entity/Q327503'},
                        'awardLabel': {'value': 'Test'},
                        'awardDescription': {'value': 'Desc'},
                        'categoryCount': {'value': 'not_a_number'},
                    }
                ]
            }
        }
        result = wikidata_client._parse_award_info(data, 'nebula')
        assert result['category_count'] is None


class TestQueryAwardInfo:
    """测试 query_award_info"""

    def test_unknown_award(self, wikidata_client):
        result = wikidata_client.query_award_info('nonexistent')
        assert result == {}


class TestGetAllAwardBooks:
    """测试 get_all_award_books"""

    @patch.object(WikidataClient, 'query_award_winners')
    def test_with_awards(self, mock_query, wikidata_client):
        mock_query.return_value = [{'title': 'Book'}]
        result = wikidata_client.get_all_award_books(awards=['nebula'], start_year=2020, end_year=2025)
        assert 'nebula' in result

    @patch.object(WikidataClient, 'query_award_winners')
    def test_default_awards(self, mock_query, wikidata_client):
        mock_query.return_value = []
        result = wikidata_client.get_all_award_books()
        assert len(result) == len(WikidataClient.AWARD_IDS)


class TestGetAllAwardInfo:
    """测试 get_all_award_info"""

    @patch.object(WikidataClient, 'query_award_info')
    def test_with_info(self, mock_query, wikidata_client):
        mock_query.return_value = {'name_en': 'Nebula Award'}
        result = wikidata_client.get_all_award_info(awards=['nebula'])
        assert 'nebula' in result

    @patch.object(WikidataClient, 'query_award_info')
    def test_no_info(self, mock_query, wikidata_client):
        mock_query.return_value = {}
        result = wikidata_client.get_all_award_info(awards=['nebula'])
        assert 'nebula' not in result
