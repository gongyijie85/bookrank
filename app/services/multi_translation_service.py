"""
多翻译API轮询服务

当主翻译API(MyMemory)限流时，自动切换到备用API(百度翻译)
"""

import logging
import hashlib
import json
import os
import random
import string
import time
from typing import Optional, List
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)


class BaiduTranslationService:
    """
    百度翻译API服务
    文档: https://fanyi-api.baidu.com/doc/21
    """
    
    API_URL = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
    
    def __init__(self):
        self.app_id = os.environ.get('BAIDU_FY_APP_ID', '')
        self.app_key = os.environ.get('BAIDU_FY_APP_KEY', '')
        
        if not self.app_id or not self.app_key:
            logger.warning("百度翻译API密钥未配置")
    
    def _make_sign(self, query: str, salt: str) -> str:
        """生成百度API签名"""
        sign_str = self.app_id + query + salt + self.app_key
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest()
    
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        """
        使用百度翻译API翻译文本
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码 (en->英文, zh->中文等)
            target_lang: 目标语言代码
            
        Returns:
            翻译后的文本，失败返回None
        """
        if not self.app_id or not self.app_key:
            return None
        
        if not text or not text.strip():
            return text
        
        # 语言代码转换
        lang_map = {
            'en': 'en',
            'zh': 'zh',
            'auto': 'auto'
        }
        from_lang = lang_map.get(source_lang, 'en')
        to_lang = lang_map.get(target_lang, 'zh')
        
        # 生成随机salt
        salt = ''.join(random.choices(string.digits, k=10))
        
        # 生成签名
        sign = self._make_sign(text, salt)
        
        params = {
            'q': text,
            'from': from_lang,
            'to': to_lang,
            'appid': self.app_id,
            'salt': salt,
            'sign': sign
        }
        
        try:
            response = requests.get(self.API_URL, params=params, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                # 检查错误
                if 'error_code' in result:
                    logger.warning(f"百度翻译API错误: {result.get('error_msg')}")
                    return None
                
                # 提取翻译结果
                trans_result = result.get('trans_result', [])
                if trans_result:
                    translated = ''.join([item.get('dst', '') for item in trans_result])
                    logger.info(f"百度翻译成功: {text[:50]}... -> {translated[:50]}...")
                    return translated
                    
        except requests.exceptions.Timeout:
            logger.warning("百度翻译请求超时")
        except requests.exceptions.RequestException as e:
            logger.warning(f"百度翻译请求失败: {e}")
        except Exception as e:
            logger.error(f"百度翻译未知错误: {e}")
        
        return None


class MyMemoryTranslationService:
    """
    MyMemory Translation API 翻译服务
    特点：
    - 完全免费，无需注册
    - 每日约5000字符免费额度
    - 内置翻译缓存
    - 自动错误处理和重试
    """
    
    API_URL = 'https://api.mymemory.translated.net/get'
    
    def __init__(self, delay: float = 0.5, max_retries: int = 3):
        """
        初始化翻译服务
        
        Args:
            delay: 请求间隔（秒）
            max_retries: 最大重试次数
        """
        self.delay = delay
        self.max_retries = max_retries
        self._rate_limited = False
        self._rate_limit_reset_time = None
        
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码
            target_lang: 目标语言代码
            
        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return text
        
        # 检查是否处于限流状态
        if self._rate_limited:
            if self._rate_limit_reset_time and datetime.now() < self._rate_limit_reset_time:
                logger.warning("MyMemory API 处于限流状态，跳过请求")
                return None
            else:
                # 重置限流状态
                self._rate_limited = False
                self._rate_limit_reset_time = None
        
        # 限制文本长度（MyMemory建议单次不超过500字符）
        if len(text) > 500:
            logger.warning(f"文本过长({len(text)}字符)，将截断翻译")
            text = text[:500]
        
        # 添加延迟
        time.sleep(self.delay)
        
        # 尝试翻译
        for attempt in range(self.max_retries):
            try:
                params = {
                    'q': text,
                    'langpair': f'{source_lang}|{target_lang}'
                }
                
                logger.debug(f"正在请求MyMemory API")
                response = requests.get(self.API_URL, params=params, timeout=30)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        
                        # 检查响应状态
                        response_status = result.get('responseStatus', 0)
                        
                        # 检查是否限流
                        if response_status == 429:
                            self._rate_limited = True
                            self._rate_limit_reset_time = datetime.now() + timedelta(hours=4)
                            logger.warning("MyMemory API 触发限流，将使用备用API")
                            return None
                        
                        if response_status == 200:
                            translated = result.get('responseData', {}).get('translatedText')
                            
                            if translated:
                                logger.info(f"MyMemory翻译成功: {text[:50]}... -> {translated[:50]}...")
                                return translated
                        else:
                            logger.warning(f"MyMemory API返回错误状态: {response_status}")
                            
                    except Exception as e:
                        logger.warning(f"解析响应失败: {e}, 响应: {response.text[:200]}")
                else:
                    logger.warning(f"API返回错误 {response.status_code}: {response.text[:200]}")
                        
            except requests.exceptions.Timeout:
                logger.warning(f"请求超时")
            except requests.exceptions.RequestException as e:
                logger.warning(f"请求失败: {e}")
            except Exception as e:
                logger.error(f"未知错误: {e}")
            
            # 重试前等待
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
        
        logger.error(f"MyMemory翻译失败，返回None")
        return None


class MultiTranslationService:
    """
    多翻译API轮询服务
    
    优先级：
    1. MyMemory API (免费，但有额度限制)
    2. 百度翻译API (备用)
    """
    
    def __init__(self):
        self.mymemory = MyMemoryTranslationService()
        self.baidu = BaiduTranslationService()
        
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        """
        翻译文本，自动选择可用的API
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码
            target_lang: 目标语言代码
            
        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return text
        
        # 首先尝试 MyMemory
        logger.info("尝试使用 MyMemory API 翻译...")
        result = self.mymemory.translate(text, source_lang, target_lang)
        
        if result:
            return result
        
        # MyMemory 失败，尝试百度翻译
        logger.info("MyMemory 不可用，切换到百度翻译API...")
        result = self.baidu.translate(text, source_lang, target_lang)
        
        if result:
            return result
        
        logger.error("所有翻译API都不可用")
        return None
    
    def translate_batch(self, texts: List[str], source_lang: str = 'en',
                       target_lang: str = 'zh', progress_callback=None) -> List[str]:
        """
        批量翻译
        
        Args:
            texts: 文本列表
            source_lang: 源语言
            target_lang: 目标语言
            progress_callback: 进度回调函数 (current, total)
        
        Returns:
            翻译结果列表
        """
        results = []
        total = len(texts)
        
        for i, text in enumerate(texts):
            if progress_callback:
                progress_callback(i + 1, total)
            
            result = self.translate(text, source_lang, target_lang)
            results.append(result if result else text)
        
        return results
