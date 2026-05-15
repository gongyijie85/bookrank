"""
批量翻译脚本

用于批量翻译所有图书的描述和详细信息
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.services.zhipu_translation_service import get_translation_service
from app.services import BookService
from app.models.database import db
from app.models.schemas import BookMetadata


def batch_translate_all_books():
    """批量翻译所有图书"""
    app = create_app()
    
    with app.app_context():
        # 获取图书服务
        book_service = app.extensions.get('book_service')
        if not book_service:
            print("错误: 无法获取图书服务")
            return
        
        translation_service = get_translation_service(app=app)
        
        # 获取所有分类
        categories = app.config.get('CATEGORIES', {})
        
        total_books = 0
        translated_count = 0
        skipped_count = 0
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
                    
                    # 检查是否已有翻译
                    existing = BookMetadata.query.get(book.isbn13 or book.isbn10)
                    if existing and existing.description_zh and existing.details_zh:
                        print(f"    已翻译，跳过")
                        skipped_count += 1
                        continue
                    
                    description_zh = None
                    details_zh = None
                    
                    # 翻译描述
                    if book.description and book.description not in ['No summary available.', '暂无简介', '']:
                        print(f"    翻译描述...", end=" ")
                        description_zh = translation_service.translate(
                            book.description, 
                            source_lang='en', 
                            target_lang='zh'
                        )
                        if description_zh:
                            print("✓")
                        else:
                            print("✗")
                            failed_count += 1
                    
                    # 翻译详细信息
                    if book.details and book.details not in ['No detailed description available.', '暂无详细介绍', '']:
                        print(f"    翻译详情...", end=" ")
                        details_zh = translation_service.translate(
                            book.details,
                            source_lang='en',
                            target_lang='zh'
                        )
                        if details_zh:
                            print("✓")
                        else:
                            print("✗")
                            failed_count += 1
                    
                    # 保存翻译结果
                    if description_zh or details_zh:
                        if book_service.save_book_translation(
                            book.isbn13 or book.isbn10,
                            description_zh=description_zh,
                            details_zh=details_zh
                        ):
                            translated_count += 1
                            print(f"    已保存到数据库")
                        else:
                            failed_count += 1
                            print(f"    保存失败")
                
            except Exception as e:
                print(f"  错误: {e}")
                failed_count += 1
        
        # 显示统计信息
        print("\n" + "=" * 60)
        print("翻译完成!")
        print("=" * 60)
        print(f"总图书数: {total_books}")
        print(f"已翻译(跳过): {skipped_count}")
        print(f"新翻译成功: {translated_count}")
        print(f"失败数量: {failed_count}")
        
        # 显示缓存统计（多翻译服务没有缓存统计）
        print(f"\n翻译完成统计:")
        print(f"  成功: {translated_count}")
        print(f"  失败: {failed_count}")


def translate_single_book(isbn: str):
    """翻译单本图书"""
    app = create_app()
    
    with app.app_context():
        book_service = app.extensions.get('book_service')
        if not book_service:
            print("错误: 无法获取图书服务")
            return
        
        translation_service = get_translation_service(app=app)
        
        # 搜索图书
        found = False
        for category_id in app.config.get('CATEGORIES', {}).keys():
            books = book_service.get_books_by_category(category_id)
            for book in books:
                if book.isbn13 == isbn or book.isbn10 == isbn:
                    found = True
                    print(f"找到图书: {book.title}")
                    
                    description_zh = None
                    details_zh = None
                    
                    # 翻译描述
                    if book.description:
                        print("翻译描述...")
                        description_zh = translation_service.translate(book.description)
                        if description_zh:
                            print(f"原文: {book.description[:100]}...")
                            print(f"译文: {description_zh[:100]}...")
                    
                    # 翻译详情
                    if book.details:
                        print("\n翻译详情...")
                        details_zh = translation_service.translate(book.details)
                        if details_zh:
                            print(f"原文: {book.details[:100]}...")
                            print(f"译文: {details_zh[:100]}...")
                    
                    # 保存翻译
                    if description_zh or details_zh:
                        if book_service.save_book_translation(
                            isbn,
                            description_zh=description_zh,
                            details_zh=details_zh
                        ):
                            print("\n翻译已保存到数据库")
                        else:
                            print("\n保存失败")
                    
                    break
            if found:
                break
        
        if not found:
            print(f"未找到ISBN为 {isbn} 的图书")


def show_cache_stats():
    """显示翻译缓存统计"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("翻译服务状态")
        print("=" * 60)
        print("使用多翻译API轮询服务:")
        print("  - MyMemory API (主)")
        print("  - 百度翻译API (备用)")
        
        # 数据库中的翻译统计
        metadata_count = BookMetadata.query.filter(
            db.or_(
                BookMetadata.description_zh.isnot(None),
                BookMetadata.details_zh.isnot(None)
            )
        ).count()
        print(f"\n数据库中已翻译图书: {metadata_count}")


def show_translation_status():
    """显示翻译状态"""
    app = create_app()
    
    with app.app_context():
        book_service = app.extensions.get('book_service')
        if not book_service:
            print("错误: 无法获取图书服务")
            return
        
        categories = app.config.get('CATEGORIES', {})
        
        total_books = 0
        translated_books = 0
        
        print("=" * 60)
        print("翻译状态检查")
        print("=" * 60)
        
        for category_id, category_name in categories.items():
            try:
                books = book_service.get_books_by_category(category_id)
                cat_total = len(books)
                cat_translated = 0
                
                for book in books:
                    metadata = BookMetadata.query.get(book.isbn13 or book.isbn10)
                    if metadata and (metadata.description_zh or metadata.details_zh):
                        cat_translated += 1
                
                total_books += cat_total
                translated_books += cat_translated
                
                print(f"{category_name}: {cat_translated}/{cat_total} 已翻译")
                
            except Exception as e:
                print(f"{category_name}: 错误 - {e}")
        
        print("-" * 60)
        if total_books > 0:
            print(f"总计: {translated_books}/{total_books} 已翻译 ({translated_books/total_books*100:.1f}%)")
        else:
            print(f"总计: {translated_books}/{total_books} 已翻译")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='批量翻译图书工具')
    parser.add_argument('--all', action='store_true', help='翻译所有图书')
    parser.add_argument('--isbn', type=str, help='翻译指定ISBN的图书')
    parser.add_argument('--stats', action='store_true', help='显示缓存统计')
    parser.add_argument('--status', action='store_true', help='显示翻译状态')
    
    args = parser.parse_args()
    
    if args.all:
        batch_translate_all_books()
    elif args.isbn:
        translate_single_book(args.isbn)
    elif args.stats:
        show_cache_stats()
    elif args.status:
        show_translation_status()
    else:
        parser.print_help()
