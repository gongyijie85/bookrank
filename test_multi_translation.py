"""
测试多翻译API轮询服务
"""

import sys
import os

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from app.services.multi_translation_service import (
    MultiTranslationService,
    BaiduTranslationService,
    MyMemoryTranslationService
)


def test_baidu_translate():
    """测试百度翻译"""
    print("=" * 60)
    print("测试百度翻译API")
    print("=" * 60)
    
    service = BaiduTranslationService()
    
    test_texts = [
        "Hello, how are you?",
        "This is a test of the translation service.",
        "The quick brown fox jumps over the lazy dog."
    ]
    
    for text in test_texts:
        print(f"\n原文: {text}")
        result = service.translate(text, source_lang='en', target_lang='zh')
        if result:
            print(f"译文: {result}")
        else:
            print("翻译失败")


def test_mymemory_translate():
    """测试MyMemory翻译"""
    print("\n" + "=" * 60)
    print("测试MyMemory翻译API")
    print("=" * 60)
    
    service = MyMemoryTranslationService()
    
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
            print("翻译失败（可能已触发限流）")


def test_multi_translate():
    """测试多翻译服务自动切换"""
    print("\n" + "=" * 60)
    print("测试多翻译服务自动切换")
    print("=" * 60)
    
    service = MultiTranslationService()
    
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
            print("所有API都翻译失败")


if __name__ == '__main__':
    # 测试百度翻译
    test_baidu_translate()
    
    # 测试MyMemory（可能已限流）
    test_mymemory_translate()
    
    # 测试多翻译服务
    test_multi_translate()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
