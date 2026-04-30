"""
Hachette Book Group 出版社爬虫

从 Hachette 官网首页抓取 New Releases 新书数据，
并访问详情页获取完整的出版日期、描述、作者等信息。

官网首页：https://www.hachettebookgroup.com/
首页结构：tabpanel[aria-label="New Releases"] 内轮播，每页6本，共24本
URL格式：/titles/{author-slug}/{title-slug}/{ISBN}/
详情页：无 Cloudflare 防护，可直接访问
"""
import logging
import re
import time
from typing import Generator

from bs4 import BeautifulSoup

from .base_crawler import BaseCrawler, BookInfo, CrawlerConfig

logger = logging.getLogger(__name__)

# ISBN 正则：从 URL 路径提取 13 位数字
ISBN_PATTERN = re.compile(r'/titles/.+?/.+?/(\d{10,13})/')


class HachetteCrawler(BaseCrawler):
    """
    Hachette Book Group 出版社爬虫

    从官网首页抓取 New Releases 轮播数据，
    并访问每本书的详情页获取完整信息。
    """

    PUBLISHER_NAME = "阿歇特"
    PUBLISHER_NAME_EN = "Hachette Book Group"
    PUBLISHER_WEBSITE = "https://www.hachettebookgroup.com"
    CRAWLER_CLASS_NAME = "HachetteCrawler"

    # 首页 URL
    HOME_URL = "https://www.hachettebookgroup.com/"

    # 详情页请求间隔（秒），避免请求过快被限制
    DETAIL_DELAY = 1.0

    CATEGORY_MAP = {
        'fiction': '小说',
        'nonfiction': '非虚构',
        'mystery': '悬疑',
        'romance': '言情',
        'thriller': '惊悚',
        'science_fiction': '科幻',
        'fantasy': '奇幻',
        'biography': '传记',
        'history': '历史',
        'children': '儿童读物',
        'young_adult': '青少年',
        'business': '商业',
        'self_help': '自助',
        'cooking': '烹饪',
        'travel': '旅行',
    }

    def __init__(self, config=None):
        super().__init__(config)
        if config is None:
            self.config.request_delay = 1.0

    def get_categories(self) -> list[dict[str, str]]:
        """获取支持的分类列表"""
        return [
            {'id': 'fiction', 'name': '小说'},
            {'id': 'nonfiction', 'name': '非虚构'},
            {'id': 'mystery', 'name': '悬疑'},
            {'id': 'romance', 'name': '言情'},
            {'id': 'thriller', 'name': '惊悚'},
            {'id': 'science_fiction', 'name': '科幻'},
            {'id': 'fantasy', 'name': '奇幻'},
            {'id': 'biography', 'name': '传记'},
            {'id': 'history', 'name': '历史'},
            {'id': 'children', 'name': '儿童读物'},
            {'id': 'young_adult', 'name': '青少年'},
            {'id': 'business', 'name': '商业'},
            {'id': 'self_help', 'name': '自助'},
            {'id': 'cooking', 'name': '烹饪'},
            {'id': 'travel', 'name': '旅行'},
        ]

    def get_new_books(
        self,
        category: str | None = None,
        max_books: int = 100,
    ) -> Generator[BookInfo, None, None]:
        """
        获取 Hachette 新书列表

        从首页 New Releases 轮播提取书籍链接，
        然后逐个访问详情页获取完整信息。

        Args:
            category: 分类筛选（可选）
            max_books: 最大获取数量

        Yields:
            BookInfo 对象
        """
        logger.info("🔍 开始从 Hachette 官网首页获取新书...")

        # 1. 请求首页
        response = self._make_request(self.HOME_URL)
        if not response:
            logger.error("❌ 无法访问 Hachette 首页")
            return

        soup = self._parse_html(response.text)

        # 2. 找到 New Releases tabpanel
        tabpanel = soup.find('div', {'role': 'tabpanel', 'aria-label': 'New Releases'})
        if not tabpanel:
            # 备用查找：查找包含 "New Releases" 文本的区域
            tabpanel = soup.find('div', attrs={'data-tab': 'new-releases'})
            if not tabpanel:
                # 尝试查找所有包含 /titles/ 链接的区域
                logger.warning("⚠️ 未找到 New Releases tabpanel，尝试从整个页面提取")
                tabpanel = soup

        # 3. 提取所有书籍链接
        book_links = []
        for link in tabpanel.find_all('a', href=True):
            href = link.get('href', '')
            match = ISBN_PATTERN.search(href)
            if match:
                isbn = match.group(1)
                # 确保是完整的 URL
                if href.startswith('/'):
                    href = f"https://www.hachettebookgroup.com{href}"
                elif not href.startswith('http'):
                    href = f"https://www.hachettebookgroup.com/{href}"
                book_links.append({
                    'url': href,
                    'isbn': isbn,
                    'link_tag': link,
                })

        logger.info(f"📖 从首页找到 {len(book_links)} 本书的链接")

        # 4. 去重（按 ISBN）
        seen_isbns = set()
        unique_books = []
        for book in book_links:
            if book['isbn'] not in seen_isbns:
                seen_isbns.add(book['isbn'])
                unique_books.append(book)
        logger.info(f"📖 去重后共 {len(unique_books)} 本")

        # 5. 逐个访问详情页获取完整信息
        count = 0
        for book_data in unique_books:
            if count >= max_books:
                break

            try:
                # 从首页提取基本信息
                link_tag = book_data['link_tag']
                img_tag = link_tag.find('img')

                title = ""
                cover_url = ""
                if img_tag:
                    title = img_tag.get('alt', '').strip()
                    cover_url = img_tag.get('src', '')

                # 如果没有标题，从链接文本提取
                if not title:
                    title = self._clean_text(link_tag.get_text())
                    # 移除可能的 "New Release" 等标签文本
                    title = title.replace('New Release', '').strip()

                # 访问详情页获取完整信息
                detail_info = self._fetch_book_detail(book_data['url'])

                # 合并信息
                isbn13 = book_data['isbn']
                author = detail_info.get('author', '')
                description = detail_info.get('description', '')
                pub_date = detail_info.get('publication_date')
                publisher = detail_info.get('publisher', '')
                price = detail_info.get('price', '')

                # 如果详情页没有作者信息，从 URL 推断
                if not author:
                    url_match = re.search(r'/titles/([^/]+)/', book_data['url'])
                    if url_match:
                        author_slug = url_match.group(1)
                        # 将 slug 转为可读名称：samara-parish → Samara Parish
                        author = author_slug.replace('-', ' ').title()

                # 如果详情页没有封面，用首页的
                if not cover_url and detail_info.get('cover_url'):
                    cover_url = detail_info['cover_url']

                book_info = BookInfo(
                    title=title,
                    author=author,
                    isbn13=isbn13,
                    description=self._truncate_description(description),
                    cover_url=cover_url,
                    publication_date=pub_date,
                    price=price,
                    source_url=book_data['url'],
                )

                # 如果有分类信息，添加
                if detail_info.get('categories'):
                    book_info.category = ', '.join(detail_info['categories'])

                logger.info(f"✅ [{count + 1}] {title} - {author} (ISBN: {isbn13})")
                yield book_info
                count += 1

            except Exception as e:
                logger.error(f"❌ 处理书籍时出错: {e}, URL: {book_data.get('url')}")
                continue

        logger.info(f"✅ Hachette 爬取完成，共获取 {count} 本新书")

    def _fetch_book_detail(self, book_url: str) -> dict:
        """
        访问书籍详情页获取完整信息

        Args:
            book_url: 书籍详情页 URL

        Returns:
            包含详情信息的字典
        """
        result = {
            'author': '',
            'description': '',
            'publication_date': None,
            'publisher': '',
            'price': '',
            'cover_url': '',
            'categories': [],
        }

        try:
            # 详情页请求间隔
            time.sleep(self.DETAIL_DELAY)

            response = self._make_request(book_url)
            if not response:
                return result

            soup = self._parse_html(response.text)

            # 提取作者：查找 /contributor/ 链接
            author_link = soup.find('a', href=re.compile(r'/contributor/'))
            if author_link:
                result['author'] = self._clean_text(author_link.get_text())

            # 提取出版日期：查找 "On Sale" 文本
            # 结构：<span>On Sale</span>: <span>Apr 28, 2026</span>
            for text_node in soup.find_all(string=re.compile(r'On Sale')):
                parent = text_node.parent
                if parent:
                    # 查找同级或父级中的日期文本
                    next_sibling = parent.find_next_sibling()
                    if next_sibling:
                        date_text = self._clean_text(next_sibling.get_text())
                        # 去掉前缀 ": "
                        date_text = date_text.lstrip(': ').strip()
                        if date_text:
                            result['publication_date'] = self._parse_date(date_text)
                            break

            # 备用日期提取：查找包含日期格式的文本
            if not result['publication_date']:
                date_pattern = re.compile(
                    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}'
                )
                for date_match in soup.find_all(string=date_pattern):
                    date_text = date_pattern.search(str(date_match))
                    if date_text:
                        result['publication_date'] = self._parse_date(date_text.group())
                        break

            # 提取描述：查找 Description 按钮后的文本
            desc_button = soup.find('button', string=re.compile(r'Description'))
            if desc_button:
                # 描述通常在按钮的下一个兄弟元素中
                desc_container = desc_button.find_next_sibling()
                if desc_container:
                    desc_text = self._clean_text(desc_container.get_text())
                    if desc_text:
                        result['description'] = desc_text
                else:
                    # 备用：查找按钮父级内的描述文本
                    parent = desc_button.parent
                    if parent:
                        # 获取按钮后的所有文本
                        desc_parts = []
                        for sibling in desc_button.find_next_siblings():
                            text = self._clean_text(sibling.get_text())
                            if text:
                                desc_parts.append(text)
                        if desc_parts:
                            result['description'] = ' '.join(desc_parts)

            # 备用描述提取：查找较长的文本块
            if not result['description']:
                # 查找包含较多文本的段落
                for p in soup.find_all(['p', 'div']):
                    text = self._clean_text(p.get_text())
                    if len(text) > 100 and len(text) < 2000:
                        # 排除导航、页脚等
                        if not p.find('a', href=True):
                            result['description'] = text
                            break

            # 提取出版社：查找 "Publisher" 文本后的链接
            for text_node in soup.find_all(string=re.compile(r'Publisher')):
                parent = text_node.parent
                if parent:
                    publisher_link = parent.find_next('a')
                    if publisher_link:
                        result['publisher'] = self._clean_text(publisher_link.get_text())
                        break

            # 提取价格
            price_pattern = re.compile(r'\$\d+\.\d{2}')
            price_match = soup.find(string=price_pattern)
            if price_match:
                price_text = price_pattern.search(str(price_match))
                if price_text:
                    result['price'] = price_text.group()

            # 提取分类/类型
            genre_heading = soup.find('h3', string=re.compile(r'Genre'))
            if genre_heading:
                genre_container = genre_heading.find_parent()
                if genre_container:
                    for link in genre_container.find_all('a'):
                        genre = self._clean_text(link.get_text())
                        if genre:
                            result['categories'].append(genre)

            # 提取封面图
            og_image = soup.find('meta', property='og:image')
            if og_image:
                result['cover_url'] = og_image.get('content', '')

        except Exception as e:
            logger.error(f"❌ 获取详情页失败: {e}, URL: {book_url}")

        return result

    def get_book_details(self, book_url: str) -> BookInfo | None:
        """
        获取书籍详情

        Args:
            book_url: 书籍详情页 URL

        Returns:
            BookInfo 对象或 None
        """
        response = self._make_request(book_url)
        if not response:
            return None

        detail = self._fetch_book_detail(book_url)

        # 从 URL 提取 ISBN
        isbn_match = ISBN_PATTERN.search(book_url)
        isbn13 = isbn_match.group(1) if isbn_match else None

        return BookInfo(
            title=detail.get('title', ''),
            author=detail.get('author', ''),
            isbn13=isbn13,
            description=self._truncate_description(detail.get('description', '')),
            cover_url=detail.get('cover_url', ''),
            publication_date=detail.get('publication_date'),
            price=detail.get('price', ''),
            source_url=book_url,
        )
