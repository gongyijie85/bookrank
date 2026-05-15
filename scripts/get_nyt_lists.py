import os
import sys
import requests
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.config import Config

def get_nyt_lists():
    """获取 NYT Books API 所有可用的分类列表"""
    print("Getting NYT Books API available lists...")
    
    # 获取 API Key
    nyt_api_key = os.environ.get('NYT_API_KEY')
    if not nyt_api_key:
        print("❌ NYT_API_KEY not found in environment variables")
        return
    
    # API 端点 - 尝试不同的端点格式
    url = "https://api.nytimes.com/svc/books/v3/lists/overview.json"
    params = {'api-key': nyt_api_key}
    
    try:
        print(f"Fetching from: {url}")
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        print(f"API response keys: {list(data.keys())}")
        
        results = data.get('results', {})
        print(f"Results keys: {list(results.keys()) if isinstance(results, dict) else 'Not a dict'}")
        
        # 检查是否有 lists 字段
        if isinstance(results, dict):
            lists = results.get('lists', [])
            print(f"Found {len(lists)} lists")
            print("\nAvailable lists:")
            print("-" * 80)
            
            # 按分类名称排序
            lists.sort(key=lambda x: x.get('display_name', ''))
            
            for item in lists:
                list_name = item.get('list_name', 'N/A')
                list_name_encoded = item.get('list_name_encoded', 'N/A')
                display_name = item.get('display_name', 'N/A')
                
                print(f"List Name: {list_name}")
                print(f"Encoded: {list_name_encoded}")
                print(f"Display: {display_name}")
                print("-" * 80)
                
            # 检查 paperback-nonfiction 是否存在
            has_paperback_nonfiction = any(item.get('list_name_encoded') == 'paperback-nonfiction' for item in lists)
            print(f"\nPaperback Nonfiction category exists: {has_paperback_nonfiction}")
            
            # 查找可能的替代分类
            if not has_paperback_nonfiction:
                print("\nLooking for alternative nonfiction categories...")
                nonfiction_lists = [item for item in lists if 'nonfiction' in item.get('list_name', '').lower()]
                if nonfiction_lists:
                    print("Found nonfiction categories:")
                    for item in nonfiction_lists:
                        print(f"- {item.get('display_name')} (encoded: {item.get('list_name_encoded')})")
                else:
                    print("No nonfiction categories found.")
        else:
            print("Results is not a dict, printing raw data:")
            print(data)
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    get_nyt_lists()
