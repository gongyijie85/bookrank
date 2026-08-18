#!/usr/bin/env python3
"""
验证CIRCE书名翻译修复
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models.schemas import BookMetadata

def verify_fix():
    """验证修复"""
    app = create_app()
    
    with app.app_context():
        print("=== 验证CIRCE书名翻译修复 ===")
        
        # 检查BookMetadata中的CIRCE数据
        circe_metadata = BookMetadata.query.filter_by(isbn='9780316556323').first()
        
        if circe_metadata:
            print(f"1. 找到CIRCE数据:")
            print(f"   ISBN: {circe_metadata.isbn}")
            print(f"   标题: {circe_metadata.title}")
            print(f"   中文标题: {circe_metadata.title_zh}")
            
            if circe_metadata.title_zh == '喀耳刻':
                print("   ✅ 中文标题正确")
                print("\n=== 修复验证成功 ===")
                return True
            else:
                print(f"   ❌ 中文标题错误: {circe_metadata.title_zh}")
                return False
        else:
            print("❌ 未找到CIRCE数据")
            return False

if __name__ == '__main__':
    success = verify_fix()
    sys.exit(0 if success else 1)