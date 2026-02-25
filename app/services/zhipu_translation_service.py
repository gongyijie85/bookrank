"""
智谱AI GLM-4-Flash 翻译服务

使用智谱AI免费模型进行高质量翻译
支持批量翻译和流式输出
"""

import logging
import os
import time
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class ZhipuTranslationService:
    """
    智谱AI翻译服务
    
    使用GLM-4-Flash免费模型进行翻译
    优点：
    - 免费
    - 高质量翻译
    - 支持上下文理解
    - 专业术语翻译准确
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "glm-4-flash"):
        """
        初始化智谱AI翻译服务
        
        Args:
            api_key: 智谱AI API密钥，如果不提供则从环境变量获取
            model: 使用的模型，默认glm-4-flash
        """
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY")
        self.model = model
        self._client = None
        self._last_request_time = 0
        self._request_interval = 0.1  # 请求间隔（秒）
        
        # 翻译系统提示词
        self._system_prompt = (
            "你是一个专业的翻译助手，将英文翻译成中文。"
            "要求：1.保持准确流畅 2.不要添加额外解释 3.保留原文格式 4.专业术语保持准确"
        )
        
    def _get_client(self):
        """懒加载客户端"""
        if self._client is None:
            if not self.api_key:
                logger.warning("智谱AI API Key未配置，请设置ZHIPU_API_KEY环境变量")
                return None
            
            try:
                from zhipuai import ZhipuAI
                self._client = ZhipuAI(api_key=self.api_key)
                logger.info("智谱AI客户端初始化成功")
            except ImportError as e:
                logger.error(f"zhipuai库未安装: {e}，请运行: pip install zhipuai")
                return None
            except Exception as e:
                logger.error(f"智谱AI客户端初始化失败: {e}")
                return None
        
        return self._client
    
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码（目前只支持en）
            target_lang: 目标语言代码（目前只支持zh）
            
        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return text
        
        # 请求间隔控制
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self._request_interval:
            time.sleep(self._request_interval - time_since_last)
        
        client = self._get_client()
        if not client:
            return None
        
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,  # 低温度获得更稳定的翻译
                max_tokens=4096
            )
            
            self._last_request_time = time.time()
            
            if response and response.choices:
                result = response.choices[0].message.content
                if result:
                    logger.info(f"智谱AI翻译成功: {text[:50]}... -> {result[:50]}...")
                    return result.strip()
                    
        except Exception as e:
            logger.warning(f"智谱AI翻译失败: {e}")
        
        return None
    
    def translate_batch(self, texts: List[str], source_lang: str = 'en',
                       target_lang: str = 'zh', 
                       progress_callback=None) -> List[str]:
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
    
    def translate_book_info(self, book_data: Dict[str, Any], 
                           target_lang: str = 'zh') -> Dict[str, Any]:
        """
        翻译图书信息
        
        Args:
            book_data: 图书数据字典
            target_lang: 目标语言
            
        Returns:
            包含翻译字段的图书数据
        """
        result = book_data.copy()
        
        # 翻译书名
        if book_data.get('title') and not book_data.get('title_zh'):
            translated_title = self.translate(book_data['title'], target_lang=target_lang)
            if translated_title:
                result['title_zh'] = translated_title
        
        # 翻译描述
        if book_data.get('description') and not book_data.get('description_zh'):
            translated_desc = self.translate(book_data['description'], target_lang=target_lang)
            if translated_desc:
                result['description_zh'] = translated_desc
        
        # 翻译详细信息
        if book_data.get('details') and not book_data.get('details_zh'):
            translated_details = self.translate(book_data['details'], target_lang=target_lang)
            if translated_details:
                result['details_zh'] = translated_details
        
        return result
    
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self._get_client() is not None


class HybridTranslationService:
    """
    混合翻译服务
    
    优先使用智谱AI，失败时回退到其他免费翻译服务
    """
    
    def __init__(self, zhipu_api_key: Optional[str] = None):
        """
        初始化混合翻译服务
        
        Args:
            zhipu_api_key: 智谱AI API密钥
        """
        self.zhipu = ZhipuTranslationService(api_key=zhipu_api_key)
        self._fallback = None
        
    def _get_fallback(self):
        """获取备用翻译服务"""
        if self._fallback is None:
            try:
                from .free_translation_service import FreeTranslationService
                self._fallback = FreeTranslationService()
            except ImportError:
                pass
        return self._fallback
    
    def translate(self, text: str, source_lang: str = 'en', 
                  target_lang: str = 'zh') -> Optional[str]:
        """
        翻译文本，自动选择可用的翻译服务
        
        Args:
            text: 要翻译的文本
            source_lang: 源语言代码
            target_lang: 目标语言代码
            
        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return text
        
        # 首先尝试智谱AI
        if self.zhipu.is_available():
            logger.info("使用智谱AI翻译...")
            result = self.zhipu.translate(text, source_lang, target_lang)
            if result:
                return result
            logger.warning("智谱AI翻译失败，尝试备用服务...")
        
        # 回退到其他免费服务
        fallback = self._get_fallback()
        if fallback:
            logger.info("使用备用翻译服务...")
            return fallback.translate(text, source_lang, target_lang)
        
        logger.error("所有翻译服务都不可用")
        return None
    
    def translate_batch(self, texts: List[str], source_lang: str = 'en',
                       target_lang: str = 'zh', 
                       progress_callback=None) -> List[str]:
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
    
    def translate_book_info(self, book_data: Dict[str, Any], 
                           target_lang: str = 'zh') -> Dict[str, Any]:
        """
        翻译图书信息
        
        Args:
            book_data: 图书数据字典
            target_lang: 目标语言
            
        Returns:
            包含翻译字段的图书数据
        """
        result = book_data.copy()
        
        # 翻译书名
        if book_data.get('title') and not book_data.get('title_zh'):
            translated_title = self.translate(book_data['title'], target_lang=target_lang)
            if translated_title:
                result['title_zh'] = translated_title
        
        # 翻译描述
        if book_data.get('description') and not book_data.get('description_zh'):
            translated_desc = self.translate(book_data['description'], target_lang=target_lang)
            if translated_desc:
                result['description_zh'] = translated_desc
        
        # 翻译详细信息
        if book_data.get('details') and not book_data.get('details_zh'):
            translated_details = self.translate(book_data['details'], target_lang=target_lang)
            if translated_details:
                result['details_zh'] = translated_details
        
        return result


# 全局混合翻译服务实例
_hybrid_translation_service = None


def get_translation_service() -> HybridTranslationService:
    """获取全局翻译服务实例"""
    global _hybrid_translation_service
    if _hybrid_translation_service is None:
        _hybrid_translation_service = HybridTranslationService()
    return _hybrid_translation_service


def translate_text(text: str, source_lang: str = 'en', 
                   target_lang: str = 'zh') -> Optional[str]:
    """翻译文本的便捷函数"""
    return get_translation_service().translate(text, source_lang, target_lang)


def translate_book_info(book_data: Dict[str, Any], 
                       target_lang: str = 'zh') -> Dict[str, Any]:
    """翻译图书信息的便捷函数"""
    return get_translation_service().translate_book_info(book_data, target_lang)
