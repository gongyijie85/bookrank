#!/usr/bin/env python3
"""
直接修复CIRCE书名翻译
通过修改翻译服务的翻译结果来修复问题
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models.schemas import BookMetadata, TranslationCache
from app.utils.api_helpers import clean_translation_text

def fix_circe_translation():
    """修复CIRCE书名翻译"""
    app = create_app()
    
    with app.app_context():
        print("=== 修复CIRCE书名翻译 ===")
        
        # 1. 检查BookMetadata中是否有CIRCE数据
        circe_metadata = BookMetadata.query.filter_by(isbn='9780316556323').first()
        
        if circe_metadata:
            print(f"1. 找到BookMetadata中的CIRCE数据:")
            print(f"   ISBN: {circe_metadata.isbn}")
            print(f"   标题: {circe_metadata.title}")
            print(f"   中文标题: {circe_metadata.title_zh}")
            
            # 修复中文标题
            if circe_metadata.title_zh == '循环经济委员会':
                print("   ❌ 确认翻译错误，正在修复...")
                circe_metadata.title_zh = '喀耳刻'
                print("   ✅ 已修复中文标题为: 喀耳刻")
            elif circe_metadata.title_zh == '喀耳刻':
                print("   ✅ 中文标题已正确")
            else:
                print(f"   ⚠️ 中文标题为其他内容: {circe_metadata.title_zh}")
        else:
            print("1. BookMetadata中未找到CIRCE数据")
            
            # 创建新的BookMetadata记录
            print("   正在创建CIRCE的BookMetadata记录...")
            from app.models import db
            new_metadata = BookMetadata(
                isbn='9780316556323',
                title='CIRCE',
                title_zh='喀耳刻',
                author='Madeline Miller',
                language='en'
            )
            db.session.add(new_metadata)
            print("   ✅ 已创建CIRCE的BookMetadata记录")
        
        # 2. 检查TranslationCache中是否有错误的翻译
        wrong_caches = TranslationCache.query.filter(
            TranslationCache.source_text.like('%CIRCE%'),
            TranslationCache.translated_text.like('%循环经济委员会%')
        ).all()
        
        if wrong_caches:
            print(f"\n2. 找到 {len(wrong_caches)} 条错误的翻译缓存:")
            for cache in wrong_caches:
                print(f"   ID: {cache.id}")
                print(f"   源文本: {cache.source_text}")
                print(f"   翻译文本: {cache.translated_text}")
                
                # 修复翻译缓存
                if 'CIRCE' in cache.source_text:
                    cache.translated_text = cache.translated_text.replace('循环经济委员会', '喀耳刻')
                    print(f"   ✅ 已修复翻译缓存")
        else:
            print("\n2. 未找到错误的翻译缓存")
        
        # 3. 提交更改
        try:
            from app.models import db
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
                return True
            else:
                print("   ❌ 修复验证失败")
                return False
        else:
            print("   ❌ 未找到CIRCE数据")
            return False

if __name__ == '__main__':
    success = fix_circe_translation()
    sys.exit(0 if success else 1)