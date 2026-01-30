"""
测试翻译API
"""
import requests
import json

def test_mymemory():
    """测试 MyMemory API"""
    print("=" * 60)
    print("测试 MyMemory API")
    print("=" * 60)
    
    url = 'https://api.mymemory.translated.net/get'
    params = {
        'q': 'Hello world, this is a test of the translation API.',
        'langpair': 'en|zh-CN'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        print(f'Status: {response.status_code}')
        print(f'Response: {response.text[:500]}')
        
        if response.status_code == 200:
            data = response.json()
            translated = data.get('responseData', {}).get('translatedText')
            print(f'Translated: {translated}')
            return True
    except Exception as e:
        print(f'Error: {e}')
    
    return False

def test_libretranslate():
    """测试 LibreTranslate API"""
    print("\n" + "=" * 60)
    print("测试 LibreTranslate API")
    print("=" * 60)
    
    urls = [
        'https://libretranslate.de/translate',
        'https://libretranslate.com/translate'
    ]
    
    payload = {
        'q': 'Hello world',
        'source': 'en',
        'target': 'zh',
        'format': 'text'
    }
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    for url in urls:
        print(f"\n测试: {url}")
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            print(f'Status: {response.status_code}')
            print(f'Response: {response.text[:200]}')
            
            if response.status_code == 200:
                data = response.json()
                translated = data.get('translatedText')
                if translated:
                    print(f'Translated: {translated}')
                    return True
        except Exception as e:
            print(f'Error: {e}')
    
    return False

if __name__ == '__main__':
    mymemory_works = test_mymemory()
    libretranslate_works = test_libretranslate()
    
    print("\n" + "=" * 60)
    print("测试结果")
    print("=" * 60)
    print(f"MyMemory API: {'可用' if mymemory_works else '不可用'}")
    print(f"LibreTranslate API: {'可用' if libretranslate_works else '不可用'}")
