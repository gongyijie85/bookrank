import os
import time
import csv
import logging
# import fcntl # 原始代码：第5行，已被替换

import json
import hashlib
import sqlite3
import re
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, render_template, jsonify, request, make_response, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# =========================================================
# 修复 Windows 上的 fcntl 错误：
# fcntl 是 Unix 专属模块。在 Windows 上提供一个虚拟实现，
# 牺牲并发安全，但确保程序可运行。
# =========================================================
try:
    import fcntl
except ImportError:
    class DummyFcntl:
        """虚拟类，用于在 Windows 上替换 fcntl，禁用文件锁."""
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 8
        def flock(self, fd, op):
            """在 Windows 上，文件锁操作为空操作 (No-op)"""
            pass
        # 为了兼容 with open() 的 file descriptor，
        # 在 fetch_books 函数中不再需要 fcntl.flock(f, fcntl.LOCK_UN)
        # 因为我们使用了 context manager，但为避免修改过多代码，保留原样。
    fcntl = DummyFcntl()
    logging.warning("⚠️ fcntl 模块未找到。已启用虚拟文件锁，并发缓存可能存在风险。")
# =========================================================

# Initialize application
app = Flask(__name__)
CORS(app)
application = app  # Required by Elastic Beanstalk

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
NYT_API_KEY = os.getenv("NYT_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
if not NYT_API_KEY:
    logger.warning("⚠️ NYT_API_KEY is not configured; book data functionality will be limited.")

# Constants
API_BASE_URL = "https://api.nytimes.com/svc/books/v3/lists/current"
CACHE_TTL = 3600  # 1 hour cache
MAX_WORKERS = 4  # Thread pool size for concurrent requests
API_RATE_LIMIT = 5  # Max API calls per minute
API_CALL_TIMES = []  # Track API call times for rate limiting

# Category configuration
CATEGORIES = {
    "hardcover-fiction": "精装小说",
    "hardcover-nonfiction": "精装非虚构",
    "trade-fiction-paperback": "平装小说", 
    "paperback-nonfiction": "平装非虚构"
}
CATEGORY_ORDER = list(CATEGORIES.keys())

# Cache directory configuration
CACHE_DIR = Path(__file__).parent / "cache"
IMAGE_CACHE_DIR = CACHE_DIR / "images"
try:
    CACHE_DIR.mkdir(exist_ok=True, mode=0o755)
    IMAGE_CACHE_DIR.mkdir(exist_ok=True, mode=0o755)
except PermissionError:
    logger.error("❌ Lacking permissions to create cache directories")

# In-memory cache for frequently accessed data
memory_cache = {}
MEMORY_CACHE_TTL = 300  # 5 minutes

# Language mapping
LANGUAGE_MAP = {
    "en": "英语", "zh": "中文", "ja": "日语", "ko": "韩语",
    "fr": "法语", "de": "德语", "es": "西班牙语", "ru": "俄语"
}

# -------------------------- Database Setup --------------------------
def init_db():
    """Initialize database for storing user preferences and book metadata"""
    db_path = Path(__file__).parent / "bestsellers.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # User preferences table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            session_id TEXT PRIMARY KEY,
            preferred_categories TEXT,
            last_viewed_isbns TEXT,
            view_mode TEXT DEFAULT 'grid',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Book metadata cache table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS book_metadata (
            isbn TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            details TEXT,
            page_count INTEGER,
            language TEXT,
            publication_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Search history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            keyword TEXT,
            result_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized successfully")

init_db()

# -------------------------- Cache Utility Functions --------------------------
def is_cache_valid(key, cache_dir=CACHE_DIR, ttl=CACHE_TTL):
    """Check if cache is still valid"""
    # Check in-memory cache first
    if key in memory_cache:
        cache_time, data = memory_cache[key]
        if time.time() - cache_time < MEMORY_CACHE_TTL:
            return True
    
    # Check file cache
    cache_file = cache_dir / f"{key}.json"
    if not cache_file.exists():
        return False
    return (time.time() - cache_file.stat().st_mtime) < ttl

def get_cached_data(key, cache_dir=CACHE_DIR):
    """Get data from cache (memory or file)"""
    # Check in-memory cache first
    if key in memory_cache:
        cache_time, data = memory_cache[key]
        if time.time() - cache_time < MEMORY_CACHE_TTL:
            logger.info(f"📥 Fetching from memory cache: {key}")
            return data
    
    # Check file cache
    cache_file = cache_dir / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Update memory cache
            memory_cache[key] = (time.time(), data)
            return data
    except (json.JSONDecodeError, PermissionError) as e:
        logger.warning(f"⚠️ Could not read cache file {cache_file}: {e}")
        return None

def save_cache_data(key, data, cache_dir=CACHE_DIR):
    """Save data to cache (memory and file)"""
    # Save to memory cache
    memory_cache[key] = (time.time(), data)
    
    # Save to file cache
    cache_file = cache_dir / f"{key}.json"
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (PermissionError, Exception) as e:
        logger.warning(f"⚠️ Failed to save cache for {key}: {e}")

def get_cache_time(key, cache_dir=CACHE_DIR):
    """Get cache file modification time"""
    cache_file = cache_dir / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        return datetime.fromtimestamp(cache_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except PermissionError:
        return None

def get_latest_cache_time():
    """Get the latest cache time across all categories"""
    latest_time = None
    for cat_id in CATEGORY_ORDER:
        cache_time_str = get_cache_time(cat_id)
        if cache_time_str:
            cache_time = datetime.strptime(cache_time_str, "%Y-%m-%d %H:%M:%S")
            if not latest_time or cache_time > latest_time:
                latest_time = cache_time
    return latest_time.strftime("%Y-%m-%d %H:%M:%S") if latest_time else "暂无数据"

# -------------------------- API Rate Limiting --------------------------
def check_rate_limit():
    """Check if we're within API rate limits"""
    global API_CALL_TIMES
    now = time.time()
    # Remove calls older than 1 minute
    API_CALL_TIMES = [t for t in API_CALL_TIMES if now - t < 60]
    
    if len(API_CALL_TIMES) >= API_RATE_LIMIT:
        return False
    API_CALL_TIMES.append(now)
    return True

# -------------------------- Book Info Utility Functions --------------------------
def fetch_supplement_info(isbn):
    """Fetch additional book info from Google Books API"""
    if not GOOGLE_API_KEY or not isbn:
        return {}
    
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        response = requests.get(url, params={"key": GOOGLE_API_KEY}, timeout=8)
        response.raise_for_status()
        data = response.json()
        if "items" in data and len(data["items"]) > 0:
            volume_info = data["items"][0]["volumeInfo"]
            lang_code = volume_info.get("language", "").lower()
            return {
                "publication_dt": volume_info.get("publishedDate", "Unknown"),
                "details": volume_info.get("description", "No detailed description available."),
                "page_count": volume_info.get("pageCount", "Unknown"),
                "language": LANGUAGE_MAP.get(lang_code, lang_code)
            }
    except Exception as e:
        logger.warning(f"⚠️ Could not fetch supplementary info for ISBN {isbn}: {e}")
    return {}

def get_cached_image_url(original_url):
    """Cache and return local path for book cover images"""
    if not original_url:
        return "/static/default-cover.png"
    
    filename = hashlib.md5(original_url.encode()).hexdigest() + ".jpg"
    cache_path = IMAGE_CACHE_DIR / filename
    relative_path = f"/cache/images/{filename}"
    
    # Return cached path if exists and is recent
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < CACHE_TTL:
        return relative_path
    
    # Download and cache the image
    try:
        response = requests.get(original_url, timeout=10, stream=True)
        response.raise_for_status()
        with open(cache_path, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return relative_path
    except Exception as e:
        logger.warning(f"⚠️ Could not cache image from {original_url}: {e}")
        return "/static/default-cover.png"

# -------------------------- Database Utility Functions --------------------------
def db_conn():
    """Create a database connection"""
    db_path = Path(__file__).parent / "bestsellers.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def save_user_preferences(session_id, preferred_categories=None, last_viewed_isbns=None, view_mode=None):
    """Save user preferences to database"""
    conn = db_conn()
    cur = conn.cursor()
    
    # Convert lists to JSON strings
    categories_json = json.dumps(preferred_categories) if preferred_categories else None
    isbns_json = json.dumps(last_viewed_isbns) if last_viewed_isbns else None
    
    try:
        cur.execute(
            """INSERT OR REPLACE INTO user_preferences 
               (session_id, preferred_categories, last_viewed_isbns, view_mode, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (session_id, categories_json, isbns_json, view_mode)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"❌ Failed to save user preferences: {e}")
        return False
    finally:
        conn.close()

def get_user_preferences(session_id):
    """Get user preferences from database"""
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_preferences WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return None
    
    # Parse JSON strings back to lists
    preferences = dict(row)
    if preferences.get("preferred_categories"):
        preferences["preferred_categories"] = json.loads(preferences["preferred_categories"])
    if preferences.get("last_viewed_isbns"):
        preferences["last_viewed_isbns"] = json.loads(preferences["last_viewed_isbns"])
    
    return preferences

def save_book_metadata(isbn, title, author, details=None, page_count=None, language=None, publication_date=None):
    """Save book metadata to database for faster access"""
    conn = db_conn()
    cur = conn.cursor()
    
    try:
        cur.execute(
            """INSERT OR REPLACE INTO book_metadata 
               (isbn, title, author, details, page_count, language, publication_date, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (isbn, title, author, details, page_count, language, publication_date)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"❌ Failed to save book metadata: {e}")
        return False
    finally:
        conn.close()

def get_book_metadata(isbn):
    """Get book metadata from database"""
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM book_metadata WHERE isbn = ?", (isbn,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def save_search_history(session_id, keyword, result_count):
    """Save search history to database"""
    conn = db_conn()
    cur = conn.cursor()
    
    try:
        cur.execute(
            """INSERT INTO search_history (session_id, keyword, result_count)
               VALUES (?, ?, ?)""",
            (session_id, keyword, result_count)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"❌ Failed to save search history: {e}")
        return False
    finally:
        conn.close()

def get_search_history(session_id, limit=5):
    """Get search history from database"""
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT keyword, result_count, created_at FROM search_history WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# -------------------------- NYT API Request --------------------------
def fetch_books(category_id, force=False):
    """Fetch books from NYT API with caching and rate limiting"""
    if not NYT_API_KEY:
        return []
    
    # Check rate limiting
    if not check_rate_limit():
        logger.warning(f"⚠️ Rate limit exceeded for {category_id}")
        return get_cached_data(category_id) or []
    
    # Use cache if available and not forced
    if not force and is_cache_valid(category_id):
        return get_cached_data(category_id)
    
    url = f"{API_BASE_URL}/{category_id}.json"
    lock_file = CACHE_DIR / "api_lock"
    
    with open(lock_file, "w") as f:
        try:
            # 这里的 fcntl.flock 在 Windows 上是空操作（no-op），但在 Unix 上是真实的文件锁。
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, BlockingIOError):
            logger.info(f"⚠️ Another process is fetching {category_id}, waiting for cache")
            time.sleep(2)
            return get_cached_data(category_id) or []
        
        try:
            # Check cache again after acquiring lock
            if not force and is_cache_valid(category_id):
                return get_cached_data(category_id)
            
            logger.info(f"⏳ Fetching {CATEGORIES[category_id]} from API...")
            time.sleep(1)  # Basic delay to reduce rate limiting
            
            response = requests.get(url, params={"api-key": NYT_API_KEY}, timeout=15)
            
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 5))
                logger.warning(f"⚠️ NYT API rate limited. Waiting {retry_after}s")
                time.sleep(retry_after)
                response = requests.get(url, params={"api-key": NYT_API_KEY}, timeout=15)
            
            response.raise_for_status()
            data = response.json()
            results = data.get("results", {})
            raw_books = results.get("books", [])
            
            # Process books in parallel for better performance
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                # Create future tasks
                future_to_book = {
                    executor.submit(process_book_details, book_data, category_id, results): book_data 
                    for book_data in raw_books
                }
                
                # Collect results as they complete
                processed_books = []
                for future in as_completed(future_to_book):
                    try:
                        book = future.result()
                        if book:
                            processed_books.append(book)
                    except Exception as e:
                        logger.error(f"Error processing book: {e}")
            
            # Sort by rank
            processed_books.sort(key=lambda x: x.get("rank", 0))
            
            # Save to cache
            save_cache_data(category_id, processed_books)
            logger.info(f"✅ Successfully fetched {len(processed_books)} books for {CATEGORIES[category_id]}")
            return processed_books
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch/process data for {CATEGORIES[category_id]}: {e}")
            return []
        finally:
            # 这里的 fcntl.flock 在 Windows 上是空操作（no-op）
            fcntl.flock(f, fcntl.LOCK_UN)

def process_book_details(book_data, category_id, results):
    """Process individual book details (runs in thread pool)"""
    isbn = book_data.get("primary_isbn13") or book_data.get("primary_isbn10", "")
    
    # Check if we have cached metadata
    cached_metadata = get_book_metadata(isbn)
    if cached_metadata:
        supplement = {
            "publication_dt": cached_metadata.get("publication_date"),
            "details": cached_metadata.get("details"),
            "page_count": cached_metadata.get("page_count"),
            "language": cached_metadata.get("language")
        }
    else:
        # Fetch supplement info and cache it
        supplement = fetch_supplement_info(isbn)
        if isbn:
            save_book_metadata(
                isbn=isbn,
                title=book_data.get("title", ""),
                author=book_data.get("author", ""),
                details=supplement.get("details"),
                page_count=supplement.get("page_count"),
                language=supplement.get("language"),
                publication_date=supplement.get("publication_dt")
            )
    
    # Extract buy links
    buy_links = [
        {"name": link.get("name", ""), "url": link.get("url", "")}
        for link in book_data.get("buy_links", [])
    ]
    
    # FIX: Handle price value of 0
    price_value = book_data.get("price")
    try:
        # If price can be converted to a float and is greater than 0, use it. Otherwise, "未知".
        final_price = str(price_value) if price_value and float(price_value) > 0 else "未知"
    except (ValueError, TypeError):
        final_price = "未知"

    return {
        "id": isbn,
        "title": book_data.get("title", "Unknown Title"),
        "author": book_data.get("author", "Unknown Author"),
        "publisher": book_data.get("publisher", "Unknown Publisher"),
        "cover": get_cached_image_url(book_data.get("book_image")),
        "list_name": results.get("list_name", "Unknown List"),
        "category_id": category_id,
        "category_name": CATEGORIES[category_id],
        "rank": book_data.get("rank", 0),
        "weeks_on_list": book_data.get("weeks_on_list", 0),
        "rank_last_week": book_data.get("rank_last_week", "无"),
        "published_date": results.get("published_date", "Unknown"),
        "description": book_data.get("description", "No summary available."),
        "details": supplement.get("details", "No detailed description available."),
        "publication_dt": supplement.get("publication_dt", "Unknown"),
        "page_count": supplement.get("page_count", "Unknown"),
        "language": supplement.get("language", "Unknown"),
        "buy_links": buy_links,
        "isbn13": book_data.get("primary_isbn13", ""),
        "isbn10": book_data.get("primary_isbn10", ""),
        "price": final_price
    }

# -------------------------- Routes --------------------------
@app.route('/')
def index():
    """Home page"""
    return render_template('index.html', categories=CATEGORIES)

@app.route('/api/books/<category>')
def api_books(category):
    """Get books API (supports single category or all)"""
    try:
        # Get session ID for user preferences
        session_id = request.args.get('session_id') or request.remote_addr
        
        if category == 'all':
            # Return all categories data
            all_books = {}
            for cat_id in CATEGORY_ORDER:
                all_books[cat_id] = fetch_books(cat_id)
            
            # Save user preference for all categories
            save_user_preferences(session_id, preferred_categories=CATEGORY_ORDER)
            
            return jsonify({
                'success': True,
                'books': all_books,
                'categories': CATEGORIES,
                'category_order': CATEGORY_ORDER,
                'latest_update': get_latest_cache_time()
            })
        else:
            # Return single category data
            if category not in CATEGORIES:
                return jsonify({'success': False, 'message': '无效的分类'}), 400
            
            books = fetch_books(category)
            
            # Save user preference for this category
            save_user_preferences(session_id, preferred_categories=[category])
            
            return jsonify({
                'success': True,
                'books': books,
                'category_name': CATEGORIES[category],
                'latest_update': get_latest_cache_time()
            })
    except Exception as e:
        logger.error(f"API错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/search')
def api_search():
    """Search books by title or author"""
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({'success': False, 'message': '搜索关键词不能为空'})
    
    try:
        # Get session ID for user preferences
        session_id = request.args.get('session_id') or request.remote_addr
        
        # Search across all categories
        results = []
        for cat_id in CATEGORY_ORDER:
            books = fetch_books(cat_id)
            keyword_lower = keyword.lower()
            for book in books:
                if (keyword_lower in book['title'].lower() or 
                    keyword_lower in book['author'].lower()):
                    results.append(book)
        
        # Save search history
        save_search_history(session_id, keyword, len(results))
        
        # Save search results to user preferences
        if results:
            viewed_isbns = [book['id'] for book in results[:5]]  # Save top 5
            save_user_preferences(session_id, last_viewed_isbns=viewed_isbns)
        
        return jsonify({
            'success': True,
            'books': results,
            'count': len(results),
            'latest_update': get_latest_cache_time()
        })
    except Exception as e:
        logger.error(f"搜索错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/search/history')
def api_search_history():
    """Get search history for current user"""
    try:
        session_id = request.args.get('session_id') or request.remote_addr
        history = get_search_history(session_id)
        return jsonify({
            'success': True,
            'history': history
        })
    except Exception as e:
        logger.error(f"获取搜索历史错误: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/user/preferences', methods=['GET', 'POST'])
def user_preferences():
    """Get or update user preferences"""
    try:
        session_id = request.args.get('session_id') or request.remote_addr
        
        if request.method == 'POST':
            data = request.get_json() or {}
            preferred_categories = data.get('preferred_categories')
            last_viewed_isbns = data.get('last_viewed_isbns')
            view_mode = data.get('view_mode')
            
            save_user_preferences(session_id, preferred_categories, last_viewed_isbns, view_mode)
            return jsonify({'success': True, 'message': 'Preferences saved'})
        
        else:  # GET
            preferences = get_user_preferences(session_id)
            return jsonify({
                'success': True,
                'preferences': preferences or {}
            })
            
    except Exception as e:
        logger.error(f"User preferences error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/export/<category>')
def export_csv(category):
    """Export books data as CSV"""
    try:
        # Collect data to export
        if category == 'all':
            all_books = []
            for cat_id in CATEGORY_ORDER:
                all_books.extend(fetch_books(cat_id))
        else:
            if category not in CATEGORIES:
                return jsonify({'success': False, 'message': '无效的分类'}), 400
            all_books = fetch_books(category)
        
        # Generate CSV content
        output = StringIO()
        writer = csv.writer(output)
        
        # FIX: Removed ISBN-10 from header
        writer.writerow([
            '分类', '书名', '作者', '出版社', '当前排名', 
            '上周排名', '上榜周数', '出版日期', '页数', 
            '语言', 'ISBN-13', '价格'
        ])
        
        # Data rows
        for book in all_books:
            # FIX: Removed ISBN-10 from data row
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
                book.get('price', '')
            ])
        
        # Prepare response (handle Chinese encoding)
        output.seek(0)
        csv_content = output.getvalue()
        response_data = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')  # Add BOM
        
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
    """Serve cached images"""
    return send_from_directory(IMAGE_CACHE_DIR, filename)

@app.route('/static/<path:path>')
def send_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

# -------------------------- Startup --------------------------
if __name__ == '__main__':
    # Production settings: disable debug, bind to 0.0.0.0 for external access
    app.run(host="0.0.0.0", port=8000, debug=False)