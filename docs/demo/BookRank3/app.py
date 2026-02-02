import os
import time
import csv
import logging
import fcntl
import json
import hashlib
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from urllib.parse import quote
import requests
from flask import Flask, render_template, jsonify, request, make_response, send_from_directory, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# 初始化应用
app = Flask(__name__)
CORS(app)
application = app  # EB需要的变量

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()
NYT_API_KEY = os.getenv("NYT_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
if not NYT_API_KEY:
    logger.warning("⚠️ 未配置NYT_API_KEY，部分功能受限")

# 常量配置
API_BASE_URL = "https://api.nytimes.com/svc/books/v3/lists/current"
CACHE_TTL = 3600  # 缓存有效期（秒）

# 分类配置（中文名称映射）
CATEGORIES = {
    # 精装类
    "hardcover-fiction": "精装小说",
    "hardcover-nonfiction": "精装非虚构",
    # 平装类
    "trade-fiction-paperback": "平装小说",
    "paperback-nonfiction": "平装非虚构"
}
# 明确分类顺序
CATEGORY_ORDER = [
    "hardcover-fiction", 
    "hardcover-nonfiction",
    "trade-fiction-paperback",
    "paperback-nonfiction"
]

# 缓存配置（使用Path库更灵活）
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
# 图片缓存配置
IMAGE_CACHE_DIR = CACHE_DIR / "images"
IMAGE_CACHE_DIR.mkdir(exist_ok=True)


# -------------------------- 缓存工具函数 --------------------------
def is_cache_valid(key):
    """检查缓存是否有效（未过期）"""
    cache_file = CACHE_DIR / f"{key}.json"
    if not cache_file.exists():
        return False
    modified_time = cache_file.stat().st_mtime
    return (time.time() - modified_time) < CACHE_TTL


def get_cached_data(key):
    """获取缓存数据"""
    cache_file = CACHE_DIR / f"{key}.json"
    if not cache_file.exists():
        return None
    with open(cache_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_cache_time(key):
    """获取缓存文件的修改时间"""
    cache_file = CACHE_DIR / f"{key}.json"
    if not cache_file.exists():
        return None
    modified_time = cache_file.stat().st_mtime
    return datetime.fromtimestamp(modified_time).strftime("%Y-%m-%d %H:%M:%S")


def get_latest_cache_time():
    """获取所有分类中最新的缓存时间"""
    latest_time = None
    for cat_id in CATEGORY_ORDER:
        cache_time = get_cache_time(cat_id)
        if cache_time:
            if not latest_time or cache_time > latest_time:
                latest_time = cache_time
    return latest_time or "暂无数据"


def save_cache_data(key, data):
    """保存数据到缓存"""
    cache_file = CACHE_DIR / f"{key}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# -------------------------- 图书信息补充工具 --------------------------
# 语言代码到中文的映射
LANGUAGE_MAP = {
    'en': '英语', 'zh': '中文', 'ja': '日语', 'ko': '韩语',
    'fr': '法语', 'de': '德语', 'es': '西班牙语', 'ru': '俄语'
}


def fetch_supplement_info(isbn):
    """通过Google Books API补充图书信息（出版日期、页数、语言等）"""
    if not GOOGLE_API_KEY or not isbn:
        return {}
    
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    params = {"key": GOOGLE_API_KEY}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "items" in data and len(data["items"]) > 0:
            volume_info = data["items"][0]["volumeInfo"]
            lang_code = volume_info.get("language", "")
            return {
                "publication_dt": volume_info.get("publishedDate", ""),
                "details": volume_info.get("description", ""),
                "page_count": volume_info.get("pageCount", ""),
                "language": LANGUAGE_MAP.get(lang_code.lower(), lang_code)
            }
    except Exception as e:
        logger.warning(f"Google API补充信息失败(ISBN: {isbn}): {str(e)}")
    
    return {}


# -------------------------- 图片缓存工具 --------------------------
def get_cached_image_url(original_url):
    """缓存图书封面图片，返回本地缓存路径（避免重复下载）"""
    if not original_url:
        return "/static/default-cover.png"  # 默认封面
    
    # 基于URL生成唯一文件名（哈希值）
    filename = hashlib.md5(original_url.encode()).hexdigest() + ".jpg"
    cache_path = IMAGE_CACHE_DIR / filename
    relative_path = f"/cache/images/{filename}"  # 前端可访问的路径
    
    # 若缓存有效，直接返回
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < CACHE_TTL:
        return relative_path
    
    # 下载并缓存图片（支持代理）
    try:
        proxies = {}
        if os.getenv("HTTP_PROXY"):
            proxies["http"] = os.getenv("HTTP_PROXY")
            proxies["https"] = os.getenv("HTTPS_PROXY")
        
        response = requests.get(original_url, proxies=proxies, timeout=15, stream=True)
        response.raise_for_status()
        
        with open(cache_path, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        
        return relative_path
    except Exception as e:
        logger.warning(f"图片缓存失败({original_url}): {str(e)}")
        return "/static/default-cover.png"


# -------------------------- API请求工具 --------------------------
def fetch_books(category_id, max_retries=3):
    """获取指定分类的图书数据（带缓存、文件锁和频率控制）"""
    if not NYT_API_KEY:
        return []
    
    # 优先使用缓存
    if is_cache_valid(category_id):
        cached_data = get_cached_data(category_id)
        logger.info(f"从缓存获取 {CATEGORIES[category_id]} 数据")
        return cached_data
    
    url = f"{API_BASE_URL}/{category_id}.json"
    params = {"api-key": NYT_API_KEY}
    
    # 文件锁：避免多进程同时请求API触发频率限制
    lock_file = CACHE_DIR / "api_lock"
    with open(lock_file, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)  # 排他锁
            
            # 再次检查缓存（可能其他进程已更新）
            if is_cache_valid(category_id):
                cached_data = get_cached_data(category_id)
                logger.info(f"从缓存获取 {CATEGORIES[category_id]} 数据")
                return cached_data
            
            # 基础延迟，减少频率限制风险
            base_delay = 3
            logger.info(f"请求 {category_id} 前等待 {base_delay} 秒")
            time.sleep(base_delay)
            
            for retry in range(max_retries):
                try:
                    response = requests.get(url, params=params, timeout=15)
                    
                    if response.status_code == 429:
                        # 频率限制：指数退避重试
                        wait_time = (retry + 1) * 10  # 10s → 20s → 30s
                        logger.warning(f"触发频率限制，等待 {wait_time} 秒后重试（第{retry+1}次）")
                        time.sleep(wait_time)
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # 提取榜单基础信息
                    results = data.get("results", {})
                    list_name = results.get("list_name", "未知榜单")
                    published_date = results.get("published_date", "")
                    
                    # 解析图书数据
                    books = []
                    for book in results.get("books", []):
                        # 提取购买链接
                        buy_links = [
                            {"name": link.get("name", ""), "url": link.get("url", "")}
                            for link in book.get("buy_links", [])
                        ]
                        
                        # 提取ISBN（优先13位）
                        isbn = book.get("primary_isbn13", book.get("primary_isbn10", ""))
                        # 获取Google补充信息
                        supplement = fetch_supplement_info(isbn)
                        
                        books.append({
                            # 基本信息
                            "id": isbn,
                            "title": book.get("title", "未知标题"),
                            "author": book.get("author", "未知作者"),
                            "publisher": book.get("publisher", "未知出版社"),
                            "cover": get_cached_image_url(book.get("book_image")),
                            
                            # 榜单信息
                            "list_name": list_name,
                            "category_id": category_id,
                            "category_name": CATEGORIES[category_id],
                            "rank": book.get("rank", 0),
                            "weeks_on_list": book.get("weeks_on_list", 0),
                            "rank_last_week": book.get("rank_last_week", "无"),
                            
                            # 描述信息
                            "description": book.get("description", "暂无简介"),
                            "details": supplement.get("details", "暂无详细介绍"),
                            
                            # 购买链接
                            "buy_links": buy_links,
                            
                            # 附加信息
                            "published_date": published_date,
                            "publication_dt": supplement.get("publication_dt", ""),
                            "page_count": supplement.get("page_count", ""),
                            "language": supplement.get("language", ""),
                            "isbn13": book.get("primary_isbn13", ""),
                            "isbn10": book.get("primary_isbn10", ""),
                            "price": book.get("price", "未知")
                        })
                    
                    # 保存到缓存
                    save_cache_data(category_id, books)
                    logger.info(f"获取并缓存 {CATEGORIES[category_id]} 数据成功")
                    return books
                    
                except Exception as e:
                    logger.error(f"请求 {category_id} 失败（第{retry+1}次）: {str(e)}")
                    if retry < max_retries - 1:
                        time.sleep(2)
                        continue
                    raise e
                    
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)  # 释放锁
    
    return []


# -------------------------- 路由定义 --------------------------
@app.route('/')
def index():
    """首页（需配合templates/index.html使用）"""
    return render_template('index.html', categories=CATEGORIES)


@app.route('/api/books/<category>')
def api_books(category):
    """获取图书数据API（支持单个分类或全部）"""
    try:
        latest_update = get_latest_cache_time()
        
        if category == 'all':
            # 返回所有分类数据
            all_books = {cat_id: fetch_books(cat_id) for cat_id in CATEGORY_ORDER}
            return jsonify({
                'success': True,
                'books': all_books,
                'categories': CATEGORIES,
                'category_order': CATEGORY_ORDER,
                'latest_update': latest_update
            })
        else:
            # 返回单个分类数据
            if category not in CATEGORIES:
                return jsonify({'success': False, 'message': '无效的分类'}), 400
            
            books = fetch_books(category)
            return jsonify({
                'success': True,
                'books': books,
                'category_name': CATEGORIES[category],
                'latest_update': latest_update
            })
    except Exception as e:
        logger.error(f"API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/search')
def api_search():
    """搜索图书（按标题或作者）"""
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({'success': False, 'message': '搜索关键词不能为空'})
    
    try:
        # 聚合所有分类的图书数据
        all_books = []
        for cat_id in CATEGORY_ORDER:
            all_books.extend(fetch_books(cat_id))
        
        # 模糊搜索（不区分大小写）
        keyword_lower = keyword.lower()
        results = [
            book for book in all_books
            if keyword_lower in book['title'].lower() or 
               keyword_lower in book['author'].lower()
        ]
        
        return jsonify({
            'success': True,
            'books': results,
            'count': len(results),
            'latest_update': get_latest_cache_time()
        })
    except Exception as e:
        logger.error(f"搜索错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/export/<category>')
def export_csv(category):
    """导出图书数据为CSV（支持单个分类或全部）"""
    try:
        # 收集要导出的数据
        if category == 'all':
            all_books = []
            for cat_id in CATEGORY_ORDER:
                all_books.extend(fetch_books(cat_id))
        else:
            if category not in CATEGORIES:
                return jsonify({'success': False, 'message': '无效的分类'}), 400
            all_books = fetch_books(category)
        
        # 生成CSV内容
        output = StringIO()
        writer = csv.writer(output)
        # 表头（中文）
        writer.writerow([
            '分类', '书名', '作者', '出版社', '当前排名', 
            '上周排名', '上榜周数', '出版日期', '页数', 
            '语言', 'ISBN-13', 'ISBN-10', '价格'
        ])
        # 数据行
        for book in all_books:
            writer.writerow([
                book.get('category_name', ''),
                book.get('title', ''),
                book.get('author', ''),
                book.get('publisher', ''),
                book.get('rank', ''),
                book.get('rank_last_week', ''),
                book.get('weeks_on_list', ''),
                book.get('publication_dt', ''),
                book.get('page_count', ''),
                book.get('language', ''),
                book.get('isbn13', ''),
                book.get('isbn10', ''),
                book.get('price', '')
            ])
        
        # 准备响应（处理中文编码）
        output.seek(0)
        csv_content = output.getvalue()
        response_data = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')  # 添加BOM避免乱码
        
        response = make_response(response_data)
        filename = f'纽约时报畅销书_{category}_{datetime.now().strftime("%Y%m%d")}.csv'
        response.headers["Content-Disposition"] = f"attachment; filename={quote(filename)}"
        response.headers["Content-type"] = "text/csv; charset=utf-8"
        return response
    except Exception as e:
        logger.error(f"导出CSV错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/cache/images/<filename>')
def cached_image(filename):
    """提供缓存图片访问"""
    return send_from_directory(IMAGE_CACHE_DIR, filename)


@app.route('/static/<path:path>')
def send_static(path):
    """提供静态文件访问（CSS/JS/默认图片等）"""
    return send_from_directory('static', path)


# -------------------------- 启动配置 --------------------------
if __name__ == '__main__':
    # 生产环境禁用debug，绑定0.0.0.0允许外部访问
    app.run(host="0.0.0.0", port=8000, debug=False)
