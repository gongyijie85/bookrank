import logging

from ...models.database import db
from ...models.new_book import NewBook, Publisher
from .. import publisher_data as pd

logger = logging.getLogger(__name__)


class PublisherManager:
    DEFAULT_PUBLISHERS = pd.DEFAULT_PUBLISHERS
    STATIC_DATA_FILES = pd.STATIC_DATA_FILES
    _CRAWLER_MIGRATION = pd.CRAWLER_MIGRATION
    VALID_CATEGORIES = pd.VALID_CATEGORIES

    def init_publishers(self) -> int:
        count = 0

        for pub_data in self.DEFAULT_PUBLISHERS:
            existing = Publisher.query.filter_by(name_en=pub_data['name_en']).first()
            if existing:
                if existing.crawler_class in self._CRAWLER_MIGRATION:
                    old_class = existing.crawler_class
                    new_class = self._CRAWLER_MIGRATION[old_class]
                    existing.crawler_class = new_class
                    logger.info(f'出版社爬虫迁移: {pub_data["name_en"]} {old_class} -> {new_class}')
                else:
                    logger.info(f'出版社已存在: {pub_data["name_en"]}')
                continue

            publisher = Publisher(
                name=pub_data['name'],
                name_en=pub_data['name_en'],
                website=pub_data['website'],
                crawler_class=pub_data['crawler_class'],
                is_active=True,
            )

            db.session.add(publisher)
            count += 1
            logger.info(f'创建出版社: {pub_data["name_en"]}')

        if count > 0:
            db.session.commit()
            logger.info(f'成功创建 {count} 个出版社')
        else:
            logger.info('所有出版社已存在，无需创建')

        return count

    def get_publishers(self, active_only: bool = True) -> list[Publisher]:
        query = Publisher.query

        if active_only:
            query = query.filter_by(is_active=True)

        return query.order_by(Publisher.name_en).all()

    def get_publisher(self, publisher_id: int) -> Publisher | None:
        return db.session.get(Publisher, publisher_id)

    def update_publisher_status(self, publisher_id: int, is_active: bool) -> bool:
        publisher = self.get_publisher(publisher_id)
        if not publisher:
            return False

        publisher.is_active = is_active
        db.session.commit()
        logger.info(f'更新出版社状态: {publisher.name_en} -> {"启用" if is_active else "禁用"}')
        return True

    def get_publisher_book_counts(self) -> dict[int, int]:
        from sqlalchemy import func

        results = (
            db.session.query(NewBook.publisher_id, func.count(NewBook.id).label('count'))
            .filter(NewBook.is_displayable.is_(True))
            .group_by(NewBook.publisher_id)
            .all()
        )
        return dict(results)
