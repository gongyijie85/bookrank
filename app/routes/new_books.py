"""
新书速递 API 路由

提供新书数据的查询、同步、导出等功能。
"""
import csv
import logging
from io import StringIO, BytesIO
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, jsonify, request, make_response, current_app

from ..models.database import db
from ..models.new_book import NewBook, Publisher
from ..utils.exceptions import APIException
from ..services.new_book_service import NewBookService

logger = logging.getLogger(__name__)

new_books_bp = Blueprint('new_books', __name__, url_prefix='/api/new-books')


class APIResponse:
    """统一API响应格式"""

    @staticmethod
    def success(data=None, message="Success", status_code=200):
        response = {
            'success': True,
            'data': data,
            'message': message
        }
        return jsonify(response), status_code

    @staticmethod
    def error(message="Error", status_code=400, errors=None):
        response = {
            'success': False,
            'message': message
        }
        if errors:
            response['errors'] = errors
        return jsonify(response), status_code


def get_new_book_service() -> NewBookService:
    """获取新书服务实例"""
    return NewBookService()


# ==================== 出版社接口 ====================

@new_books_bp.route('/publishers')
def get_publishers():
    """获取出版社列表"""
    try:
        service = get_new_book_service()
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        
        publishers = service.get_publishers(active_only=active_only)
        
        return APIResponse.success(data={
            'publishers': [p.to_dict() for p in publishers]
        })
    
    except Exception as e:
        logger.error(f"获取出版社列表失败: {e}", exc_info=True)
        return APIResponse.error('获取出版社列表失败', 500)


@new_books_bp.route('/publishers/<int:publisher_id>')
def get_publisher(publisher_id: int):
    """获取单个出版社详情"""
    try:
        service = get_new_book_service()
        publisher = service.get_publisher(publisher_id)
        
        if not publisher:
            return APIResponse.error('出版社不存在', 404)
        
        return APIResponse.success(data={
            'publisher': publisher.to_dict()
        })
    
    except Exception as e:
        logger.error(f"获取出版社详情失败: {e}", exc_info=True)
        return APIResponse.error('获取出版社详情失败', 500)


@new_books_bp.route('/publishers/<int:publisher_id>/status', methods=['POST'])
def update_publisher_status(publisher_id: int):
    """更新出版社状态"""
    try:
        if not request.is_json:
            return APIResponse.error('Content-Type must be application/json', 400)
        
        data = request.get_json() or {}
        is_active = data.get('is_active')
        
        if is_active is None:
            return APIResponse.error('缺少 is_active 参数', 400)
        
        service = get_new_book_service()
        success = service.update_publisher_status(publisher_id, is_active)
        
        if not success:
            return APIResponse.error('出版社不存在', 404)
        
        return APIResponse.success(message=f"出版社已{'启用' if is_active else '禁用'}")
    
    except Exception as e:
        logger.error(f"更新出版社状态失败: {e}", exc_info=True)
        db.session.rollback()
        return APIResponse.error('更新出版社状态失败', 500)


# ==================== 新书接口 ====================

