#!/usr/bin/env python3
"""
校验获奖图书 ISBN 脚本
通过 Google Books API 使用书名+作者查询，验证 ISBN 是否正确
"""

import sys
from app import create_app
from app.services.api_client import GoogleBooksClient

# 获奖图书数据
sample_books = [
    # 普利策奖
    {'award_name': '普利策奖', 'year': 2025, 'title': 'James', 'author': 'Percival Everett', 'isbn13': '9780385550369'},
    {'award_name': '普利策奖', 'year': 2024, 'title': 'The Nickel Boys', 'author': 'Colson Whitehead', 'isbn13': '9780385537070'},
    {'award_name': '普利策奖', 'year': 2023, 'title': 'Demon Copperhead', 'author': 'Barbara Kingsolver', 'isbn13': '9780063251922'},
    {'award_name': '普利策奖', 'year': 2023, 'title': 'His Name Is George Floyd', 'author': 'Robert Samuels, Toluse Olorunnipa', 'isbn13': '9780593491930'},
    {'award_name': '普利策奖', 'year': 2022, 'title': 'The Netanyahus', 'author': 'Joshua Cohen', 'isbn13': '9781681376070'},
    
    # 布克奖
    {'award_name': '布克奖', 'year': 2024, 'title': 'Orbital', 'author': 'Samantha Harvey', 'isbn13': '9780802163807'},
    {'award_name': '布克奖', 'year': 2023, 'title': 'Prophet Song', 'author': 'Paul Lynch', 'isbn13': '9780802161513'},
    {'award_name': '布克奖', 'year': 2022, 'title': 'The Seven Moons of Maali Almeida', 'author': 'Shehan Karunatilaka', 'isbn13': '9781324035910'},
    
    # 诺贝尔文学奖
    {'award_name': '诺贝尔文学奖', 'year': 2024, 'title': 'The Vegetarian', 'author': 'Han Kang', 'isbn13': '9780553448184'},
    {'award_name': '诺贝尔文学奖', 'year': 2023, 'title': 'A New Name: Septology VI-VII', 'author': 'Jon Fosse', 'isbn13': '9781555978896'},
    {'award_name': '诺贝尔文学奖', 'year': 2022, 'title': 'The Years', 'author': 'Annie Ernaux', 'isbn13': '9781609808927'},
    
    # 雨果奖
    {'award_name': '雨果奖', 'year': 2025, 'title': 'The Tainted Cup', 'author': 'Robert Jackson Bennett', 'isbn13': '9781984820709'},
    {'award_name': '雨果奖', 'year': 2024, 'title': 'Some Desperate Glory', 'author': 'Emily Tesh', 'isbn13': '9781250834989'},
    {'award_name': '雨果奖', 'year': 2023, 'title': 'Nettle & Bone', 'author': 'T. Kingfisher', 'isbn13': '9781250244048'},
    
    # 美国国家图书奖
    {'award_name': '美国国家图书奖', 'year': 2024, 'title': 'James', 'author': 'Percival Everett', 'isbn13': '9780385550369'},
    {'award_name': '美国国家图书奖', 'year': 2023, 'title': 'The Rabbit Hutch', 'author': 'Tess Gunty', 'isbn13': '9780593534668'},
    {'award_name': '美国国家图书奖', 'year': 2022, 'title': 'The Rabbit Hutch', 'author': 'Tess Gunty', 'isbn13': '9780593534668'},
    
    # 星云奖
    {'award_name': '星云奖', 'year': 2023, 'title': 'Babel: Or the Necessity of Violence', 'author': 'R.F. Kuang', 'isbn13': '9780063021426'},
    {'award_name': '星云奖', 'year': 2022, 'title': 'A Desolation Called Peace', 'author': 'Arkady Martine', 'isbn13': '9781250186461'},
    
    # 国际布克奖
    {'award_name': '国际布克奖', 'year': 2024, 'title': 'Kairos', 'author': 'Jenny Erpenbeck', 'isbn13': '9780811232011'},
    {'award_name': '国际布克奖', 'year': 2023, 'title': 'Time Shelter', 'author': 'Georgi Gospodinov', 'isbn13': '9781324008372'},
    {'award_name': '国际布克奖', 'year': 2022, 'title': 'Tomb of Sand', 'author': 'Geetanjali Shree', 'isbn13': '9781953861162'},
    
    # 爱伦·坡奖
    {'award_name': '爱伦·坡奖', 'year': 2024, 'title': 'The River We Remember', 'author': 'William Kent Krueger', 'isbn13': '9781982178697'},
    {'award_name': '爱伦·坡奖', 'year': 2023, 'title': 'The Accomplice', 'author': 'Lisa Lutz', 'isbn13': '9781982168322'},
    {'award_name': '爱伦·坡奖', 'year': 2022, 'title': 'Billy Summers', 'author': 'Stephen King', 'isbn13': '9781982173616'},
]

