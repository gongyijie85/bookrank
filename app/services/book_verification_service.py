"""
图书验证服务
自动校对获奖图书信息，确保数据准确性
"""

import json
import re
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from flask import current_app

from ..models.schemas import AwardBook, db


class BookVerificationService:
    """图书验证服务类"""
    
    def __init__(self, app=None):
        self.app = app
        self.errors = []
        self.warnings = []
    
    def verify_book(self, book: AwardBook) -> Tuple[bool, Dict]:
        """
        验证单本图书
        
        Args:
            book: AwardBook 对象
            
        Returns:
            (是否通过验证, 验证详情字典)
        """
        self.errors = []
        self.warnings = []
        
        result = {
            'book_id': book.id,
            'title': book.title,
            'isbn13': book.isbn13,
            'checks': {},
            'passed': False
        }
        
        # 1. 验证基本信息
        result['checks']['basic_info'] = self._verify_basic_info(book)
        
        # 2. 验证 ISBN
        result['checks']['isbn'] = self._verify_isbn(book)
        
        # 3. 验证封面可用性
        result['checks']['cover'] = self._verify_cover(book)
        
        # 4. 验证元数据完整性
        result['checks']['metadata'] = self._verify_metadata(book)
        
        # 5. 通过外部 API 验证图书存在性（如果 ISBN 存在）
        if book.isbn13:
            result['checks']['external_api'] = self._verify_external_api(book)
        
        # 计算验证结果
        critical_checks = ['basic_info', 'isbn']
        all_critical_passed = all(result['checks'].get(check, {}).get('passed', False) 
                                  for check in critical_checks if check in result['checks'])
        
        # 只要有严重错误就不通过
        if self.errors:
            result['passed'] = False
            result['status'] = 'failed'
        # 基本信息和 ISBN 验证通过即可标记为可展示
        elif all_critical_passed:
            result['passed'] = True
            result['status'] = 'verified'
        else:
            result['passed'] = False
            result['status'] = 'pending'
        
        result['errors'] = self.errors
        result['warnings'] = self.warnings
        
        return result['passed'], result
    
    def _verify_basic_info(self, book: AwardBook) -> Dict:
        """验证基本信息"""
        check = {'name': '基本信息', 'passed': True, 'details': []}
        
        # 检查书名
        if not book.title or len(book.title.strip()) < 2:
            self.errors.append('书名不能为空或太短')
            check['passed'] = False
            check['details'].append('❌ 书名无效')
        else:
            check['details'].append('✅ 书名有效')
        
        # 检查作者
        if not book.author or len(book.author.strip()) < 2:
            self.errors.append('作者不能为空或太短')
            check['passed'] = False
            check['details'].append('❌ 作者无效')
        else:
            check['details'].append('✅ 作者有效')
        
        # 检查简介（警告级别）
        if not book.description or len(book.description.strip()) < 10:
            self.warnings.append('简介为空或太短')
            check['details'].append('⚠️ 简介不完整')
        else:
            check['details'].append('✅ 简介完整')
        
        return check
    
    def _verify_isbn(self, book: AwardBook) -> Dict:
        """验证 ISBN"""
        check = {'name': 'ISBN验证', 'passed': True, 'details': []}
        
        if not book.isbn13:
            self.errors.append('ISBN-13 不能为空')
            check['passed'] = False
            check['details'].append('❌ 缺少 ISBN-13')
            return check
        
        # 验证 ISBN-13 格式
        isbn = book.isbn13.replace('-', '').replace(' ', '')
        if len(isbn) != 13:
            self.errors.append(f'ISBN-13 长度不正确: {len(isbn)} 位，应为 13 位')
            check['passed'] = False
            check['details'].append(f'❌ ISBN 长度错误 ({len(isbn)}位)')
            return check
        
        if not isbn.isdigit():
            self.errors.append('ISBN-13 只能包含数字')
            check['passed'] = False
            check['details'].append('❌ ISBN 格式错误（含非数字字符）')
            return check
        
        # 验证 ISBN-13 校验位
        if not self._validate_isbn13_checksum(isbn):
            self.errors.append('ISBN-13 校验位不正确')
            check['passed'] = False
            check['details'].append('❌ ISBN 校验失败')
            return check
        
        check['details'].append('✅ ISBN-13 格式正确')
        
        # 检查 ISBN-10（如果有）
        if book.isbn10:
            isbn10 = book.isbn10.replace('-', '').replace(' ', '')
            if len(isbn10) != 10:
                self.warnings.append('ISBN-10 长度不正确')
                check['details'].append('⚠️ ISBN-10 长度错误')
            else:
                check['details'].append('✅ ISBN-10 格式正确')
        
        return check
    
    def _validate_isbn13_checksum(self, isbn: str) -> bool:
        """验证 ISBN-13 校验位"""
        if len(isbn) != 13 or not isbn.isdigit():
            return False
        
        # ISBN-13 校验算法
        total = 0
        for i, digit in enumerate(isbn[:-1]):
            if i % 2 == 0:
                total += int(digit)
            else:
                total += int(digit) * 3
        
        check_digit = (10 - (total % 10)) % 10
        return check_digit == int(isbn[-1])
    
    def _verify_cover(self, book: AwardBook) -> Dict:
        """验证封面可用性"""
        check = {'name': '封面验证', 'passed': False, 'details': []}
        
        # 1. 检查本地封面
        if book.cover_local_path:
            check['passed'] = True
            check['details'].append('✅ 本地封面存在')
            return check
        
        # 2. 检查原始封面 URL
        if book.cover_original_url:
            check['passed'] = True
            check['details'].append('✅ 原始封面 URL 存在')
            return check
        
        # 3. 检查是否可以通过 ISBN 获取 Open Library 封面
        if book.isbn13:
            openlib_url = f"https://covers.openlibrary.org/b/isbn/{book.isbn13}-M.jpg"
            try:
                response = requests.head(openlib_url, timeout=5, allow_redirects=True)
                if response.status_code == 200:
                    check['passed'] = True
                    check['details'].append('✅ Open Library 封面可用')
                    return check
            except:
                pass
        
        self.warnings.append('封面不可用，将使用默认封面')
        check['details'].append('⚠️ 封面不可用（将使用默认封面）')
        return check
    
    def _verify_metadata(self, book: AwardBook) -> Dict:
        """验证元数据完整性"""
        check = {'name': '元数据验证', 'passed': True, 'details': []}
        
        # 检查出版社
        if not book.publisher:
            self.warnings.append('出版社信息缺失')
            check['details'].append('⚠️ 出版社未填写')
        else:
            check['details'].append('✅ 出版社已填写')
        
        # 检查出版年份
        if not book.publication_year:
            self.warnings.append('出版年份缺失')
            check['details'].append('⚠️ 出版年份未填写')
        elif not (1800 <= book.publication_year <= 2100):
            self.warnings.append(f'出版年份异常: {book.publication_year}')
            check['details'].append(f'⚠️ 出版年份异常 ({book.publication_year})')
        else:
            check['details'].append('✅ 出版年份有效')
        
        # 检查获奖年份
        if not book.year:
            self.errors.append('获奖年份不能为空')
            check['passed'] = False
            check['details'].append('❌ 获奖年份未填写')
        else:
            check['details'].append('✅ 获奖年份已填写')
        
        return check
    
    def _verify_external_api(self, book: AwardBook) -> Dict:
        """通过外部 API 验证图书存在性"""
        check = {'name': '外部API验证', 'passed': False, 'details': []}
        
        if not book.isbn13:
            check['details'].append('⏭️ 跳过（无 ISBN）')
            return check
        
        # 尝试 Open Library API
        try:
            url = f"https://openlibrary.org/isbn/{book.isbn13}.json"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                check['passed'] = True
                check['details'].append('✅ Open Library 验证通过')
                
                # 对比书名是否匹配
                api_title = data.get('title', '')
                if api_title and book.title:
                    # 简单匹配：检查 API 返回的书名是否包含在本地书名中或反之
                    if (book.title.lower() in api_title.lower() or 
                        api_title.lower() in book.title.lower()):
                        check['details'].append('✅ 书名匹配')
                    else:
                        self.warnings.append(f'书名可能不匹配: 本地"{book.title}" vs API"{api_title}"')
                        check['details'].append(f'⚠️ 书名差异')
                
                return check
        except Exception as e:
            check['details'].append(f'⚠️ Open Library 查询失败: {str(e)[:50]}')
        
        # Open Library 失败，尝试 Google Books API
        try:
            api_key = current_app.config.get('GOOGLE_API_KEY')
            if api_key:
                url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{book.isbn13}&key={api_key}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('totalItems', 0) > 0:
                        check['passed'] = True
                        check['details'].append('✅ Google Books 验证通过')
                        return check
                    else:
                        check['details'].append('⚠️ Google Books 未找到该图书')
                elif response.status_code == 429:
                    check['details'].append('⏸️ Google Books API 限流')
                else:
                    check['details'].append(f'⚠️ Google Books 返回错误: {response.status_code}')
        except Exception as e:
            check['details'].append(f'⚠️ Google Books 查询失败: {str(e)[:50]}')
        
        if not check['passed']:
            self.warnings.append('无法通过外部 API 验证图书存在性')
        
        return check
    
    def verify_all_pending(self, limit: int = 10) -> List[Dict]:
        """
        验证所有待验证的图书
        
        Args:
            limit: 每次验证的最大数量，防止 API 限流
            
        Returns:
            验证结果列表
        """
        results = []
        
        # 查询待验证或验证失败的图书
        pending_books = AwardBook.query.filter(
            AwardBook.verification_status.in_(['pending', 'failed'])
        ).limit(limit).all()
        
        current_app.logger.info(f'开始验证 {len(pending_books)} 本图书')
        
        for book in pending_books:
            try:
                passed, result = self.verify_book(book)
                
                # 更新图书验证状态
                book.verification_status = result['status']
                book.verification_checked_at = datetime.utcnow()
                book.verification_errors = json.dumps({
                    'errors': self.errors,
                    'warnings': self.warnings,
                    'checks': result['checks']
                })
                
                # 只有验证通过且没有严重错误的图书才展示给读者
                if passed and not self.errors:
                    book.is_displayable = True
                else:
                    book.is_displayable = False
                
                db.session.commit()
                
                results.append(result)
                current_app.logger.info(f'图书验证完成: {book.title} - {result["status"]}')
                
            except Exception as e:
                current_app.logger.error(f'验证图书失败 {book.title}: {e}')
                results.append({
                    'book_id': book.id,
                    'title': book.title,
                    'status': 'error',
                    'error': str(e)
                })
        
        return results
    
    def get_verification_summary(self) -> Dict:
        """获取验证状态汇总"""
        total = AwardBook.query.count()
        verified = AwardBook.query.filter_by(verification_status='verified').count()
        pending = AwardBook.query.filter_by(verification_status='pending').count()
        failed = AwardBook.query.filter_by(verification_status='failed').count()
        displayable = AwardBook.query.filter_by(is_displayable=True).count()
        
        return {
            'total': total,
            'verified': verified,
            'pending': pending,
            'failed': failed,
            'displayable': displayable,
            'verification_rate': round(verified / total * 100, 2) if total > 0 else 0
        }
