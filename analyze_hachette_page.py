#!/usr/bin/env python3
"""
Hachette 页面结构分析脚本

详细分析 Hachette 页面的结构，寻找真正的书籍列表。
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

# Hachette 页面 URL
HACHETTE_URL = 'https://www.hachettebookgroup.com/category/books/'

# User-Agent
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

def analyze_hachette_page():
    """分析 Hachette 页面结构"""
    logger.info("=== 分析 Hachette 页面结构 ===")
    
    html = get_page_content(HACHETTE_URL)
    if not html:
        return
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # 检查页面标题
    title = soup.find('title')
    if title:
        logger.info(f"页面标题: {title.get_text(strip=True)}")
    
    # 检查所有 div 元素，寻找可能包含书籍的容器
    logger.info("\n检查所有 div 元素...")
    all_divs = soup.find_all('div', class_=True)
    
    # 统计不同类名的 div
    class_counts = {}
    for div in all_divs:
        classes = ' '.join(div.get('class', []))
        if classes:
            class_counts[classes] = class_counts.get(classes, 0) + 1
    
    # 显示出现次数最多的类名
    logger.info("\n出现次数最多的 div 类名:")
    sorted_classes = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)
    for cls, count in sorted_classes[:20]:
        logger.info(f"  {cls}: {count}")
    
    # 检查是否有书籍列表容器
    logger.info("\n检查可能的书籍列表容器...")
    book_containers = []
    
    # 寻找包含书籍的容器
    for div in all_divs:
        classes = ' '.join(div.get('class', []))
        if any(keyword in classes.lower() for keyword in ['book', 'product', 'list', 'grid', 'catalog']):
            book_containers.append(div)
    
    logger.info(f"找到 {len(book_containers)} 个可能的书籍容器")
    
    # 检查每个容器内的书籍项
    for i, container in enumerate(book_containers[:3]):
        logger.info(f"\n容器 {i+1}:")
        logger.info(f"  类: {container.get('class', [])}")
        
        # 检查容器内的链接
        links = container.find_all('a', href=True)
        logger.info(f"  链接数量: {len(links)}")
        
        # 显示前几个链接
        for j, link in enumerate(links[:5]):
            href = link.get('href')
            text = link.get_text(strip=True)
            if href and text:
                logger.info(f"    {j+1}. {text[:50]}... -> {href}")