def validate_isbn(app, book):
    """通过书名查询 Google Books API 验证 ISBN"""
    client = GoogleBooksClient(
        api_key=app.config.get('GOOGLE_API_KEY'),
        base_url='https://www.googleapis.com/books/v1/volumes',
        timeout=10
    )
    
    title = book['title']
    author = book['author'].split(',')[0] if ',' in book['author'] else book['author']
    current_isbn = book['isbn13']
    
    print(f"\n📚 {book['award_name']} ({book['year']})")
    print(f"   书名: {title}")
    print(f"   作者: {book['author']}")
    print(f"   当前 ISBN: {current_isbn}")
    
    # 使用当前 ISBN 查询
    result_by_isbn = client.fetch_book_details(current_isbn)
    if result_by_isbn:
        print(f"   ✅ ISBN 查询成功: {result_by_isbn.get('title')}")
        print(f"   返回 ISBN-13: {result_by_isbn.get('isbn_13')}")
        if result_by_isbn.get('isbn_13') == current_isbn:
            print(f"   ✅ ISBN 匹配正确")
            return True, current_isbn
        else:
            print(f"   ⚠️ ISBN 不匹配，建议更新为: {result_by_isbn.get('isbn_13')}")
            return False, result_by_isbn.get('isbn_13')
    else:
        print(f"   ❌ ISBN 查询失败，尝试用书名查询...")
    
    # 使用书名+作者查询
    result_by_title = client.search_book_by_title(title, author)
    if result_by_title:
        found_isbn = result_by_title.get('isbn_13')
        found_title = result_by_title.get('title')
        print(f"   ✅ 书名查询成功: {found_title}")
        print(f"   找到 ISBN-13: {found_isbn}")
        if found_isbn == current_isbn:
            print(f"   ✅ ISBN 正确")
            return True, current_isbn
        else:
            print(f"   ⚠️ ISBN 不正确，建议更新为: {found_isbn}")
            return False, found_isbn
    else:
        print(f"   ❌ 书名查询也失败，无法验证")
        return None, None

if __name__ == '__main__':
    app = create_app()
    
    print("="*80)
    print("开始校验获奖图书 ISBN")
    print("="*80)
    
    corrections = []
    
    with app.app_context():
        for i, book in enumerate(sample_books, 1):
            print(f"\n[{i}/{len(sample_books)}] ", end="")
            is_correct, correct_isbn = validate_isbn(app, book)
            
            if is_correct is False and correct_isbn:
                corrections.append({
                    'award_name': book['award_name'],
                    'year': book['year'],
                    'title': book['title'],
                    'old_isbn': book['isbn13'],
                    'new_isbn': correct_isbn
                })
            
            # 添加延迟避免 API 限流
            import time
            time.sleep(1)
    
    print("\n" + "="*80)
    print("校验完成")
    print("="*80)
    
    if corrections:
        print(f"\n发现 {len(corrections)} 个需要修正的 ISBN:")
        for item in corrections:
            print(f"  - {item['award_name']} ({item['year']}): {item['title']}")
            print(f"    {item['old_isbn']} -> {item['new_isbn']}")
    else:
        print("\n✅ 所有 ISBN 都正确")
