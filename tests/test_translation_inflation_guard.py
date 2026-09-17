"""「上下文注水」（译文膨胀）防线回归测试。

## 背景

2026-09-17 生产取证：卡片与详情页上的中文简介比英文原文长数倍，但内容**不是翻译** ——
模型拿图书上下文里的书名、作者、榜单名重新写了一段图书介绍：

- `AWESOME FRIENDLY KID`：英文 73 字符 → 中文 311 字符（4.26 倍），
  译文开头是「《超棒又友善的孩子》（AWESOME FRIENDLY KID）由杰夫·金尼创作，属于儿童与青少年系列…」
- `WARRIORS: THE PROPHECIES BEG`：英文 72 字符 → 中文 201 字符（2.79 倍）

根因是出版语境的翻译提示词把**出版社 / 榜单类别 / 系列**一并喂给了模型，同时又要求
「采用上下文中的书名与术语并保持一致」；短简介输入下，模型把这些事实当素材写进了译文。
而 `translate()` 里既有的质量校验**只打 warning、并不拦截**，坏值照样返回并写进缓存与语言包。

## 本文件锁住的三层

1. `is_inflated_translation` 判定本身（长度比率 + 上下文元信息泄漏）；
2. 提示词按字段裁剪上下文：简介/详情看不到出版社与榜单，书名翻译仍保留完整上下文；
3. `translate()` 命中后去掉上下文重译一次、仍不可信则丢弃（不缓存、不落库），
   以及 Hybrid 缓存读取时不再把旧的注水译文直接返回。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from app.services.zhipu_translation_service import (
    HybridTranslationService,
    ZhipuTranslationService,
)
from app.utils.api_helpers import INFLATION_GUARDED_FIELDS, is_inflated_translation


def _pad(text: str, total: int) -> str:
    """把文本补到指定字符数，让用例里的长度关系一眼可见。"""
    assert len(text) <= total, f'{len(text)} > {total}'
    return text + '的' * (total - len(text))


#: 英文原文（52 字符，量级与 NYT 的短摘要一致）
EN_SHORT = 'A new kid in town outshines Greg in every possible way.'
#: 忠实的短译文：中文字符数只有英文的约 0.33 倍（实测正常值中位数约 0.42）
ZH_FAITHFUL = '镇上新来的孩子样样都比格雷格强。'
#: 生产实测的注水译文（311 字符）：句式是模型自撰的图书介绍，含书名/作者/系列
ZH_INFLATED = _pad(
    '《超棒又友善的孩子》（AWESOME FRIENDLY KID）由杰夫·金尼创作，属于儿童与青少年系列，描写格雷格的新同学。',
    311,
)
#: 当时传给翻译的图书上下文
CONTEXT = {
    'title': 'AWESOME FRIENDLY KID',
    'author': 'Jeff Kinney',
    'publisher': 'Amulet',
    'list_name': "Children's & Young Adult Series",
}


def _api_response(content: str) -> Mock:
    """构造模拟的 OpenAI 兼容响应对象。"""
    response = Mock()
    choice = Mock()
    message = Mock()
    message.content = content
    choice.message = message
    response.choices = [choice]
    return response


def _siliconflow_service(responses: list[str]) -> tuple[ZhipuTranslationService, MagicMock]:
    """构造走 siliconflow（即 `_build_hunyuan_prompt`）路径的服务，客户端按序返回给定内容。"""
    service = ZhipuTranslationService(api_key='test-key')
    service.provider = 'siliconflow'
    client = MagicMock()
    client.chat.completions.create.side_effect = [_api_response(text) for text in responses]
    service._client = client
    return service, client


def _prompts(client: MagicMock) -> list[str]:
    """取出每次调用实际发出的 user 消息内容。"""
    return [call.kwargs['messages'][0]['content'] for call in client.chat.completions.create.call_args_list]


class TestIsInflatedTranslation:
    """长度比率与元信息泄漏两条判定。"""

    def test_faithful_translation_passes(self):
        assert is_inflated_translation(EN_SHORT, ZH_FAITHFUL, CONTEXT) is False

    def test_production_case_is_flagged(self):
        """生产实测的 4.26 倍译文必须被判为不可信。"""
        assert is_inflated_translation(EN_SHORT, ZH_INFLATED, CONTEXT) is True

    def test_length_ratio_alone_is_enough(self):
        """即使不含任何上下文元信息，长度暴涨本身也足以判定。"""
        assert is_inflated_translation(EN_SHORT, _pad('这是一段被写长的译文。', 300)) is True

    def test_short_source_is_exempt_from_the_ratio_rule(self):
        """短文本的比率不稳定：译文不足 120 字符时不按比率判定。"""
        source = 'A New York Times bestseller.'  # 28 字符
        translated = _pad('纽约时报畅销书。', 110)  # 3.9 倍，但未达绝对长度下限
        assert is_inflated_translation(source, translated) is False

    def test_publisher_leak_is_flagged_without_length_blowup(self):
        """长度正常但把出版社写进译文，同样要判出来 —— 两条规则互相独立。"""
        source = (
            'A taut thriller about a family secret that resurfaces decades later, '
            'forcing two estranged sisters to confront what they buried. '
            'Their reunion unearths more than either of them expected.'
        )
        translated = _pad('这本书由 Scribner 出版，讲述了一个关于成长的故事。', 210)  # 约 1.05 倍
        assert len(translated) <= len(source) * 1.5, '本用例要验证的是非长度路径'
        assert is_inflated_translation(source, translated, {'publisher': 'Scribner'}) is True

    def test_metadata_already_in_source_is_not_flagged(self):
        """原文自己提到了出版社，就不算泄漏。"""
        source = (
            'Published by Scribner, this taut thriller follows two estranged sisters '
            'as a decades-old family secret resurfaces and forces them to confront '
            'what they buried long before either of them left home.'
        )
        translated = _pad('由 Scribner 出版，这部惊悚小说讲述了两个疏远的姐妹的故事。', 200)
        assert is_inflated_translation(source, translated, {'publisher': 'Scribner'}) is False

    def test_short_metadata_values_are_ignored(self):
        """过短的元信息值（如 'N/A'）不参与泄漏判定，避免误伤。"""
        source = (
            'A sweeping family saga that follows three generations of a fishing village '
            'through war, migration and the slow return of the tide, told through the '
            'eyes of the youngest daughter.'
        )
        translated = _pad('一部跨越三代人的家族史诗。', 150)
        assert len(translated) <= len(source) * 1.5, '本用例要验证的是元信息路径'
        assert is_inflated_translation(source, translated, {'publisher': 'N/A', 'series': 'A'}) is False

    def test_empty_inputs_are_safe(self):
        assert is_inflated_translation(None, ZH_INFLATED, CONTEXT) is False
        assert is_inflated_translation(EN_SHORT, None, CONTEXT) is False
        assert is_inflated_translation('', '', CONTEXT) is False

    def test_object_context_is_supported(self):
        """上下文既可能是 dict，也可能是带同名属性的对象。"""
        translated = _pad('由 Scribner 出版，讲述一个关于成长的故事。', 210)
        source = 'A taut thriller about a family secret that resurfaces decades later. ' * 3
        assert is_inflated_translation(source, translated, SimpleNamespace(publisher='Scribner')) is True


class TestPromptContextIsScoped:
    """提示词只给该字段需要的上下文。"""

    def test_guarded_fields_are_description_and_details(self):
        assert frozenset({'description', 'details'}) == INFLATION_GUARDED_FIELDS

    def test_description_prompt_hides_publisher_and_list_name(self):
        prompt = ZhipuTranslationService._build_hunyuan_prompt(EN_SHORT, 'zh', 'description', CONTEXT)
        assert 'Amulet' not in prompt, '出版社不该出现在简介提示词里 —— 这正是译文被注水的来源'
        assert "Children's & Young Adult Series" not in prompt, '榜单类别不该出现在简介提示词里'

    def test_details_prompt_hides_publisher_and_list_name(self):
        prompt = ZhipuTranslationService._build_hunyuan_prompt(EN_SHORT, 'zh', 'details', CONTEXT)
        assert 'Amulet' not in prompt
        assert "Children's & Young Adult Series" not in prompt

    def test_description_prompt_keeps_title_and_glossary(self):
        """统一译名仍然需要书名、作者与术语表。"""
        context = dict(CONTEXT, glossary={'Greg': '格雷格'})
        prompt = ZhipuTranslationService._build_hunyuan_prompt(EN_SHORT, 'zh', 'description', context)
        assert 'AWESOME FRIENDLY KID' in prompt
        assert 'Jeff Kinney' in prompt
        assert '格雷格' in prompt

    def test_description_prompt_states_the_no_new_facts_rule(self):
        prompt = ZhipuTranslationService._build_hunyuan_prompt(EN_SHORT, 'zh', 'description', CONTEXT)
        assert '不得出现原文没有的任何事实' in prompt
        assert '出版社' in prompt  # 明确点名不许提的东西

    def test_title_prompt_still_sees_full_context(self):
        """书名翻译本就靠体裁与简介判断含义，保持完整上下文。"""
        prompt = ZhipuTranslationService._build_hunyuan_prompt('AWESOME FRIENDLY KID', 'zh', 'title', CONTEXT)
        assert 'Amulet' in prompt
        assert "Children's & Young Adult Series" in prompt

    def test_unknown_field_type_keeps_full_context(self):
        """只给实证出问题的字段设限：其它字段仍拿到完整上下文。"""
        rendered = ZhipuTranslationService._context_for_prompt('text', CONTEXT)
        assert 'Amulet' in rendered
        assert "Children's & Young Adult Series" in rendered

    def test_description_context_scope_is_the_only_narrowing(self):
        """简介/详情之外，白名单不应意外收窄 —— 逐一比对字段全集。"""
        full = ZhipuTranslationService._context_for_prompt('title', CONTEXT)
        for field in ('英文书名', '作者', '出版社', '榜单类别'):
            assert field in full, f'书名上下文不该丢掉 {field}'

    def test_non_chinese_target_is_untouched(self):
        prompt = ZhipuTranslationService._build_hunyuan_prompt(EN_SHORT, 'en', 'description', CONTEXT)
        assert 'Amulet' not in prompt
        assert EN_SHORT in prompt


class TestTranslateGuardsContextInflation:
    """`translate()` 的重译与丢弃行为。"""

    def test_inflated_result_is_replaced_by_a_context_free_retry(self):
        service, client = _siliconflow_service([ZH_INFLATED, ZH_FAITHFUL])

        result = service.translate(EN_SHORT, 'en', 'zh', field_type='description', context=CONTEXT)

        assert result == ZH_FAITHFUL
        prompts = _prompts(client)
        assert len(prompts) == 2, '应当且只应当重译一次'
        assert 'Jeff Kinney' in prompts[0], '第一次带（已裁剪的）上下文'
        assert 'Jeff Kinney' not in prompts[1], '重译必须去掉上下文'
        assert '无额外上下文' in prompts[1]

    def test_inflation_surviving_the_retry_is_dropped(self):
        """两次都不可信时返回 None —— 宁可不翻译，也不能把自撰介绍当成译文。"""
        service, client = _siliconflow_service([ZH_INFLATED, ZH_INFLATED])

        assert service.translate(EN_SHORT, 'en', 'zh', field_type='description', context=CONTEXT) is None
        assert client.chat.completions.create.call_count == 2

    def test_clean_translation_needs_no_retry(self):
        service, client = _siliconflow_service([ZH_FAITHFUL])

        assert service.translate(EN_SHORT, 'en', 'zh', field_type='description', context=CONTEXT) == ZH_FAITHFUL
        assert client.chat.completions.create.call_count == 1

    def test_title_is_not_subject_to_the_guard(self):
        """书名这类短字段不启用防线，正常返回、不触发重译。"""
        long_title = _pad('《超棒又友善的孩子》', 200)
        service, client = _siliconflow_service([long_title])

        assert service.translate('AWESOME FRIENDLY KID', 'en', 'zh', field_type='title', context=CONTEXT) is not None
        assert client.chat.completions.create.call_count == 1

    def test_dict_context_is_accepted(self):
        service, _client = _siliconflow_service([ZH_FAITHFUL])
        assert service.translate(EN_SHORT, 'en', 'zh', field_type='description', context=CONTEXT) == ZH_FAITHFUL


class TestHybridCacheTreatsInflatedValueAsMiss:
    """旧缓存里的注水译文不再被直接返回，而是触发重译（自愈）。"""

    @staticmethod
    def _service_with_cache(cached_text: str | None, fresh: str | None):
        service = HybridTranslationService(zhipu_api_key='test-key')
        cache_service = Mock()
        cache_service.get.return_value = None if cached_text is None else SimpleNamespace(translated_text=cached_text)
        service._cache_service = cache_service
        return service, cache_service

    def test_inflated_cached_value_is_not_returned(self):
        service, _cache = self._service_with_cache(ZH_INFLATED, ZH_FAITHFUL)
        with (
            patch.object(service.zhipu, 'is_available', return_value=True),
            patch.object(service.zhipu, 'translate', return_value=ZH_FAITHFUL) as mock_translate,
        ):
            result = service.translate(EN_SHORT, 'en', 'zh', field_type='description', context=CONTEXT)

        assert result == ZH_FAITHFUL
        mock_translate.assert_called_once()

    def test_clean_cached_value_is_still_served(self):
        service, _cache = self._service_with_cache(ZH_FAITHFUL, None)
        with patch.object(service.zhipu, 'translate', return_value='不应被调用') as mock_translate:
            result = service.translate(EN_SHORT, 'en', 'zh', field_type='description', context=CONTEXT)

        assert result == ZH_FAITHFUL
        mock_translate.assert_not_called()
