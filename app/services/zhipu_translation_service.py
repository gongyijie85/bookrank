"""
智谱AI GLM-4.7-Flash 翻译服务

使用智谱AI免费模型进行高质量翻译
支持批量翻译和流式输出
内置翻译缓存系统避免重复翻译
"""

import logging
import os
import re
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


def _translate_book_info(translator, book_data: dict[str, Any], target_lang: str = 'zh') -> dict[str, Any]:
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
            translated = translator.translate(book_data[src_key], target_lang=target_lang, field_type=field_type)
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

    def __init__(self, api_key: str | None = None, model: str | None = None, app=None):
        """
        初始化智谱AI翻译服务

        Args:
            api_key: 智谱AI API密钥，如果不提供则从环境变量获取
            model: 使用的模型，默认从 app.config 读取，回退到 'glm-4.7-flash'
            app: Flask应用实例，用于提供应用上下文
        """
        self.api_key = api_key or os.environ.get('ZHIPU_API_KEY')
        self._default_model = 'glm-4.7-flash'
        self._app = app
        # 如果提供了 model 参数则使用，否则从 app.config 读取
        if model is not None:
            self.model = model
        elif app is not None:
            self.model = app.config.get('ZHIPU_TRANSLATION_MODEL', self._default_model)
        else:
            self.model = self._default_model
        self._client = None
        self._last_request_time = 0
        self._request_interval = 0.1
        self._author_name_cache: OrderedDict[str, str] = OrderedDict()
        self._author_name_cache_max_size = 1000
        self._cache_service = None

        self._field_prompts: dict[str, str] = {
            'title': (
                '你是一位资深图书翻译专家，正在翻译英文书名为中文。\n'
                '规则：\n'
                '- 文学性书名采用意译，体现文学美感\n'
                '- 专业/技术书籍采用直译，保持准确性\n'
                '- 系列书籍保持系列名称一致性\n'
                '- 不添加书名号《》，只输出纯文字书名\n'
                '- 只输出翻译后的书名，不添加任何前缀、注释或解释\n'
                "- 禁止输出'书名：''翻译：'等标签\n"
                '- 禁止输出英文原文\n'
                "- 禁止添加'译''(译)'等后缀\n"
                '示例：\n'
                '"The Great Gatsby" → 了不起的盖茨比\n'
                '"Clean Code" → 代码整洁之道\n'
                '"The Night We Met" → 我们相遇的那晚\n'
                '"Atomic Habits" → 原子习惯\n'
                '"The Midnight Library" → 午夜图书馆\n'
                '"Dune" → 沙丘'
            ),
            'description': (
                '你是一位资深图书翻译专家，正在翻译英文图书简介为中文。\n'
                '规则：\n'
                '- 准确传达原意，不添加原文没有的内容\n'
                '- 流畅自然，符合中文阅读习惯\n'
                '- 适当调整语序（英文常倒装，中文为主谓宾）\n'
                '- 专有名词（地名、机构名）首次出现时附英文原文，如：纽约时报(New York Times)\n'
                '- 书名在简介中出现时用书名号《》，如：《百年孤独》\n'
                '- 引用语保留双引号'
                '\n'
                '- 只输出翻译结果，不添加任何标签、注释或解释\n'
                "- 禁止输出'简介：''描述：''翻译：'等标签\n"
                '- 禁止使用Markdown格式\n'
                "- 禁止添加'译'(译)等后缀标记"
            ),
            'details': (
                '你是一位资深图书翻译专家，正在翻译英文图书详情为中文。\n'
                '规则：\n'
                '- 准确翻译出版信息、页数、价格等详情\n'
                '- 数字和单位保持原格式（如 320页、$25.99）\n'
                '- 出版社名优先使用中文官方译名，附英文原名，如：企鹅出版社(Penguin Books)\n'
                '- ISBN号保持原样不翻译\n'
                '- 语言字段翻译为中文（如 English → 英语, Spanish → 西班牙语）\n'
                '- 只输出翻译结果，不添加任何标签、注释或解释\n'
                "- 禁止输出'详情：''翻译：'等标签\n"
                '- 禁止使用Markdown格式'
            ),
            'author': (
                '你是一位资深姓名翻译专家，正在将人名翻译为中文。\n'
                '规则：\n'
                '- 英语姓名：使用标准中文译名，名和姓之间用间隔号·分隔\n'
                '- 日本姓名：直接使用汉字或标准日文读音的中文译名\n'
                '- 韩国姓名：使用标准中文译名，名和姓之间用间隔号·分隔\n'
                '- 多作者用顿号、分隔，如：张三·李四、王五\n'
                '- 只输出译名，不添加任何解释或注释\n'
                "- 禁止输出'作者：''翻译：'等标签\n"
                '示例：\n'
                '"Abby Jimenez" → 艾比·希门尼斯\n'
                '"Viola Davis" → 维奥拉·戴维斯\n'
                '"Haruki Murakami" → 村上春树\n'
                '"Han Kang" → 韩江\n'
                '"George R.R. Martin" → 乔治·R·R·马丁'
            ),
            'text': (
                '你是一位资深翻译专家，将英文翻译为中文。\n'
                '规则：\n'
                '- 准确传达原意，不添加原文没有的内容\n'
                '- 符合中文表达习惯，避免翻译腔\n'
                '- 书名出现时用书名号《》\n'
                '- 只输出翻译结果，不添加任何解释、注释或备注\n'
                "- 禁止输出'翻译：''译文：'等前缀\n"
                '- 禁止使用Markdown格式\n'
                "- 禁止添加'译'(译)等后缀标记"
            ),
        }

    def _get_prompt_for_field(self, field_type: str) -> str:
        """获取字段类型对应的提示词"""
        return self._field_prompts.get(field_type, self._field_prompts['text'])

    def _get_client(self):
        """懒加载客户端"""
        if self._client is None:
            if not self.api_key:
                logger.warning('智谱AI API Key未配置，请设置ZHIPU_API_KEY环境变量')
                return None

            try:
                from zhipuai import ZhipuAI

                self._client = ZhipuAI(api_key=self.api_key)
                logger.info('智谱AI客户端初始化成功')
            except ImportError as e:
                logger.error(f'zhipuai库未安装: {e}，请运行: pip install zhipuai')
                return None
            except (ConnectionError, TimeoutError, RuntimeError) as e:
                logger.error(f'zhipuai库未安装或初始化失败: {e}，请运行: pip install zhipuai')
                return None

        return self._client

    def _get_cache_service(self):
        """获取翻译缓存服务"""
        if self._cache_service is None:
            try:
                from .translation_cache_service import get_translation_cache_service

                self._cache_service = get_translation_cache_service()
            except (ImportError, ModuleNotFoundError) as e:
                logger.warning(f'翻译缓存服务初始化失败: {e}')
        return self._cache_service

    def translate(
        self, text: str, source_lang: str = 'en', target_lang: str = 'zh', field_type: str = 'text'
    ) -> str | None:
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

        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

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
                    {'role': 'system', 'content': self._get_prompt_for_field(field_type)},
                    {'role': 'user', 'content': text},
                ],
                temperature=0.3,
                max_tokens=4096,
            )

        try:
            response = _call_api()
            self._last_request_time = time.time()

            if response and response.choices:
                result = response.choices[0].message.content
                if result:
                    if not self._validate_translation(result, text):
                        logger.warning(f'翻译质量校验失败(含污染标记)，将尝试后处理: {result[:100]}')
                    result = self._postprocess_translation(result, field_type=field_type)
                    logger.info(f'智谱AI翻译成功: {text[:50]}... -> {result[:50]}...')
                    return result

        except Exception as e:
            logger.warning(f'智谱AI翻译失败(重试耗尽): {e}')

        return None

    def translate_batch(
        self,
        texts: list[str],
        source_lang: str = 'en',
        target_lang: str = 'zh',
        progress_callback=None,
        max_workers: int = 3,
    ) -> list[str]:
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
                except (requests.RequestException, ValueError, KeyError) as e:
                    logger.debug(f'缓存读取失败: {e}')

            to_translate.append((i, text))

        # 第二步：并行翻译（控制并发避免API限流）
        if to_translate and self.is_available():

            def _translate_item(item):
                idx, txt = item
                result = self.translate(txt, source_lang, target_lang)
                return idx, result if result else txt

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_item = {executor.submit(_translate_item, item): item for item in to_translate}

                completed = 0
                for future in as_completed(future_to_item):
                    idx, result = future.result()
                    results[idx] = result
                    completed += 1

                    if progress_callback:
                        progress_callback(total - len(to_translate) + completed, total)

        logger.info(f'批量翻译完成: 共{total}条, 缓存命中{cache_hits}条, 并行翻译{len(to_translate)}条')
        return results

    def translate_book_info(self, book_data: dict[str, Any], target_lang: str = 'zh') -> dict[str, Any]:
        """翻译图书信息"""
        return _translate_book_info(self, book_data, target_lang)

    def translate_book_fields(
        self,
        title: str = '',
        description: str = '',
        details: str = '',
        source_lang: str = 'en',
        target_lang: str = 'zh',
    ) -> dict[str, str | None]:
        """
        合并翻译一本书的多个字段（单次API调用）

        将标题、描述、详情合并为一个请求发送给GLM，
        减少API调用次数从3次降为1次

        Args:
            title: 书名（英文）
            description: 简介（英文）
            details: 详情（英文）
            source_lang: 源语言
            target_lang: 目标语言

        Returns:
            包含 title_zh / description_zh / details_zh 的字典
        """
        from ..utils.api_helpers import clean_translation_text

        cache_service = self._get_cache_service()

        result: dict[str, str | None] = {
            'title_zh': None,
            'description_zh': None,
            'details_zh': None,
        }

        if cache_service:
            for field, key, field_type in [
                (title, 'title_zh', 'title'),
                (description, 'description_zh', 'description'),
                (details, 'details_zh', 'details'),
            ]:
                if field and field.strip():
                    try:
                        cached = cache_service.get(field, source_lang, target_lang)
                        if cached:
                            result[key] = clean_translation_text(cached.translated_text, field_type=field_type)
                    except Exception:
                        pass

        uncached_fields = []
        if title and title.strip() and not result['title_zh']:
            uncached_fields.append(('title', title))
        if description and description.strip() and not result['description_zh']:
            uncached_fields.append(('description', description))
        if details and details.strip() and not result['details_zh']:
            uncached_fields.append(('details', details))

        if not uncached_fields:
            return result

        client = self._get_client()
        if not client:
            for field_type, text in uncached_fields:
                single = self.translate(text, source_lang, target_lang, field_type=field_type)
                key = f'{field_type}_zh'
                if single:
                    result[key] = single
            return result

        combined_prompt = (
            '你是一位资深图书翻译专家，请将以下英文图书信息翻译为中文。\n'
            '请严格按JSON格式输出，包含以下键：\n'
            '- "title_zh": 书名翻译（纯文字，不加书名号《》）\n'
            '- "description_zh": 简介翻译\n'
            '- "details_zh": 详情翻译\n'
            '规则：\n'
            '- 书名：文学性意译/专业直译，不加《》和后缀\n'
            '- 简介：流畅自然，专有名词附原文，书中书名用《》\n'
            '- 详情：出版信息准确，出版社附英文原名，ISBN不翻译\n'
            '- 只输出JSON，不添加任何其他文字、注释或Markdown标记'
        )

        combined_text_parts = []
        if title and title.strip() and not result['title_zh']:
            combined_text_parts.append(f'Title: {title}')
        if description and description.strip() and not result['description_zh']:
            combined_text_parts.append(f'Description: {description}')
        if details and details.strip() and not result['details_zh']:
            combined_text_parts.append(f'Details: {details}')

        if not combined_text_parts:
            return result

        combined_text = '\n'.join(combined_text_parts)

        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((ConnectionError, TimeoutError)),
            reraise=True,
        )
        def _call_api():
            return client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'system', 'content': combined_prompt}, {'role': 'user', 'content': combined_text}],
                temperature=0.3,
                max_tokens=4096,
            )

        try:
            import json as _json

            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            if time_since_last < self._request_interval:
                time.sleep(self._request_interval - time_since_last)

            response = _call_api()
            self._last_request_time = time.time()

            if response and response.choices:
                content = response.choices[0].message.content
                if content:
                    content = content.strip()
                    if content.startswith('```'):
                        content = re.sub(r'^```(?:json)?\s*', '', content)
                        content = re.sub(r'\s*```$', '', content)
                    try:
                        parsed = _json.loads(content)
                    except _json.JSONDecodeError:
                        parsed = self._parse_json_from_text(content)

                    if parsed and isinstance(parsed, dict):
                        for key, field_type in [
                            ('title_zh', 'title'),
                            ('description_zh', 'description'),
                            ('details_zh', 'details'),
                        ]:
                            val = parsed.get(key)
                            if val and isinstance(val, str) and val.strip():
                                cleaned = clean_translation_text(val.strip(), field_type=field_type)
                                result[key] = cleaned

                        if cache_service:
                            src_map = {
                                'title': title,
                                'description': description,
                                'details': details,
                            }
                            for src_key, dst_key in [
                                ('title', 'title_zh'),
                                ('description', 'description_zh'),
                                ('details', 'details_zh'),
                            ]:
                                src_text = src_map.get(src_key, '')
                                translated_val = result.get(dst_key)
                                if src_text and translated_val:
                                    try:
                                        cache_service.set(
                                            src_text,
                                            translated_val,
                                            source_lang,
                                            target_lang,
                                            model_name=self.model,
                                            model_version=str(TranslationCacheService.CACHE_VERSION),
                                        )
                                    except Exception:
                                        pass

                        return result

        except Exception as e:
            logger.warning(f'合并翻译失败，回退到逐字段翻译: {e}')

        for field_type, text in uncached_fields:
            single = self.translate(text, source_lang, target_lang, field_type=field_type)
            key = f'{field_type}_zh'
            if single:
                result[key] = single

        return result

    @staticmethod
    def _parse_json_from_text(text: str) -> dict[str, Any] | None:
        """从可能包含非JSON内容的文本中提取JSON"""
        import json as _json

        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start != -1 and brace_end > brace_start:
            try:
                return _json.loads(text[brace_start : brace_end + 1])
            except _json.JSONDecodeError:
                pass
        return None

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
        return translated.strip() != source.strip()

    def translate_author_name(self, author: str) -> str | None:
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
            logger.debug(f'作者名缓存已清理 {remove_count} 条，当前大小: {len(self._author_name_cache)}')

        translated = self.translate(author, field_type='author')
        if translated:
            self._author_name_cache[author] = translated
            logger.debug(f'作者名已翻译并缓存: {author} -> {translated}')

        return translated

    def get_cache_stats(self) -> dict[str, Any]:
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

    def __init__(self, zhipu_api_key: str | None = None, app=None):
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
                logger.warning(f'翻译缓存服务初始化失败: {e}')
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

    def translate(
        self, text: str, source_lang: str = 'en', target_lang: str = 'zh', field_type: str = 'text'
    ) -> str | None:
        if not text or not text.strip():
            return text

        cache_service = self._get_cache_service()
        if cache_service:
            try:
                cached = self._run_with_context(lambda: cache_service.get(text, source_lang, target_lang))
                if cached:
                    from ..utils.api_helpers import clean_translation_text

                    result = clean_translation_text(cached.translated_text, field_type=field_type)
                    logger.debug('缓存命中，返回翻译结果（已后处理）')
                    return result
            except Exception as e:
                logger.debug(f'缓存读取失败: {e}')

        translated = None

        if self.zhipu.is_available():
            logger.info('使用智谱AI翻译...')
            translated = self.zhipu.translate(text, source_lang, target_lang, field_type=field_type)

        if not translated:
            fallback = self._get_fallback()
            if fallback:
                logger.info('使用备用翻译服务...')
                translated = fallback.translate(text, source_lang, target_lang)

        if translated and cache_service:
            try:
                from .translation_cache_service import TranslationCacheService

                cache_version = str(TranslationCacheService.CACHE_VERSION)
                self._run_with_context(
                    lambda: cache_service.set(
                        text,
                        translated,
                        source_lang,
                        target_lang,
                        model_name='glm-4.7-flash',
                        model_version=cache_version,
                    )
                )
                logger.info('翻译结果已缓存')
            except Exception as e:
                logger.warning(f'缓存翻译结果失败: {e}')

        if not translated:
            logger.error('所有翻译服务都不可用')

        return translated

    def translate_batch(
        self,
        texts: list[str],
        source_lang: str = 'en',
        target_lang: str = 'zh',
        progress_callback=None,
        max_workers: int = 2,
    ) -> list[str]:
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
        results: list[str | None] = [None] * total
        to_translate = []

        # 第一步：检查缓存
        from ..utils.api_helpers import clean_translation_text

        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = text
                continue
            if cache_service:
                try:
                    cached = self._run_with_context(lambda t=text: cache_service.get(t, source_lang, target_lang))
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
                future_to_item = {executor.submit(_translate_item, item): item for item in to_translate}

                completed = 0
                for future in as_completed(future_to_item):
                    idx, result = future.result()
                    results[idx] = result
                    completed += 1
                    if progress_callback:
                        cache_hits = total - len(to_translate)
                        progress_callback(cache_hits + completed, total)

        logger.info(f'批量翻译完成: 共{total}条, 缓存命中{total - len(to_translate)}条, 并行翻译{len(to_translate)}条')
        return results

    def translate_book_info(self, book_data: dict[str, Any], target_lang: str = 'zh') -> dict[str, Any]:
        """翻译图书信息"""
        return _translate_book_info(self, book_data, target_lang)

    def translate_book_fields(
        self,
        title: str = '',
        description: str = '',
        details: str = '',
        source_lang: str = 'en',
        target_lang: str = 'zh',
    ) -> dict[str, str | None]:
        """合并翻译一本书的多个字段（委托给智谱AI，单次API调用）"""
        return self.zhipu.translate_book_fields(
            title=title, description=description, details=details, source_lang=source_lang, target_lang=target_lang
        )

    def translate_author_name(self, author: str) -> str | None:
        """翻译作者名（委托给智谱AI服务）"""
        return self.zhipu.translate_author_name(author)

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.zhipu.is_available() or self._get_fallback() is not None

    def get_cache_stats(self) -> dict[str, Any]:
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


def translate_text(text: str, source_lang: str = 'en', target_lang: str = 'zh') -> str | None:
    """翻译文本的便捷函数"""
    return get_translation_service().translate(text, source_lang, target_lang)


def translate_book_info(book_data: dict[str, Any], target_lang: str = 'zh') -> dict[str, Any]:
    """翻译图书信息的便捷函数"""
    return get_translation_service().translate_book_info(book_data, target_lang)
