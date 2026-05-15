#!/usr/bin/env python3
"""
页面结构检查脚本

获取出版社页面的 HTML 结构，以便分析和更新爬虫选择器。
"""

import requests
import logging
from bs4 import BeautifulSoup

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 测试 URL
TEST_URLS = [
    'https://www.hachettebookgroup.com/category/books/',
    'https://us.macmillan.com/new-releases'
]

# 测试不同的 User-Agent
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

def get_page_content(url):
    """获取页面内容"""
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"获取页面失败: {e}")
        return None

def inspect_page_structure(url):
    """检查页面结构"""
    logger.info(f"\n=== 检查页面结构: {url} ===")
    
    html = get_page_content(url)
    if not html:
        return
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # 检查主要容器
    logger.info("检查主要容器...")
    containers = soup.find_all(['div', 'section', 'main'], class_=True)
    
    # 过滤出可能包含书籍的容器
    book_containers = []
    for container in containers:
        classes = container.get('class', [])
        if any(keyword in ' '.join(classes).lower() for keyword in ['book', 'product', 'catalog', 'release', 'new']):
            book_containers.append(container)
    
    logger.info(f"找到 {len(book_containers)} 个可能的书籍容器")
    
    # 检查每个容器的内部结构
    for i, container in enumerate(book_containers[:3]):  # 只检查前3个
        logger.info(f"\n容器 {i+1} 结构:")
        logger.info(f"标签: {container.name}")
        logger.info(f"类: {container.get('class', [])}")
        
        # 检查容器内的直接子元素
        children = container.find_all(recursive=False)
        logger.info(f"直接子元素数量: {len(children)}")
        
        # 检查是否有链接和标题
        links = container.find_all('a', href=True)
        logger.info(f"链接数量: {len(links)}")
        
        titles = container.find_all(['h1', 'h2', 'h3', 'h4'])
        logger.info(f"标题数量: {len(titles)}")
        
        # 显示前几个标题
        for j, title in enumerate(titles[:3]):
            logger.info(f"  标题 {j+1}: {title.get_text(strip=True)[:50]}...")
    
    # 检查所有可能的书籍项
    logger.info("\n检查可能的书籍项...")
    potential_items = soup.find_all(['div', 'article', 'li'], class_=True)
    
    # 过滤出可能的书籍项
    book_items = []
    for item in potential_items:
        classes = item.get('class', [])
        text = item.get_text().lower()
        if any(keyword in ' '.join(classes).lower() for keyword in ['book', 'product', 'item', 'tile', 'card']) or \
           any(keyword in text for keyword in ['author', 'isbn', 'price', 'publish']):
            book_items.append(item)
    
    logger.info(f"找到 {len(book_items)} 个可能的书籍项")
    
    # 显示前几个书籍项的结构
    for i, item in enumerate(book_items[:3]):
        logger.info(f"\n书籍项 {i+1} 结构:")
        logger.info(f"标签: {item.name}")
        logger.info(f"类: {item.get('class', [])}")
        
        # 检查是否有链接
        link = item.find('a', href=True)
        if link:
            logger.info(f"链接: {link.get('href')}")
        
        # 检查是否有标题
        title = item.find(['h2', 'h3', 'h4'])
        if title:
            logger.info(f"标题: {title.get_text(strip=True)[:50]}...")
        
        # 检查是否有作者
        author = item.find(['p', 'span'], class_=True)
        if author:
            text = author.get_text(strip=True)
            if 'by' in text.lower() or 'author' in ' '.join(author.get('class', [])).lower():
                logger.info(f"作者: {text[:50]}...")

def main():
    """主函数"""
    for url in TEST_URLS:
        inspect_page_structure(url)

if __name__ == '__main__':
    main()
