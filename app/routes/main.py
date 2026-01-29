import re
from pathlib import Path

from flask import Blueprint, render_template, send_from_directory, abort
from werkzeug.utils import secure_filename

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """首页"""
    from flask import current_app
    return render_template('index.html', categories=current_app.config['CATEGORIES'])


@main_bp.route('/cache/images/<filename>')
def cached_image(filename: str):
    """
    提供缓存的图片文件
    
    安全注意：验证文件名格式，防止路径遍历攻击
    """
    # 验证文件名格式（只允许MD5哈希格式的文件名）
    if not re.match(r'^[a-f0-9]{32}\.jpg$', filename):
        abort(404)
    
    # 使用secure_filename进一步确保安全
    safe_filename = secure_filename(filename)
    
    from flask import current_app
    cache_dir = current_app.config.get('IMAGE_CACHE_DIR', Path('cache/images'))
    
    return send_from_directory(cache_dir, safe_filename)


@main_bp.route('/static/<path:path>')
def send_static(path: str):
    """提供静态文件"""
    return send_from_directory('static', path)