@new_books_bp.route('')
def get_new_books():
    """获取新书列表"""
    try:
        service = get_new_book_service()
        
        # 获取筛选参数
        publisher_id = request.args.get('publisher_id', type=int)
        category = request.args.get('category')
        days = request.args.get('days', 30, type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # 限制参数范围
        days = min(max(1, days), 365)
        page = min(max(1, page), 10000)
        per_page = min(max(1, per_page), 50)
        
        books, total = service.get_new_books(
            publisher_id=publisher_id,
            category=category,
            days=days,
            page=page,
            per_page=per_page
        )
        
        return APIResponse.success(data={
            'books': [b.to_dict() for b in books],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
    
    except Exception as e:
        logger.error(f"获取新书列表失败: {e}", exc_info=True)
        return APIResponse.error('获取新书列表失败', 500)


@new_books_bp.route('/<int:book_id>')
def get_book_detail(book_id: int):
    """获取新书详情"""
    try:
        service = get_new_book_service()
        book = service.get_book(book_id)
        
        if not book:
            return APIResponse.error('图书不存在', 404)
        
        return APIResponse.success(data={
            'book': book.to_dict()
        })
    
    except Exception as e:
        logger.error(f"获取图书详情失败: {e}", exc_info=True)
        return APIResponse.error('获取图书详情失败', 500)


@new_books_bp.route('/search')
def search_new_books():
    """搜索新书"""
    try:
        keyword = request.args.get('keyword', '').strip()
        
        if not keyword:
            return APIResponse.error('搜索关键词不能为空', 400)
        
        if len(keyword) > 100:
            return APIResponse.error('关键词长度不能超过100个字符', 400)
        
        service = get_new_book_service()
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # 限制参数范围
        page = min(max(1, page), 10000)
        per_page = min(max(1, per_page), 50)
        
        books, total = service.search_books(keyword, page, per_page)
        
        return APIResponse.success(data={
            'keyword': keyword,
            'books': [b.to_dict() for b in books],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
    
    except Exception as e:
        logger.error(f"搜索新书失败: {e}", exc_info=True)
        return APIResponse.error('搜索失败', 500)


# ==================== 分类接口 ====================

@new_books_bp.route('/categories')
def get_categories():
    """获取分类列表"""
    try:
        service = get_new_book_service()
        categories = service.get_categories()
        
        return APIResponse.success(data={
            'categories': categories
        })
    
    except Exception as e:
        logger.error(f"获取分类列表失败: {e}", exc_info=True)
        return APIResponse.error('获取分类列表失败', 500)


# ==================== 同步接口 ====================

@new_books_bp.route('/sync', methods=['POST'])
def sync_all_publishers():
    """同步所有出版社新书"""
    try:
        service = get_new_book_service()
        
        # 先确保出版社已初始化
        service.init_publishers()
        
        max_books = request.args.get('max_books', 30, type=int)
        max_books = min(max(1, max_books), 100)
        
        results = service.sync_all_publishers(max_books_per_publisher=max_books)
        
        # 统计结果
        total_added = sum(r.get('added', 0) for r in results)
        total_updated = sum(r.get('updated', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)
        
        return APIResponse.success(data={
            'results': results,
            'summary': {
                'total_publishers': len(results),
                'total_added': total_added,
                'total_updated': total_updated,
                'total_errors': total_errors
            }
        })
    
    except Exception as e:
        logger.error(f"同步新书失败: {e}", exc_info=True)
        return APIResponse.error(f'同步失败: {str(e)}', 500)


@new_books_bp.route('/sync/<int:publisher_id>', methods=['POST'])
def sync_publisher(publisher_id: int):
    """同步指定出版社新书"""
    try:
        service = get_new_book_service()
        
        max_books = request.args.get('max_books', 50, type=int)
        max_books = min(max(1, max_books), 100)
        
        result = service.sync_publisher_books(publisher_id, max_books=max_books)
        
        if not result.get('success'):
            return APIResponse.error(result.get('error', '同步失败'), 400)
        
        return APIResponse.success(data=result)
    
    except Exception as e:
        logger.error(f"同步出版社新书失败: {e}", exc_info=True)
        return APIResponse.error(f'同步失败: {str(e)}', 500)


# ==================== 统计接口 ====================

@new_books_bp.route('/statistics')
def get_statistics():
    """获取统计数据"""
    try:
        service = get_new_book_service()
        stats = service.get_statistics()
        
        return APIResponse.success(data=stats)
    
    except Exception as e:
        logger.error(f"获取统计数据失败: {e}", exc_info=True)
        return APIResponse.error('获取统计数据失败', 500)


# ==================== 导出接口 ====================

@new_books_bp.route('/export/excel')
def export_excel():
    """导出Excel格式"""
    try:
        service = get_new_book_service()
        
        # 获取筛选参数
        publisher_id = request.args.get('publisher_id', type=int)
        category = request.args.get('category')
        days = request.args.get('days', 30, type=int)
        
        days = min(max(1, days), 365)
        
        # 获取数据
        books, _ = service.get_new_books(
            publisher_id=publisher_id,
            category=category,
            days=days,
            page=1,
            per_page=1000
        )
        
        # 生成CSV（Excel兼容）
        output = StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow([
            '书名', '中文书名', '作者', '出版社', '分类',
            '出版日期', 'ISBN-13', 'ISBN-10', '价格', '页数', '语言',
            '简介', '中文简介', '来源链接'
        ])
        
        # 写入数据
        for book in books:
            writer.writerow([
                book.title,
                book.title_zh or '',
                book.author,
                book.publisher.name if book.publisher else '',
                book.category or '',
                book.publication_date.isoformat() if book.publication_date else '',
                book.isbn13 or '',
                book.isbn10 or '',
                book.price or '',
                book.page_count or '',
                book.language or '',
                book.description or '',
                book.description_zh or '',
                book.source_url or ''
            ])
        
        # 准备响应
        output.seek(0)
        csv_content = output.getvalue()
        response_data = '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')
        
        response = make_response(response_data)
        filename = f'新书速递_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response.headers["Content-Disposition"] = f"attachment; filename={quote(filename)}"
        response.headers["Content-type"] = "text/csv; charset=utf-8"
        
        return response
    
    except Exception as e:
        logger.error(f"导出Excel失败: {e}", exc_info=True)
        return APIResponse.error('导出失败', 500)


# ==================== 初始化接口 ====================

@new_books_bp.route('/init', methods=['POST'])
def init_publishers():
    """初始化出版社数据"""
    try:
        service = get_new_book_service()
        count = service.init_publishers()
        
        return APIResponse.success(data={
            'created_count': count
        }, message=f'成功初始化 {count} 个出版社')
    
    except Exception as e:
        logger.error(f"初始化出版社失败: {e}", exc_info=True)
        db.session.rollback()
        return APIResponse.error('初始化失败', 500)


# 错误处理器
@new_books_bp.errorhandler(404)
def not_found(error):
    return APIResponse.error('Resource not found', 404)


@new_books_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return APIResponse.error('Internal server error', 500)
