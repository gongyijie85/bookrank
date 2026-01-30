"""
测试免费翻译服务
"""

import sys
import os

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app.services.free_translation_service import (
    FreeTranslationService,
    GoogleTranslationService,
    LibreTranslatePublicService
)


def test_google_translate():
    """测试 Google Translate"""
    print("=" * 60)
    print("测试 Google Translate")
    print("=" * 60)
    
    service = GoogleTranslationService()
    
    test_texts = [
        "Hello, how are you?",
        "This is a book about artificial intelligence.",
        "The quick brown fox jumps over the lazy dog."
    ]
    
    for text in test_texts:
        print(f"\n原文: {text}")
        result = service.translate(text, source_lang='en', target_lang='zh')
        if result:
            print(f"译文: {result}")
        else:
            print("翻译失败")


def test_libre_translate():
    """测试 LibreTranslate"""
    print("\n" + "=" * 60)
    print("测试 LibreTranslate 公共实例")
    print("=" * 60)
    
    service = LibreTranslatePublicService()
    
    test_texts = [
        "Hello, world!",
        "This is a test.",
    ]
    
    for text in test_texts:
        print(f"\n原文: {text}")
        result = service.translate(text, source_lang='en', target_lang='zh')
        if result:
            print(f"译文: {result}")
        else:
            print("翻译失败")


def test_free_service():
    """测试免费翻译服务聚合"""
    print("\n" + "=" * 60)
    print("测试免费翻译服务聚合")
    print("=" * 60)
    
    service = FreeTranslationService()
    
    test_texts = [
        "Hello, how are you today?",
        "This is a book about artificial intelligence.",
        "The weather is nice today.",
        "I love reading books.",
    ]
    
    for text in test_texts:
        print(f"\n原文: {text}")
        result = service.translate(text, source_lang='en', target_lang='zh')
        if result:
            print(f"译文: {result}")
        else:
            print("所有免费API都翻译失败")


if __name__ == '__main__':
    # 测试 Google Translate
    test_google_translate()
    
    # 测试 LibreTranslate
    test_libre_translate()
    
    # 测试免费服务聚合
    test_free_service()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
