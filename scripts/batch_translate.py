"""
批量翻译脚本

用于批量翻译所有图书的描述和详细信息
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.services.translation_service import LibreTranslateService
from app.services import BookService
from app.models.database import db


def batch_translate_all_books():
    """批量翻译所有图书"""
    app = create_app()
    
    with app.app_context():
        # 获取图书服务
        book_service = app.extensions.get('book_service')
        if not book_service:
            print("错误: 无法获取图书服务")
            return
        
        # 创建翻译服务
        translation_service = LibreTranslateService(delay=1.0)
        
        # 获取所有分类
        categories = app.config.get('CATEGORIES', {})
        
        total_books = 0
        translated_count = 0
        failed_count = 0
        
        print("=" * 60)
        print("开始批量翻译图书")
        print("=" * 60)
        
        for category_id, category_name in categories.items():
            print(f"\n📚 处理分类: {category_name} ({category_id})")
            print("-" * 60)
            
            try:
                # 获取该分类的图书
                books = book_service.get_books_by_category(category_id)
                
                for i, book in enumerate(books):
                    total_books += 1
                    print(f"\n  [{i+1}/{len(books)}] {book.title}")
                    
                    # 翻译描述
                    if book.description and book.description not in ['No summary available.', '暂无简介']:
                        print(f"    翻译描述...", end=" ")
                        translated_desc = translation_service.translate(
                            book.description, 
                            source_lang='en', 
                            target_lang='zh'
                        )
                        if translated_desc:
                            print("✓")
                            translated_count += 1
                        else:
                            print("✗")
                            failed_count += 1
                    
                    # 翻译详细信息
                    if book.details and book.details not in ['No detailed description available.', '暂无详细介绍']:
                        print(f"    翻译详情...", end=" ")
                        translated_details = translation_service.translate(
                            book.details,
                            source_lang='en',
                            target_lang='zh'
                        )
                        if translated_details:
                            print("✓")
                            translated_count += 1
                        else:
                            print("✗")
                            failed_count += 1
                
            except Exception as e:
                print(f"  错误: {e}")
                failed_count += 1
        
        # 显示统计信息
        print("\n" + "=" * 60)
        print("翻译完成!")
        print("=" * 60)
        print(f"总图书数: {total_books}")
        print(f"成功翻译: {translated_count}")
        print(f"失败数量: {failed_count}")
        
        # 显示缓存统计
        cache_stats = translation_service.get_cache_stats()
        print(f"\n缓存统计:")
        print(f"  缓存条目: {cache_stats['total_entries']}")
        print(f"  总使用次数: {cache_stats['total_uses']}")
        print(f"  平均使用: {cache_stats['avg_uses_per_entry']}")


def translate_single_book(isbn: str):
    """翻译单本图书"""
    app = create_app()
    
    with app.app_context():
        book_service = app.extensions.get('book_service')
        if not book_service:
            print("错误: 无法获取图书服务")
            return
        
        translation_service = LibreTranslateService()
        
        # 搜索图书
        found = False
        for category_id in app.config.get('CATEGORIES', {}).keys():
            books = book_service.get_books_by_category(category_id)
            for book in books:
                if book.isbn13 == isbn or book.isbn10 == isbn:
                    found = True
                    print(f"找到图书: {book.title}")
                    
                    # 翻译描述
                    if book.description:
                        print("翻译描述...")
                        result = translation_service.translate(book.description)
                        if result:
                            print(f"原文: {book.description[:100]}...")
                            print(f"译文: {result[:100]}...")
                    
                    # 翻译详情
                    if book.details:
                        print("\n翻译详情...")
                        result = translation_service.translate(book.details)
                        if result:
                            print(f"原文: {book.details[:100]}...")
                            print(f"译文: {result[:100]}...")
                    
                    break
            if found:
                break
        
        if not found:
            print(f"未找到ISBN为 {isbn} 的图书")


def show_cache_stats():
    """显示翻译缓存统计"""
    app = create_app()
    
    with app.app_context():
        translation_service = LibreTranslateService()
        stats = translation_service.get_cache_stats()
        
        print("=" * 60)
        print("翻译缓存统计")
        print("=" * 60)
        print(f"缓存条目数: {stats['total_entries']}")
        print(f"总使用次数: {stats['total_uses']}")
        print(f"平均每条目使用: {stats['avg_uses_per_entry']}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='批量翻译图书工具')
    parser.add_argument('--all', action='store_true', help='翻译所有图书')
    parser.add_argument('--isbn', type=str, help='翻译指定ISBN的图书')
    parser.add_argument('--stats', action='store_true', help='显示缓存统计')
    
    args = parser.parse_args()
    
    if args.all:
        batch_translate_all_books()
    elif args.isbn:
        translate_single_book(args.isbn)
    elif args.stats:
        show_cache_stats()
    else:
        parser.print_help()
