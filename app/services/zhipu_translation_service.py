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
        ('title', 'title_zh', 'title'),
        ('description', 'description_zh', 'description'),
        ('details', 'details_zh', 'details'),
    ]

    for src_key, dst_key, field_type in fields:
        if book_data.get(src_key) and not book_data.get(dst_key):
            translated = translator.translate(
                book_data[src_key],
                target_lang=target_lang,
                field_type=field_type
            )
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

    def __init__(self, api_key: Optional[str] = None, model: str = "glm-4.7-flash", app=None):
        """
        初始化智谱AI翻译服务

        Args:
            api_key: 智谱AI API密钥，如果不提供则从环境变量获取
            model: 使用的模型，默认glm-4.7-flash
            app: Flask应用实例，用于提供应用上下文
        """
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY")
        self.model = model
        self._client = None
        self._last_request_time = 0
        self._request_interval = 0.1
        self._author_name_cache: OrderedDict[str, str] = OrderedDict()
        self._author_name_cache_max_size = 1000
        self._cache_service = None
        self._app = app

        self._field_prompts: Dict[str, str] = {
            'title': (
                "你是一位资深图书翻译专家，正在翻译英文书名为中文。\n"
                "规则：\n"
                "- 文学性书名采用意译，体现文学美感\n"
                "- 专业书籍采用直译，保持准确性\n"
                "- 系列书籍保持系列名称一致性\n"
                "- 只输出翻译后的书名，不添加任何前缀、注释或解释\n"
                "- 禁止添加书名号《》\n"
                "- 禁止输出'书名：''翻译：'等标签\n"
                "- 禁止输出英文原文\n"
                "示例：\n"
                '"The Great Gatsby" → 了不起的盖茨比\n'
                '"Clean Code" → 代码整洁之道\n'
                '"The Night We Met" → 我们相遇的那晚'
            ),
            'description': (
                "你是一位资深图书翻译专家，正在翻译英文图书简介为中文。\n"
                "规则：\n"
                "- 准确传达原意，不添加原文没有的内容\n"
                "- 流畅自然，符合中文阅读习惯\n"
                "- 适当调整语序（英文常倒装，中文为主谓宾）\n"
                "- 专有名词（地名、机构名）保留英文或附原文\n"
                "- 去除'本书''作者'等冗余主语\n"
                "- 只输出翻译结果，不添加任何标签、注释或解释\n"
                "- 禁止输出'简介：''描述：''翻译：'等标签\n"
                "- 禁止使用Markdown格式"
            ),
            'details': (
                "你是一位资深图书翻译专家，正在翻译英文图书详情为中文。\n"
                "规则：\n"
                "- 准确翻译出版信息、页数、价格等详情\n"
                "- 数字和单位保持原格式\n"
                "- 出版社名优先使用中文官方译名\n"
                "- 只输出翻译结果，不添加任何标签、注释或解释\n"
                "- 禁止输出'详情：''翻译：'等标签\n"
                "- 禁止使用Markdown格式"
            ),
            'author': (
                "你是一位资深姓名翻译专家，正在将英文名字翻译为中文。\n"
                "规则：\n"
                "- 使用标准中文译名（参考维基百科、豆瓣）\n"
                "- 名和姓之间用间隔号·分隔\n"
                "- 只输出译名，不添加任何解释或注释\n"
                "- 禁止输出'作者：''翻译：'等标签\n"
                "示例：\n"
                '"Abby Jimenez" → 艾比·希门尼斯\n'
                '"Viola Davis" → 维奥拉·戴维斯'
            ),
            'text': (
                "你是一位资深翻译专家，将英文翻译为中文。\n"
                "规则：\n"
                "- 准确传达原意，不添加原文没有的内容\n"
                "- 符合中文表达习惯，避免翻译腔\n"
                "- 只输出翻译结果，不添加任何解释、注释或备注\n"
                "- 禁止输出'翻译：''译文：'等前缀\n"
                "- 禁止使用Markdown格式"
            ),
        }

    def _get_prompt_for_field(self, field_type: str) -> str:
        """获取字段类型对应的提示词"""
        return self._field_prompts.get(field_type, self._field_prompts['text'])

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
                  target_lang: str = 'zh', field_type: str = 'text') -> Optional[str]:
        """
        翻译文本

        Args:
            text: 要翻译的文本
            source_lang: 源语言代码（目前只支持en）
            target_lang: 目标语言代码（目前只支持zh）
            field_type: 字段类型（'title'/'description'/'details'/'text'），用于后处理

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

        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((ConnectionError, TimeoutError)),
            reraise=True,
        )
        def _call_api():
            return client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_prompt_for_field(field_type)},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=4096
            )

        try:
            response = _call_api()
            self._last_request_time = time.time()

            if response and response.choices:
                result = response.choices[0].message.content
                if result:
                    if not self._validate_translation(result, text):
                        logger.warning(f"翻译质量校验失败(含污染标记)，将尝试后处理: {result[:100]}")
                    result = self._postprocess_translation(result, field_type=field_type)
                    logger.info(f"智谱AI翻译成功: {text[:50]}... -> {result[:50]}...")
                    return result

        except Exception as e:
            logger.warning(f"智谱AI翻译失败(重试耗尽): {e}")

        return None

    def translate_batch(self, texts: List[str], source_lang: str = 'en',
                       target_lang: str = 'zh',
                       progress_callback=None,
                       max_workers: int = 3) -> List[str]:
        """
        批量翻译，使用缓存避免重复翻译，支持并行处理

        Args:
            texts: 文本列表
            source_lang: 源语言
            target_lang: 目标语言
            progress_callback: 进度回调函数 (current, total)
            max_workers: 最大并行线程数（默认3，避免API限流）

        Returns:
            翻译结果列表
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(texts)
        cache_hits = 0
        results = [None] * total
        to_translate = []  # (index, text) 需要翻译的项

        cache_service = self._get_cache_service()

        # 第一步：检查缓存
        from ..utils.api_helpers import clean_translation_text
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = text
                continue

            if cache_service:
                try:
                    cached = cache_service.get(text, source_lang, target_lang)
                    if cached:
                        results[i] = clean_translation_text(cached.translated_text)
                        cache_hits += 1
                        continue
                except Exception:
                    pass

            to_translate.append((i, text))

        # 第二步：并行翻译（控制并发避免API限流）
        if to_translate and self.is_available():
            def _translate_item(item):
                idx, txt = item
                result = self.translate(txt, source_lang, target_lang)
                return idx, result if result else txt

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_item = {
                    executor.submit(_translate_item, item): item
                    for item in to_translate
                }

                completed = 0
                for future in as_completed(future_to_item):
                    idx, result = future.result()
                    results[idx] = result
                    completed += 1

                    if progress_callback:
                        progress_callback(total - len(to_translate) + completed, total)

        logger.info(f"批量翻译完成: 共{total}条, 缓存命中{cache_hits}条, 并行翻译{len(to_translate)}条")
        return results

    def translate_book_info(self, book_data: Dict[str, Any],
                           target_lang: str = 'zh') -> Dict[str, Any]:
        """翻译图书信息"""
        return _translate_book_info(self, book_data, target_lang)

    @staticmethod
    def _postprocess_translation(text: str, field_type: str = 'text') -> str:
        """翻译结果后处理（委托到统一清洁函数）"""
        from ..utils.api_helpers import clean_translation_text
        return clean_translation_text(text, field_type=field_type)

    @staticmethod
    def _validate_translation(translated: str, source: str) -> bool:
        """校验翻译结果质量，返回True表示可接受"""
        if not translated:
            return True
        from ..utils.api_helpers import _DIRTY_MARKERS
        if any(marker in translated for marker in _DIRTY_MARKERS):
            return False
        if translated.strip() == source.strip():
            return False
        return True

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

        translated = self.translate(author, field_type='author')
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

    def __init__(self, zhipu_api_key: Optional[str] = None, app=None):
        """
        初始化混合翻译服务

        Args:
            zhipu_api_key: 智谱AI API密钥
            app: Flask应用实例，用于提供应用上下文
        """
        self.zhipu = ZhipuTranslationService(api_key=zhipu_api_key, app=app)
        self._fallback = None
        self._cache_service = None
        self._app = app

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

    def _run_with_context(self, func, *args):
        """在应用上下文中执行函数（如有app则自动推送上下文）"""
        if self._app:
            with self._app.app_context():
                return func(*args)
        return func(*args)

    def translate(self, text: str, source_lang: str = 'en',
                  target_lang: str = 'zh', field_type: str = 'text') -> Optional[str]:
        if not text or not text.strip():
            return text

        cache_service = self._get_cache_service()
        if cache_service:
            try:
                cached = self._run_with_context(
                    lambda: cache_service.get(text, source_lang, target_lang)
                )
                if cached:
                    from ..utils.api_helpers import clean_translation_text
                    result = clean_translation_text(cached.translated_text, field_type=field_type)
                    logger.debug("缓存命中，返回翻译结果（已后处理）")
                    return result
            except Exception as e:
                logger.debug(f"缓存读取失败: {e}")

        translated = None

        if self.zhipu.is_available():
            logger.info("使用智谱AI翻译...")
            translated = self.zhipu.translate(text, source_lang, target_lang, field_type=field_type)

        if not translated:
            fallback = self._get_fallback()
            if fallback:
                logger.info("使用备用翻译服务...")
                translated = fallback.translate(text, source_lang, target_lang)

        if translated and cache_service:
            try:
                from .translation_cache_service import TranslationCacheService
                cache_version = str(TranslationCacheService.CACHE_VERSION)
                self._run_with_context(
                    lambda: cache_service.set(
                        text, translated, source_lang, target_lang,
                        model_name='glm-4.7-flash',
                        model_version=cache_version
                    )
                )
                logger.info("翻译结果已缓存")
            except Exception as e:
                logger.warning(f"缓存翻译结果失败: {e}")

        if not translated:
            logger.error("所有翻译服务都不可用")

        return translated

    def translate_batch(self, texts: List[str], source_lang: str = 'en',
                       target_lang: str = 'zh',
                       progress_callback=None,
                       max_workers: int = 2) -> List[str]:
        """
        批量翻译（缓存预检+并行翻译）

        Args:
            texts: 文本列表
            source_lang: 源语言
            target_lang: 目标语言
            progress_callback: 进度回调函数 (current, total)
            max_workers: 最大并行线程数（默认2，适配Render免费版512MB内存）

        Returns:
            翻译结果列表
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(texts)
        cache_service = self._get_cache_service()
        results: List[Optional[str]] = [None] * total
        to_translate = []

        # 第一步：检查缓存
        from ..utils.api_helpers import clean_translation_text
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = text
                continue
            if cache_service:
                try:
                    cached = self._run_with_context(
                        lambda t=text: cache_service.get(t, source_lang, target_lang)
                    )
                    if cached:
                        results[i] = clean_translation_text(cached.translated_text)
                        continue
                except Exception:
                    pass
            to_translate.append((i, text))

        # 第二步：并行翻译
        if to_translate:
            def _translate_item(item):
                idx, txt = item
                result = self.translate(txt, source_lang, target_lang)
                return idx, result if result else txt

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_item = {
                    executor.submit(_translate_item, item): item
                    for item in to_translate
                }

                completed = 0
                for future in as_completed(future_to_item):
                    idx, result = future.result()
                    results[idx] = result
                    completed += 1
                    if progress_callback:
                        cache_hits = total - len(to_translate)
                        progress_callback(cache_hits + completed, total)

        logger.info(f"批量翻译完成: 共{total}条, 缓存命中{total - len(to_translate)}条, 并行翻译{len(to_translate)}条")
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


def get_translation_service(app=None) -> HybridTranslationService:
    """获取全局翻译服务实例（容错初始化）"""
    global _hybrid_translation_service
    if _hybrid_translation_service is None:
        _hybrid_translation_service = HybridTranslationService(app=app)
    return _hybrid_translation_service


def translate_text(text: str, source_lang: str = 'en',
                   target_lang: str = 'zh') -> Optional[str]:
    """翻译文本的便捷函数"""
    return get_translation_service().translate(text, source_lang, target_lang)


def translate_book_info(book_data: Dict[str, Any],
                       target_lang: str = 'zh') -> Dict[str, Any]:
    """翻译图书信息的便捷函数"""
    return get_translation_service().translate_book_info(book_data, target_lang)
