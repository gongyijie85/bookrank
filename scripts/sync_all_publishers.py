"""
同步所有出版社的新书数据

混合架构：先尝试传统 requests，失败后自动降级到 Crawl4AI（如果已安装）
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.services.new_book_service import NewBookService
from app.models.database import db
from app.models.new_book import Publisher, NewBook

def main():
    """主函数"""
    print("🚀 开始同步所有出版社...")
    
    # 创建 Flask 应用
    app = create_app()
    
    with app.app_context():
        # 初始化数据库表
        print("📦 初始化数据库...")
        db.create_all()
        
        # 初始化出版社服务
        service = NewBookService()
        
        # 初始化默认出版社
        print("📚 初始化出版社...")
        service.init_publishers()
        
        # 获取所有启用的出版社
        publishers = service.get_publishers(active_only=True)
        print(f"\n📊 准备同步 {len(publishers)} 个出版社...")
        
        # 同步每个出版社
        results = []
        for publisher in publishers:
            print(f"\n{'='*60}")
            print(f"🔍 正在同步: {publisher.name} ({publisher.name_en})")
            print(f"{'='*60}")
            
            try:
                # 每个出版社先同步 20 本（避免耗时太长）
                result = service.sync_publisher_books(
                    publisher.id,
                    category=None,
                    max_books=20,
                    translate=False
                )
                results.append(result)
                
                if result['success']:
                    print(f"✅ 同步成功!")
                    print(f"   总计: {result['total']}")
                    print(f"   新增: {result['added']}")
                    print(f"   更新: {result['updated']}")
                    print(f"   跳过: {result['skipped']}")
                    print(f"   错误: {result['errors']}")
                else:
                    print(f"❌ 同步失败: {result.get('error', '未知错误')}")
                    
            except Exception as e:
                print(f"❌ 同步异常: {e}")
                results.append({
                    'success': False,
                    'publisher': publisher.name_en,
                    'error': str(e)
                })
        
        # 汇总统计
        print(f"\n{'='*60}")
        print("📊 同步完成汇总")
        print(f"{'='*60}")
        
        total_added = sum(r.get('added', 0) for r in results if r['success'])
        total_updated = sum(r.get('updated', 0) for r in results if r['success'])
        total_skipped = sum(r.get('skipped', 0) for r in results if r['success'])
        total_errors = sum(r.get('errors', 0) for r in results if r['success'])
        
        print(f"📈 总计新增: {total_added} 本")
        print(f"📈 总计更新: {total_updated} 本")
        print(f"📈 总计跳过: {total_skipped} 本")
        print(f"📈 总计错误: {total_errors} 本")
        
        # 最终统计
        print(f"\n{'='*60}")
        print("📖 最终数据库统计")
        print(f"{'='*60}")
        
        total_books = NewBook.query.count()
        print(f"📚 数据库总书籍数: {total_books}")
        
        for pub in publishers:
            count = NewBook.query.filter_by(publisher_id=pub.id).count()
            print(f"  - {pub.name}: {count} 本")
        
        print(f"\n✅ 全部完成！")

if __name__ == "__main__":
    main()
