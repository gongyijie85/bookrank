"""
智谱AI GLM-4.7-Flash 翻译服务

使用智谱AI免费模型进行高质量翻译
支持批量翻译和流式输出
内置翻译缓存系统避免重复翻译
"""

import json
import logging
import os
import re
import time
from functools import lru_cache
from typing import Any

from ..utils.api_helpers import clean_translation_text
from ..utils.error_handler import ErrorCategory, log_error
from .api_utils import run_with_app_context

logger = logging.getLogger(__name__)

_AUTHOR_TRANSLATION_MISS = object()


@lru_cache(maxsize=1000)
def _cached_translate_author_name(translator: Any, author: str) -> Any:
    """翻译作者名（带 lru_cache）；失败用哨兵值避免缓存 None。"""
    translated = translator.translate(author, field_type='author')
    return translated if translated is not None else _AUTHOR_TRANSLATION_MISS


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
            try:
                translated = translator.translate(
                    book_data[src_key], target_lang=target_lang, field_type=field_type, context=book_data
                )
            except TypeError:
                # 兼容只实现旧 translate 签名的测试替身和第三方适配器。
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

    PROMPT_VERSION = 'book-publishing-v1'
    _CONTEXT_FIELDS = (
        'title',
        'title_zh',
        'author',
        'category',
        'category_name',
        'list_name',
        'series',
        'publisher',
        'description',
        'glossary',
    )

    def __init__(self, api_key: str | None = None, model: str | None = None, app=None):
        """
        初始化智谱AI翻译服务

        Args:
            api_key: 智谱AI API密钥，如果不提供则从环境变量获取
            model: 使用的模型，默认从 app.config 读取，回退到 'glm-4.7-flash'
            app: Flask应用实例，用于提供应用上下文
        """
        self._default_model = 'glm-4.7-flash'
        self._app = app

        # provider: 'zhipu'（智谱 GLM，免费）| 'siliconflow'（硅基流动 Hunyuan-MT-7B，付费）
        # 默认走硅基流动 Hunyuan（线上实测期）；TRANSLATION_PROVIDER=zhipu 一键回退智谱。
        self.provider = 'zhipu'
        if app is not None:
            self.provider = app.config.get('TRANSLATION_PROVIDER', 'zhipu')
        if self.provider not in ('zhipu', 'siliconflow'):
            logger.warning(f'未知 TRANSLATION_PROVIDER={self.provider!r}，回退为 zhipu')
            self.provider = 'zhipu'

        # API Key 与端点按 provider 选择
        env_key = 'SILICONFLOW_API_KEY' if self.provider == 'siliconflow' else 'ZHIPU_API_KEY'
        self.api_key = api_key or os.environ.get(env_key)
        self.base_url = None
        if app is not None:
            self.base_url = app.config.get('SILICONFLOW_BASE_URL')

        # 模型名：显式构造参数始终优先；配置模型按 provider 分开读取。
        # TRANSLATION_MODEL 属于 siliconflow，避免 Render 固定的 Hunyuan 模型破坏
        # TRANSLATION_PROVIDER=zhipu 的单变量回退；zhipu 继续使用旧配置键。
        if model is not None:
            self.model = model
        elif app is not None and self.provider == 'siliconflow' and app.config.get('TRANSLATION_MODEL'):
            self.model = app.config['TRANSLATION_MODEL']
        elif app is not None and self.provider == 'siliconflow':
            self.model = 'tencent/Hunyuan-MT-7B'
        elif app is not None:
            self.model = app.config.get('ZHIPU_TRANSLATION_MODEL', self._default_model)
        else:
            self.model = self._default_model

        # 合并 JSON 单次调用：zhipu 默认启用（已上线验证）；siliconflow 的 MT 模型默认逐字段，
        # 避免 JSON 输出不稳。可被 TRANSLATION_USE_MERGED_JSON 显式覆盖。
        merged_override = app.config.get('TRANSLATION_USE_MERGED_JSON') if app is not None else None
        self.use_merged_json = merged_override if merged_override is not None else (self.provider == 'zhipu')

        self._client = None
        self._last_request_time = 0
        self._request_interval = 0.1
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

    @classmethod
    def _normalize_book_context(cls, context: dict[str, Any] | Any | None) -> dict[str, Any]:
        """提取稳定、紧凑的图书上下文，供提示和缓存共同使用。"""
        if context is None:
            return {}

        normalized: dict[str, Any] = {}
        for field in cls._CONTEXT_FIELDS:
            value = context.get(field) if isinstance(context, dict) else getattr(context, field, None)
            if value is None or value == '':
                continue
            if isinstance(value, (dict, list, tuple)):
                normalized[field] = value
                continue
            cleaned = str(value).strip()
            if not cleaned:
                continue
            # 简介只用于消歧；限制长度可避免详情字段把提示膨胀到不可控。
            normalized[field] = cleaned[:1600] if field == 'description' else cleaned[:400]
        return normalized

    @classmethod
    def build_cache_context(cls, field_type: str, context: dict[str, Any] | Any | None = None) -> str:
        """返回包含提示版本、字段类型和图书语境的稳定缓存标识。"""
        payload = {
            'prompt_version': cls.PROMPT_VERSION,
            'field_type': field_type,
            'book_context': cls._normalize_book_context(context),
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            default=str,
        )

    @classmethod
    def _format_book_context(cls, context: dict[str, Any] | Any | None) -> str:
        values = cls._normalize_book_context(context)
        labels = {
            'title': '英文书名',
            'title_zh': '已确定中文书名',
            'author': '作者',
            'category': '类别',
            'category_name': '中文类别',
            'list_name': '榜单类别',
            'series': '系列',
            'publisher': '出版社',
            'description': '内容简介',
            'glossary': '术语表',
        }
        lines = []
        for field, value in values.items():
            rendered = (
                json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list, tuple)) else value
            )
            lines.append(f'{labels[field]}：{rendered}')
        return '\n'.join(lines) if lines else '无额外上下文'

    @classmethod
    def _build_hunyuan_prompt(
        cls,
        text: str,
        target_lang: str,
        field_type: str,
        context: dict[str, Any] | Any | None = None,
    ) -> str:
        """构造符合 Hunyuan-MT 单 user 消息格式的出版翻译提示。"""
        if target_lang != 'zh':
            return f'Translate the following segment into {target_lang}, without additional explanation.\n\n{text}'

        book_context = cls._format_book_context(context)
        prompts = {
            'title': (
                '将下面的英文图书标题翻译成专业、自然的简体中文出版书名。只输出一个最终书名，'
                '不要加书名号、英文原文或解释。\n\n'
                '要求：结合作者、体裁和简介判断标题含义；允许有依据的意译和有限创译，优先保留作品的'
                '核心含义、意象、情绪与类型气质；人名标题不必机械音译，若词义与主题相关可自然意译；'
                '采用已确定译名和术语表；避免生硬逐字翻译、翻译腔、空泛套话及原文无依据的情节暗示。\n\n'
                f'图书上下文（仅用于消歧）：\n{book_context}\n\n英文书名：\n{text}'
            ),
            'description': (
                '将下面的英文图书简介翻译成专业、自然的简体中文。只输出译文，不要解释或使用 Markdown。\n\n'
                '要求：完整忠实，不遗漏、不增添、不改变人物关系和情节；在准确的基础上使用凝练、流畅、'
                '有节奏的现代中文，保留原文语气、悬念和体裁风格；采用上下文中的书名与术语并保持一致；'
                '人物名不附英文，书名使用《》；保留原有段落结构。\n\n'
                f'图书上下文：\n{book_context}\n\n待翻译简介：\n{text}'
            ),
            'details': (
                '将下面的英文图书详情翻译成准确、自然的简体中文。只输出译文，不要解释或使用 Markdown。\n\n'
                '要求：不增删事实；采用上下文中的书名与术语；保留段落、数字、日期、价格、ISBN及专有标识；'
                '出版与装帧信息使用规范中文表达。\n\n'
                f'图书上下文：\n{book_context}\n\n待翻译详情：\n{text}'
            ),
            'author': (
                '将下面的作者姓名翻译成规范简体中文译名。优先采用公认译名，否则按通行音译规则处理；'
                '只输出姓名，不要解释。\n\n' + text
            ),
            'text': '把下面的文本翻译成自然、准确的简体中文，不要额外解释。\n\n' + text,
        }
        return prompts.get(field_type, prompts['text'])

    def _get_client(self):
        """懒加载客户端（按 provider 选择 zhipuai / openai 兼容客户端）"""
        if self._client is None:
            if not self.api_key:
                if self.provider == 'siliconflow':
                    logger.warning('硅基流动 API Key未配置，请设置SILICONFLOW_API_KEY环境变量')
                else:
                    logger.warning('智谱AI API Key未配置，请设置ZHIPU_API_KEY环境变量')
                return None

            try:
                if self.provider == 'siliconflow':
                    from openai import OpenAI

                    self._client = OpenAI(
                        api_key=self.api_key,
                        base_url=self.base_url or 'https://api.siliconflow.cn/v1',
                        timeout=60.0,
                    )
                    logger.info('硅基流动(Hunyuan-MT-7B)客户端初始化成功')
                else:
                    from zhipuai import ZhipuAI

                    # 显式超时：SDK 默认超时过长（可达数百秒），后台批量同步时
                    # 单次翻译挂起会成倍放大（每本书 2 个字段×重试），必须封顶。
                    self._client = ZhipuAI(api_key=self.api_key, timeout=60.0)
                    logger.info('智谱AI客户端初始化成功')
            except ImportError as e:
                lib = 'openai' if self.provider == 'siliconflow' else 'zhipuai'
                logger.error(f'{lib}库未安装: {e}，请运行: pip install {lib}')
                return None
            except (ConnectionError, TimeoutError, RuntimeError) as e:
                lib = 'openai' if self.provider == 'siliconflow' else 'zhipuai'
                logger.error(f'{lib}库初始化失败: {e}，请运行: pip install {lib}')
                return None

        return self._client

    def _get_cache_service(self):
        """获取翻译缓存服务"""
        if self._cache_service is None:
            try:
                from .translation_cache_service import get_translation_cache_service

                self._cache_service = get_translation_cache_service()
            except (ImportError, ModuleNotFoundError) as e:
                log_error(ErrorCategory.TRANSLATION, f'翻译缓存服务初始化失败: {e}', level='warning')
        return self._cache_service

    def translate(
        self,
        text: str,
        source_lang: str = 'en',
        target_lang: str = 'zh',
        field_type: str = 'text',
        context: dict[str, Any] | Any | None = None,
    ) -> str | None:
        """
        翻译文本

        Args:
            text: 要翻译的文本
            source_lang: 源语言代码（目前只支持en）
            target_lang: 目标语言代码（目前只支持zh）
            field_type: 字段类型（'title'/'description'/'details'/'text'），用于后处理
            context: 作者、类别、简介、系列与术语表等图书上下文

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
            if self.provider == 'siliconflow':
                return client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            'role': 'user',
                            'content': self._build_hunyuan_prompt(text, target_lang, field_type, context),
                        }
                    ],
                    temperature=0.7,
                    top_p=0.6,
                    frequency_penalty=0,
                    max_tokens=4096,
                    extra_body={'top_k': 20, 'repetition_penalty': 1.05},
                )
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
                    result = clean_translation_text(result, field_type=field_type)
                    logger.info(f'智谱AI翻译成功: {text[:50]}... -> {result[:50]}...')
                    return result

        except Exception as e:
            log_error(ErrorCategory.TRANSLATION, f'智谱AI翻译失败(重试耗尽): {e}', level='warning')

        return None

    def translate_batch(
        self,
        texts: list[str],
        source_lang: str = 'en',
        target_lang: str = 'zh',
        progress_callback=None,
        max_workers: int = 3,
    ) -> list[str | None]:
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
        results: list[str | None] = [None] * total
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
                    cached = cache_service.get(text, source_lang, target_lang, model_name=self.model)
                    if cached:
                        results[i] = clean_translation_text(cached.translated_text)
                        cache_hits += 1
                        continue
                except (ValueError, KeyError) as e:
                    log_error(ErrorCategory.TRANSLATION, f'缓存读取失败: {e}', level='warning')

            to_translate.append((i, text))

        # 第二步：并行翻译（控制并发避免API限流）
        if to_translate and self.is_available():

            def _translate_item(item):
                idx, txt = item
                result = self.translate(txt, source_lang, target_lang)
                return idx, result if result else txt

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_item = {executor.submit(_translate_item, item): item for item in to_translate}

                for completed, future in enumerate(as_completed(future_to_item)):
                    idx, result = future.result()
                    results[idx] = result

                    if progress_callback:
                        progress_callback(total - len(to_translate) + completed + 1, total)

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
        context: dict[str, Any] | None = None,
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
            context: 作者、类别、系列、出版社和术语表等图书上下文

        Returns:
            包含 title_zh / description_zh / details_zh 的字典
        """
        from ..utils.api_helpers import clean_translation_text

        cache_service = self._get_cache_service()
        book_context = dict(context or {})
        book_context.setdefault('title', title)
        book_context.setdefault('description', description)

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
                        cache_context = (
                            self.build_cache_context(field_type, book_context)
                            if self.provider == 'siliconflow'
                            else None
                        )
                        cache_kwargs = {'model_name': self.model}
                        if cache_context:
                            cache_kwargs['cache_context'] = cache_context
                        cached = cache_service.get(field, source_lang, target_lang, **cache_kwargs)
                        if cached:
                            result[key] = clean_translation_text(cached.translated_text, field_type=field_type)
                    except Exception as e:
                        log_error(ErrorCategory.TRANSLATION, f'读取翻译缓存失败 key={key}: {e}', level='warning')

        uncached_fields = []
        if title and title.strip() and not result['title_zh']:
            uncached_fields.append(('title', title))
        if description and description.strip() and not result['description_zh']:
            uncached_fields.append(('description', description))
        if details and details.strip() and not result['details_zh']:
            uncached_fields.append(('details', details))

        if not uncached_fields:
            return result

        # 合并 JSON 单次调用：zhipu 默认启用；siliconflow 的 MT 模型默认逐字段（JSON 输出不稳）。
        # 当 use_merged_json=False 时 client 为 None，走下方逐字段回退逻辑。
        client = self._get_client() if self.use_merged_json else None
        if not client:
            for field_type, text in uncached_fields:
                translate_kwargs: dict[str, Any] = {'field_type': field_type}
                if self.provider == 'siliconflow':
                    translate_kwargs['context'] = book_context
                single = self.translate(text, source_lang, target_lang, **translate_kwargs)
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
                                        from .translation_cache_service import TranslationCacheService

                                        cache_service.set(
                                            src_text,
                                            translated_val,
                                            source_lang,
                                            target_lang,
                                            model_name=self.model,
                                            model_version=str(TranslationCacheService.CACHE_VERSION),
                                        )
                                    except Exception as cache_err:
                                        logger.debug(f'翻译缓存写入失败: {cache_err}')

                        return result

        except Exception as e:
            logger.warning(f'合并翻译失败，回退到逐字段翻译: {e}')

        for field_type, text in uncached_fields:
            translate_kwargs = {'field_type': field_type}
            if self.provider == 'siliconflow':
                translate_kwargs['context'] = book_context
            single = self.translate(text, source_lang, target_lang, **translate_kwargs)
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
    def _validate_translation(translated: str, source: str) -> bool:
        """校验翻译结果质量，返回True表示可接受"""
        if not translated:
            return True
        from ..utils.api_helpers import _DIRTY_MARKERS

        if any(marker in translated for marker in _DIRTY_MARKERS):
            return False
        return translated.strip() != source.strip()

    def _translate_author_name_cached(self, author: str) -> Any:
        return _cached_translate_author_name(self, author)

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
        result = self._translate_author_name_cached(author)
        return None if result is _AUTHOR_TRANSLATION_MISS else result

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

    FALLBACK_MODEL_NAME = 'google-translate'

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
                log_error(ErrorCategory.TRANSLATION, f'翻译缓存服务初始化失败: {e}', level='warning')
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

    def translate(
        self,
        text: str,
        source_lang: str = 'en',
        target_lang: str = 'zh',
        field_type: str = 'text',
        context: dict[str, Any] | Any | None = None,
    ) -> str | None:
        if not text or not text.strip():
            return text

        cache_service = self._get_cache_service()
        cache_context = (
            self.zhipu.build_cache_context(field_type, context) if self.zhipu.provider == 'siliconflow' else None
        )
        if cache_service:
            try:
                cache_kwargs = {'model_name': self.zhipu.model}
                if cache_context:
                    cache_kwargs['cache_context'] = cache_context
                cached = run_with_app_context(
                    self._app,
                    lambda: cache_service.get(text, source_lang, target_lang, **cache_kwargs),
                )
                if cached:
                    from ..utils.api_helpers import clean_translation_text

                    result = clean_translation_text(cached.translated_text, field_type=field_type)
                    logger.debug('缓存命中，返回翻译结果（已后处理）')
                    return result
            except Exception as e:
                log_error(ErrorCategory.TRANSLATION, f'缓存读取失败: {e}', level='warning')

        translated = None
        used_fallback = False

        if self.zhipu.is_available():
            logger.info('使用智谱AI翻译...')
            translate_kwargs = {'field_type': field_type}
            if self.zhipu.provider == 'siliconflow':
                translate_kwargs['context'] = context
            translated = self.zhipu.translate(text, source_lang, target_lang, **translate_kwargs)

        if not translated:
            fallback = self._get_fallback()
            if fallback:
                logger.info('使用备用翻译服务...')
                translated = fallback.translate(text, source_lang, target_lang)
                used_fallback = bool(translated)

        if translated and cache_service:
            try:
                from .translation_cache_service import TranslationCacheService

                cache_version = str(TranslationCacheService.CACHE_VERSION)

                cache_set_kwargs = {
                    'model_name': self.FALLBACK_MODEL_NAME if used_fallback else self.zhipu.model,
                    'model_version': cache_version,
                }
                if cache_context and not used_fallback:
                    cache_set_kwargs['cache_context'] = cache_context
                run_with_app_context(
                    self._app,
                    lambda: cache_service.set(
                        text,
                        translated,
                        source_lang,
                        target_lang,
                        **cache_set_kwargs,
                    ),
                )
                logger.info('翻译结果已缓存')
            except Exception as e:
                log_error(ErrorCategory.TRANSLATION, f'缓存翻译结果失败: {e}', level='warning')

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
    ) -> list[str | None]:
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
                    cached = run_with_app_context(
                        self._app,
                        lambda t=text: cache_service.get(t, source_lang, target_lang, model_name=self.zhipu.model),
                    )
                    if cached:
                        results[i] = clean_translation_text(cached.translated_text)
                        continue
                except Exception as e:
                    log_error(
                        ErrorCategory.TRANSLATION, f'批量翻译缓存查找失败 text[{i}]={text[:30]}: {e}', level='warning'
                    )
            to_translate.append((i, text))

        # 第二步：并行翻译
        if to_translate:

            def _translate_item(item):
                idx, txt = item
                result = self.translate(txt, source_lang, target_lang)
                return idx, result if result else txt

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_item = {executor.submit(_translate_item, item): item for item in to_translate}

                for completed, future in enumerate(as_completed(future_to_item)):
                    idx, result = future.result()
                    results[idx] = result
                    if progress_callback:
                        cache_hits = total - len(to_translate)
                        progress_callback(cache_hits + completed + 1, total)

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
        context: dict[str, Any] | None = None,
    ) -> dict[str, str | None]:
        """合并翻译一本书的多个字段（委托给智谱AI，单次API调用）"""
        kwargs: dict[str, Any] = {
            'title': title,
            'description': description,
            'details': details,
            'source_lang': source_lang,
            'target_lang': target_lang,
        }
        if context is not None:
            kwargs['context'] = context
        return self.zhipu.translate_book_fields(
            **kwargs,
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
