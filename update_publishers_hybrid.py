"""
批量给出版社添加混合架构支持
"""
import re

# 混合架构代码模板 - 需要添加到每个出版社爬虫的 __init__ 后面
HYBRID_CODE_TEMPLATE = """
        self._crawl4ai_available = self._check_crawl4ai()

    def _check_crawl4ai(self) -> bool:
        \"\"\"检查 Crawl4AI 是否可用\"\"\"
        try:
            import crawl4ai
            logger.info(f\"✅ {self.PUBLISHER_NAME_EN}: Crawl4AI 可用\")
            return True
        except ImportError:
            logger.info(f\"ℹ️ {self.PUBLISHER_NAME_EN}: Crawl4AI 未安装，仅使用传统 requests\")
            return False

    async def _crawl_with_crawl4ai_async(self, url: str):
        \"\"\"使用 Crawl4AI 异步爬取\"\"\"
        if not self._crawl4ai_available:
            return None

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
            from bs4 import BeautifulSoup

            logger.info(f\"🕸️ {self.PUBLISHER_NAME_EN}: 使用 Crawl4AI 爬取: {url}\")

            browser_config = BrowserConfig(headless=True, verbose=False)
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                timeout=30000,
                word_count_threshold=1,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)
                if result and result.success and result.html:
                    logger.info(f\"✅ {self.PUBLISHER_NAME_EN}: Crawl4AI 爬取成功\")
                    return BeautifulSoup(result.html, 'html.parser'), 'crawl4ai'
            return None, None
        except Exception as e:
            logger.warning(f\"⚠️ {self.PUBLISHER_NAME_EN}: Crawl4AI 出错: {e}\")
            return None, None

    def _crawl_with_crawl4ai(self, url: str):
        \"\"\"同步使用 Crawl4AI 爬取\"\"\"
        import asyncio
        try:
            return asyncio.run(self._crawl_with_crawl4ai_async(url))
        except Exception as e:
            logger.warning(f\"⚠️ {self.PUBLISHER_NAME_EN}: Crawl4AI 同步调用失败: {e}\")
            return None, None

    def _make_request_with_fallback(self, url: str):
        \"\"\"
        带降级的请求方法

        先尝试传统 requests，失败后用 Crawl4AI
        返回 (soup, source)，source 是 'requests' 或 'crawl4ai'
        \"\"\"
        # 先尝试传统 requests
        logger.info(f\"🔄 {self.PUBLISHER_NAME_EN}: 尝试传统 requests: {url}\")
        response = self._make_request(url)

        if response:
            logger.info(f\"✅ {self.PUBLISHER_NAME_EN}: 传统 requests 成功\")
            return self._parse_html(response.text), 'requests'

        # 失败后尝试 Crawl4AI
        if self._crawl4ai_available:
            logger.info(f\"🔄 {self.PUBLISHER_NAME_EN}: 降级到 Crawl4AI\")
            return self._crawl_with_crawl4ai(url)

        logger.warning(f\"❌ {self.PUBLISHER_NAME_EN}: 所有方法都失败: {url}\")
        return None, None
"""


def update_publisher_file(file_path):
    """更新单个出版社文件"""
    print(f"\n📄 处理: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否已经更新过了
    if '_crawl4ai_available' in content:
        print(f"   ✅ 已经包含混合架构，跳过")
        return False
    
    # 找到 __init__ 方法
    init_pattern = r'(def __init__\(self, config: CrawlerConfig \| None = None\):\s+super\(\).__init__\(config\)\s+if config is None:\s+self\.config\.request_delay = [\d.]+)'
    
    match = re.search(init_pattern, content, re.MULTILINE | re.DOTALL)
    
    if not match:
        print(f"   ❌ 找不到 __init__ 方法")
        return False
    
    # 在 __init__ 后面插入混合架构代码
    old_init = match.group(1)
    new_init = old_init + HYBRID_CODE_TEMPLATE
    
    content = content.replace(old_init, new_init)
    
    # 替换 get_new_books 中的 response = self._make_request(url)
    content = re.sub(
        r'(response = self\._make_request\(url\)\s+if not response:\s+break\s+\s+soup = self\._parse_html\(response\.text\))',
        r'soup, source = self._make_request_with_fallback(url)\n        if not soup:\n            break\n\n        logger.info(f"✅ 使用 {source} 获取页面成功")',
        content
    )
    
    # 替换 get_book_details 中的 response = self._make_request(book_url)
    content = re.sub(
        r'(response = self\._make_request\(book_url\)\s+if not response:\s+return None\s+\s+soup = self\._parse_html\(response\.text\))',
        r'soup, source = self._make_request_with_fallback(book_url)\n        if not soup:\n            return None\n\n        logger.info(f"✅ 使用 {source} 获取书籍详情成功")',
        content
    )
    
    # 写入更新后的内容
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"   ✅ 更新成功")
    return True


def main():
    """主函数"""
    print("="*60)
    print("🔧 批量更新出版社混合架构")
    print("="*60)
    
    import sys
    from pathlib import Path
    
    project_root = Path(__file__).parent
    crawler_dir = project_root / 'app' / 'services' / 'publisher_crawler'
    
    # 要更新的文件列表
    publishers = [
        'simon_schuster.py',
        'hachette.py',
        'harpercollins.py',
        'macmillan.py',
    ]
    
    updated_count = 0
    for pub_file in publishers:
        file_path = crawler_dir / pub_file
        if file_path.exists():
            if update_publisher_file(str(file_path)):
                updated_count += 1
        else:
            print(f"\n❌ 文件不存在: {file_path}")
    
    print("\n" + "="*60)
    print(f"✅ 完成！更新了 {updated_count} 个文件")
    print("="*60)


if __name__ == "__main__":
    main()

