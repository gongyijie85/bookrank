"""
智谱AI GLM-4.7-Flash 翻译服务

使用智谱AI免费模型进行高质量翻译
支持批量翻译和流式输出
内置翻译缓存系统避免重复翻译
"""

import logging
import os
import time
from collections import OrderedDict
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def _translate_book_info(translator, book_data: Dict[str, Any],
                         target_lang: str = 'zh') -> Dict[str, Any]:
    """
    翻译图书信息（共享逻辑）

    Args:
        translator: 翻译服务实例（需有translate方法）
        book_data: 图书数据字典
        target_lang: 目标语言

    Returns:
        包含翻译字段的图书数据
    """
    result = book_data.copy()

    fields = [
        ('title', 'title_zh'),
        ('description', 'description_zh'),
        ('details', 'details_zh'),
    ]

    for src_key, dst_key in fields:
        if book_data.get(src_key) and not book_data.get(dst_key):
            translated = translator.translate(book_data[src_key], target_lang=target_lang)
            if translated:
                result[dst_key] = translated

    return result


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

    def __init__(self, api_key: Optional[str] = None, model: str = "glm-4.7-flash"):
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
        self._request_interval = 0.1
        self._author_name_cache: OrderedDict[str, str] = OrderedDict()
        self._author_name_cache_max_size = 1000
        self._cache_service = None

        self._system_prompt = """你是一位资深的图书翻译专家，专门负责将英文图书信息翻译成中文。

## 翻译规则

### 书名翻译（最重要）
- 文学性书名：采用意译，体现文学美感
  - 例："The Night We Met" → "我们相遇的那晚"
  - 例："The Great Gatsby" → "了不起的盖茨比"
- 专业书籍：采用直译，保持准确性
  - 例："Clean Code" → "代码整洁之道"
- 系列书籍：保持系列名称一致性
  - 例："Dungeon Crawler Carl Series" → "地下城卡尔·克劳利系列"

### 作者名翻译
- 使用标准中文译名（参考维基百科、豆瓣）
- 格式："原名 · 译名" 或仅译名
  - 例："Abby Jimenez" → "艾比·希门尼斯"
  - 例："Viola Davis" → "维奥拉·戴维斯"

### 描述文本翻译
- 流畅自然，符合中文阅读习惯
- 适当调整语序（英文常倒装，中文为主谓宾）
- 保留专有名词（地名、机构名）可不译或附原文

### 格式要求
- 不要添加任何解释、注释或备注
- 只返回纯翻译结果
- 保留段落结构"""

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

    def _get_cache_service(self):
        """获取翻译缓存服务"""
        if self._cache_service is None:
            try:
                from .translation_cache_service import get_translation_cache_service
                self._cache_service = get_translation_cache_service()
            except Exception as e:
                logger.warning(f"翻译缓存服务初始化失败: {e}")
        return self._cache_service

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
                temperature=0.3,
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
        批量翻译，使用缓存避免重复翻译

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
        cache_hits = 0

        cache_service = self._get_cache_service()

        for i, text in enumerate(texts):
            if progress_callback:
                progress_callback(i + 1, total)

            if not text or not text.strip():
                results.append(text)
                continue

            if cache_service:
                try:
                    cached = cache_service.get(text, source_lang, target_lang)
                    if cached:
                        results.append(cached.translated_text)
                        cache_hits += 1
                        continue
                except Exception:
                    pass

            result = self.translate(text, source_lang, target_lang)
            results.append(result if result else text)

        logger.info(f"批量翻译完成: 共{total}条, 缓存命中{cache_hits}条")
        return results

    def translate_book_info(self, book_data: Dict[str, Any],
                           target_lang: str = 'zh') -> Dict[str, Any]:
        """翻译图书信息"""
        return _translate_book_info(self, book_data, target_lang)

    def translate_author_name(self, author: str) -> Optional[str]:
        """
        翻译作者名（带内存缓存，LRU策略）

        Args:
            author: 原始作者名（英文）

        Returns:
            翻译后的作者名（中文），失败返回None
        """
        if not author or not author.strip():
            return None

        if author in self._author_name_cache:
            self._author_name_cache.move_to_end(author)
            return self._author_name_cache[author]

        if len(self._author_name_cache) >= self._author_name_cache_max_size:
            remove_count = int(self._author_name_cache_max_size * 0.2)
            for _ in range(remove_count):
                self._author_name_cache.popitem(last=False)
            logger.debug(f"作者名缓存已清理 {remove_count} 条，当前大小: {len(self._author_name_cache)}")

        translated = self.translate(author)

        if translated:
            self._author_name_cache[author] = translated
            logger.debug(f"作者名已翻译并缓存: {author} -> {translated}")

        return translated

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        cache_service = self._get_cache_service()
        if cache_service:
            return cache_service.get_stats()
        return {'total_count': 0, 'message': '缓存服务不可用'}

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self._get_client() is not None


class HybridTranslationService:
    """
    混合翻译服务

    优先使用智谱AI，失败时回退到其他免费翻译服务
    内置缓存系统避免重复翻译相同内容
    """

    def __init__(self, zhipu_api_key: Optional[str] = None):
        """
        初始化混合翻译服务

        Args:
            zhipu_api_key: 智谱AI API密钥
        """
        self.zhipu = ZhipuTranslationService(api_key=zhipu_api_key)
        self._fallback = None
        self._cache_service = None

    def _get_cache_service(self):
        """获取缓存服务"""
        if self._cache_service is None:
            try:
                from .translation_cache_service import get_translation_cache_service
                self._cache_service = get_translation_cache_service()
            except Exception as e:
                logger.warning(f"翻译缓存服务初始化失败: {e}")
        return self._cache_service

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
        翻译文本，自动选择可用的翻译服务并使用缓存

        Args:
            text: 要翻译的文本
            source_lang: 源语言代码
            target_lang: 目标语言代码

        Returns:
            翻译后的文本，失败返回None
        """
        if not text or not text.strip():
            return text

        cache_service = self._get_cache_service()
        if cache_service:
            try:
                cached = cache_service.get(text, source_lang, target_lang)
                if cached:
                    logger.debug("缓存命中，返回翻译结果")
                    return cached.translated_text
            except Exception as e:
                logger.debug(f"缓存读取失败: {e}")

        translated = None

        if self.zhipu.is_available():
            logger.info("使用智谱AI翻译...")
            translated = self.zhipu.translate(text, source_lang, target_lang)

        if not translated:
            fallback = self._get_fallback()
            if fallback:
                logger.info("使用备用翻译服务...")
                translated = fallback.translate(text, source_lang, target_lang)

        if translated and cache_service:
            try:
                cache_service.set(text, translated, source_lang, target_lang,
                                model_name='glm-4.7-flash')
                logger.info("翻译结果已缓存")
            except Exception as e:
                logger.warning(f"缓存翻译结果失败: {e}")

        if not translated:
            logger.error("所有翻译服务都不可用")

        return translated

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
        """翻译图书信息"""
        return _translate_book_info(self, book_data, target_lang)

    def translate_author_name(self, author: str) -> Optional[str]:
        """翻译作者名（委托给智谱AI服务）"""
        return self.zhipu.translate_author_name(author)

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.zhipu.is_available() or self._get_fallback() is not None

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        cache_service = self._get_cache_service()
        if cache_service:
            return cache_service.get_stats()
        return {'total_count': 0, 'message': '缓存服务不可用'}


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
