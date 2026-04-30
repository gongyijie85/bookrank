import time
import logging
from typing import Any, Optional

import requests

from .api_utils import (
    create_session_with_retry, _get_api_cache_service,
    _safe_cache_set, api_retry
)

logger = logging.getLogger(__name__)


class WikidataClient:
    """
    Wikidata SPARQL API 客户端

    用于批量获取图书奖项获奖数据
    Wikidata 是维基百科的结构化数据存储库

    API 文档：https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service
    """

    AWARD_IDS = {
        'nebula': 'Q327503',
        'hugo': 'Q162455',
        'booker': 'Q155091',
        'international_booker': 'Q2519161',
        'pulitzer_fiction': 'Q162530',
        'edgar': 'Q532244',
        'nobel_literature': 'Q37922',
    }

    def __init__(self, timeout: int = 60):
        self._base_url = 'https://query.wikidata.org/sparql'
        self._timeout = timeout
        self._session = create_session_with_retry(max_retries=1)
        self._session.headers.update({
            'User-Agent': 'BookRank/2.0 (bookrank@example.com)',
            'Accept': 'application/sparql-results+json'
        })

    @api_retry(max_attempts=2, backoff_factor=1.5)
    def query_award_winners(self, award_key: str, start_year: int = 2020,
                           end_year: int = 2025, limit: int = 100) -> list:
        """查询指定奖项的获奖图书"""
        award_id = self.AWARD_IDS.get(award_key)
        if not award_id:
            logger.error(f"Unknown award: {award_key}")
            return []

        sparql_query = self._build_sparql_query(award_id, start_year, end_year, limit)

        try:
            response = self._session.get(
                self._base_url,
                params={'query': sparql_query, 'format': 'json'},
                timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_sparql_results(data, award_key)

        except requests.RequestException as e:
            logger.warning(f"Failed to query Wikidata for {award_key}: {e}")
            return []

    def _build_sparql_query(self, award_id: str, start_year: int,
                           end_year: int, limit: int) -> str:
        """构建 SPARQL 查询语句"""
        return f"""
        SELECT DISTINCT ?book ?bookLabel ?author ?authorLabel ?isbn13 ?isbn10
                        ?publicationDate ?year ?publisher ?publisherLabel
        WHERE {{
          ?book wdt:P31 wd:Q7725634 ;
                wdt:P166 wd:{award_id} ;
                wdt:P1476 ?bookLabel ;
                wdt:P50 ?author ;
                wdt:P577 ?publicationDate .

          ?author rdfs:label ?authorLabel .
          FILTER(LANG(?authorLabel) = "en")

          OPTIONAL {{ ?book wdt:P212 ?isbn13 }}
          OPTIONAL {{ ?book wdt:P957 ?isbn10 }}

          OPTIONAL {{
            ?book wdt:P123 ?publisher .
            ?publisher rdfs:label ?publisherLabel .
            FILTER(LANG(?publisherLabel) = "en")
          }}

          BIND(YEAR(?publicationDate) AS ?year)
          FILTER(?year >= {start_year} && ?year <= {end_year})
          FILTER(LANG(?bookLabel) = "en")
        }}
        ORDER BY DESC(?year)
        LIMIT {limit}
        """

    def _parse_sparql_results(self, data: dict, award_key: str) -> list:
        """解析 SPARQL 查询结果"""
        books = []
        bindings = data.get('results', {}).get('bindings', [])

        for binding in bindings:
            book = {
                'award': award_key,
                'wikidata_id': binding.get('book', {}).get('value', '').split('/')[-1],
                'title': binding.get('bookLabel', {}).get('value', ''),
                'author_wikidata_id': binding.get('author', {}).get('value', '').split('/')[-1],
                'author': binding.get('authorLabel', {}).get('value', ''),
                'isbn13': binding.get('isbn13', {}).get('value', ''),
                'isbn10': binding.get('isbn10', {}).get('value', ''),
                'publication_date': binding.get('publicationDate', {}).get('value', ''),
                'year': int(binding.get('year', {}).get('value', 0)),
                'publisher': binding.get('publisherLabel', {}).get('value', ''),
            }
            books.append(book)

        return books

    def get_all_award_books(self, awards: list | None = None, start_year: int = 2020,
                           end_year: int = 2025) -> dict:
        """获取多个奖项的获奖图书"""
        if awards is None:
            awards = list(self.AWARD_IDS.keys())

        results = {}

        for award_key in awards:
            logger.info(f"查询 {award_key} 获奖图书...")
            books = self.query_award_winners(award_key, start_year, end_year)
            results[award_key] = books
            logger.info(f"{award_key}: 找到 {len(books)} 本图书")

            time.sleep(0.5)

        return results

    @api_retry(max_attempts=2, backoff_factor=1.5)
    def query_award_info(self, award_key: str) -> dict:
        """查询奖项的详细信息"""
        award_id = self.AWARD_IDS.get(award_key)
        if not award_id:
            logger.error(f"Unknown award: {award_key}")
            return {}

        sparql_query = self._build_award_info_query(award_id)

        try:
            response = self._session.get(
                self._base_url,
                params={'query': sparql_query, 'format': 'json'},
                timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_award_info(data, award_key)

        except requests.RequestException as e:
            logger.warning(f"Failed to query award info for {award_key}: {e}")
            return {}

    def _build_award_info_query(self, award_id: str) -> str:
        """构建查询奖项信息的 SPARQL 语句"""
        return f"""
        SELECT DISTINCT ?award ?awardLabel ?awardDescription
                        ?country ?countryLabel
                        ?inception ?categoryCount
        WHERE {{
          BIND(wd:{award_id} AS ?award)

          ?award rdfs:label ?awardLabel .
          FILTER(LANG(?awardLabel) = "en")

          ?award schema:description ?awardDescription .
          FILTER(LANG(?awardDescription) = "en")

          OPTIONAL {{
            ?award wdt:P17 ?country .
            ?country rdfs:label ?countryLabel .
            FILTER(LANG(?countryLabel) = "en")
          }}

          OPTIONAL {{ ?award wdt:P571 ?inception }}
          OPTIONAL {{ ?award wdt:P2517 ?categoryCount }}
        }}
        LIMIT 1
        """

    def _parse_award_info(self, data: dict, award_key: str) -> dict:
        """解析奖项信息查询结果"""
        bindings = data.get('results', {}).get('bindings', [])

        if not bindings:
            logger.warning(f"No award info found for {award_key}")
            return {}

        binding = bindings[0]

        inception = binding.get('inception', {}).get('value', '')
        established_year = None
        if inception:
            try:
                established_year = int(inception[:4])
            except (ValueError, IndexError):
                pass

        category_count = binding.get('categoryCount', {}).get('value', '')
        try:
            category_count = int(category_count) if category_count else None
        except ValueError:
            category_count = None

        return {
            'award_key': award_key,
            'wikidata_id': binding.get('award', {}).get('value', '').split('/')[-1],
            'name_en': binding.get('awardLabel', {}).get('value', ''),
            'description_en': binding.get('awardDescription', {}).get('value', ''),
            'country_en': binding.get('countryLabel', {}).get('value', ''),
            'established_year': established_year,
            'category_count': category_count,
        }

    def get_all_award_info(self, awards: list | None = None) -> dict:
        """获取多个奖项的详细信息"""
        if awards is None:
            awards = list(self.AWARD_IDS.keys())

        results = {}

        for award_key in awards:
            logger.info(f"查询 {award_key} 奖项信息...")
            info = self.query_award_info(award_key)
            if info:
                results[award_key] = info
                logger.info(f"{award_key}: 获取到奖项信息")
            else:
                logger.warning(f"{award_key}: 未能获取奖项信息")

            time.sleep(0.3)

        return results
