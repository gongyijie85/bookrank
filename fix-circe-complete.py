#!/usr/bin/env python3
"""
完整修复CIRCE书名翻译
包括清理缓存和验证修复
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models.schemas import BookMetadata, TranslationCache
from app.models import db

def fix_circe_complete():
    """完整修复CIRCE书名翻译"""
    app = create_app()
    
    with app.app_context():
        print("=== 完整修复CIRCE书名翻译 ===")
        
        # 1. 修复BookMetadata中的数据
        print("1. 修复BookMetadata数据:")
        circe_metadata = BookMetadata.query.filter_by(isbn='9780316556323').first()
        
        if circe_metadata:
            print(f"   找到CIRCE数据: {circe_metadata.title}")
            if circe_metadata.title_zh == '循环经济委员会':
                print("   ❌ 确认翻译错误，正在修复...")
                circe_metadata.title_zh = '喀耳刻'
                print("   ✅ 已修复中文标题为: 喀耳刻")
            elif circe_metadata.title_zh == '喀耳刻':
                print("   ✅ 中文标题已正确")
            else:
                print(f"   ⚠️ 中文标题为其他内容: {circe_metadata.title_zh}")
        else:
            print("   未找到CIRCE数据，正在创建...")
            new_metadata = BookMetadata(
                isbn='9780316556323',
                title='CIRCE',
                title_zh='喀耳刻',
                author='Madeline Miller',
                language='en'
            )
            db.session.add(new_metadata)
            print("   ✅ 已创建CIRCE的BookMetadata记录")
        
        # 2. 清理翻译缓存中的错误数据
        print("\n2. 清理翻译缓存:")
        wrong_caches = TranslationCache.query.filter(
            TranslationCache.translated_text.like('%循环经济委员会%')
        ).all()
        
        if wrong_caches:
            print(f"   找到 {len(wrong_caches)} 条错误的翻译缓存")
            for cache in wrong_caches:
                print(f"   删除缓存ID: {cache.id}")
                db.session.delete(cache)
            print("   ✅ 已删除所有错误的翻译缓存")
        else:
            print("   未找到错误的翻译缓存")
        
        # 3. 提交更改
        try:
            db.session.commit()
            print("\n3. ✅ 所有更改已提交到数据库")
        except Exception as e:
            db.session.rollback()
            print(f"\n3. ❌ 提交更改失败: {e}")
            return False
        
        # 4. 验证修复
        print("\n4. 验证修复:")
        circe_metadata = BookMetadata.query.filter_by(isbn='9780316556323').first()
        if circe_metadata:
            print(f"   中文标题: {circe_metadata.title_zh}")
            if circe_metadata.title_zh == '喀耳刻':
                print("   ✅ 修复验证成功")
                
                # 5. 提供下一步建议
                print("\n5. 下一步操作:")
                print("   1. 重启应用程序以清除内存缓存")
                print("   2. 访问 https://bookrank-ckml.onrender.com/book/10?category=trade-fiction-paperback")
                print("   3. 验证书名是否显示为'喀耳刻'")
                print("   4. 运行测试脚本验证: node test-circe-translation.js")
                
                return True
            else:
                print("   ❌ 修复验证失败")
                return False
        else:
            print("   ❌ 未找到CIRCE数据")
            return False

if __name__ == '__main__':
    success = fix_circe_complete()
    sys.exit(0 if success else 1)