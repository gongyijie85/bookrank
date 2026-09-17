"""导出服务测试"""

import json
from datetime import date
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fpdf import FPDF
from openpyxl import load_workbook

from app.services.export_service import ExportService
from app.utils.weekly_report_presentation import prepare_report_presentation


@pytest.fixture
def export_service():
    return ExportService()


@pytest.fixture
def mock_report():
    """模拟周报对象"""
    report = MagicMock()
    report.title = 'Weekly Bestseller Report 2024 Week 3'
    report.report_date = date(2024, 1, 21)
    report.week_start = date(2024, 1, 15)
    report.week_end = date(2024, 1, 21)
    report.summary = '15 new books on the list, 3 rose significantly in rank.'
    report.content = json.dumps(
        {
            'top_changes': [
                {'title': 'Book A', 'author': 'Author A', 'category': 'Fiction', 'rank_change': 5},
                {'title': 'Book B', 'author': 'Author B', 'category': 'Non-Fiction', 'rank_change': -3},
                {'title': 'Book C', 'author': 'Author C', 'category': 'Fiction', 'rank_change': 0},
            ],
            'featured_books': [
                {'title': 'Featured Book', 'author': 'Featured Author', 'reason': 'Great reviews'},
            ],
        }
    )
    return report


@pytest.fixture
def mock_report_no_content():
    """模拟无详细内容的周报"""
    report = MagicMock()
    report.title = 'Simple Report'
    report.report_date = date(2024, 2, 1)
    report.week_start = date(2024, 1, 29)
    report.week_end = date(2024, 2, 4)
    report.summary = 'A simple summary.'
    report.content = None
    return report


class TestInitPdfFont:
    """测试 _init_pdf_font"""

    def test_font_init_result(self, export_service):
        from fpdf import FPDF

        pdf = FPDF()
        result = export_service._init_pdf_font(pdf)
        assert isinstance(result, bool)

    def test_a_cjk_font_is_available_in_this_environment(self):
        """环境必须真的能找到一个 CJK 字体。

        `_init_pdf_font()` 找不到字体时**不抛错**，只把文本降级成纯 ASCII（中文变 '?'），
        所以"缺字体"必须在这里响亮失败，而不是让下游的中文断言换一种写法悄悄通过。
        线上（Render）曾长期处于这个降级分支：PDF 里的中文全变成 '?'。

        Linux/CI 需要安装 CJK 字体（见 .github/workflows/ci.yml 的 `Install CJK font`
        步骤，包名 fonts-noto-cjk）；若发行版换了安装路径，请同步更新
        `_SYSTEM_FONT_CANDIDATES`，不要在本用例上放宽断言。
        """
        from fpdf import FPDF

        from app.services import export_service as export_service_module

        assert ExportService()._init_pdf_font(FPDF()) is True, (
            '当前环境找不到任何可用中文字体，PDF 导出会静默把中文降级成 ASCII。'
            f'已尝试的路径：{[str(p) for p in export_service_module._SYSTEM_FONT_CANDIDATES]}'
        )

    @patch('app.services.export_service._BUILTIN_FONT_CANDIDATES', [])
    @patch('app.services.export_service._SYSTEM_FONT_CANDIDATES', [])
    @patch('app.services.export_service.CHINESE_FONT')
    def test_font_not_exists(self, mock_font_path, export_service):
        """两个候选列表都必须清空：仓库自带的 assets/fonts/ 否则一定会命中。"""
        from fpdf import FPDF

        mock_font_path.exists.return_value = False
        pdf = FPDF()
        result = export_service._init_pdf_font(pdf)
        assert result is False

    @patch('app.services.export_service.CHINESE_FONT')
    def test_font_load_exception(self, mock_font_path, export_service):
        from fpdf import FPDF

        mock_font_path.exists.return_value = True
        mock_font_path.__str__ = lambda self: '/fake/path/simhei.ttf'
        pdf = FPDF()
        with patch.object(pdf, 'add_font', side_effect=Exception('font error')):
            result = export_service._init_pdf_font(pdf)
        assert result is False

    @patch('app.services.export_service._SYSTEM_FONT_CANDIDATES', [])
    def test_bundled_cjk_font_is_shipped_and_loadable(self):
        """回归锁：**只靠仓库自带的字体**（不依赖任何系统字体）也必须能出中文。

        存在理由——`_init_pdf_font()` 找不到字体时**不报错**，只把中文降级成 '?'，线上
        （Render 原生环境，装不了系统字体包、镜像里也没有任何 CJK 字体）就长期处于这个
        状态：导出的 PDF 只嵌 Helvetica、中文全是 '?'。所以字体必须随仓库走。

        这里把系统候选清空，正是为了复现 Render 的环境：本用例通过 = 位置在
        ``assets/fonts/wqy-microhei.ttc`` 的字体确实在位、能被 fpdf2 加载、且覆盖中文。
        删掉该文件、或换成 fpdf2 不支持的 CFF/OTF 轮廓字体，必须变红
        （换字体请同步更新同目录 README 与哈希）。
        """
        from fontTools.ttLib import TTFont
        from fpdf import FPDF

        from app.services import export_service as export_service_module

        font_path = export_service_module.BUILTIN_FONT_DIR / 'wqy-microhei.ttc'
        assert font_path.is_file(), f'内置中文字体缺失：{font_path}（见同目录 README）'

        # fpdf2 只吃 TrueType 轮廓；且字体必须真的覆盖中文，不能被换成拉丁字体。
        cmap = TTFont(str(font_path), fontNumber=0).getBestCmap()
        missing = [ch for ch in '本周指标数据待补全榜单作者类别排名变化' if ord(ch) not in cmap]
        assert not missing, f'内置字体缺少这些字形：{"".join(missing)}'

        assert ExportService()._init_pdf_font(FPDF()) is True


class TestExportWeeklyReportPdf:
    """测试 export_weekly_report_pdf（真实 FPDF 生成，保留原有实现级验证）"""

    def test_pdf_export_success(self, export_service, mock_report):
        result = export_service.export_weekly_report_pdf(mock_report)
        assert result is not None
        assert isinstance(result, BytesIO)
        content = result.read()
        assert len(content) > 0
        assert content.startswith(b'%PDF')

    def test_pdf_export_no_content(self, export_service, mock_report_no_content):
        result = export_service.export_weekly_report_pdf(mock_report_no_content)
        assert result is not None
        assert isinstance(result, BytesIO)

    @patch('app.services.export_service.FPDF', side_effect=Exception('PDF creation failed'))
    def test_pdf_export_exception(self, mock_fpdf, export_service, mock_report):
        result = export_service.export_weekly_report_pdf(mock_report)
        assert result is None

    def test_pdf_export_with_rank_changes(self, export_service, mock_report):
        result = export_service.export_weekly_report_pdf(mock_report)
        assert result is not None

    def test_pdf_export_content_without_top_changes(self, export_service):
        report = MagicMock()
        report.title = 'Report'
        report.report_date = date(2024, 1, 21)
        report.week_start = date(2024, 1, 15)
        report.week_end = date(2024, 1, 21)
        report.summary = 'Summary'
        report.content = json.dumps(
            {
                'featured_books': [
                    {'title': 'Book X', 'author': 'Author X', 'reason': 'Recommended'},
                ],
            }
        )
        result = export_service.export_weekly_report_pdf(report)
        assert result is not None

    def test_pdf_export_content_without_featured_books(self, export_service):
        report = MagicMock()
        report.title = 'Report'
        report.report_date = date(2024, 1, 21)
        report.week_start = date(2024, 1, 15)
        report.week_end = date(2024, 1, 21)
        report.summary = 'Summary'
        report.content = json.dumps(
            {
                'top_changes': [
                    {'title': 'Book A', 'author': 'Author A', 'category': 'Fiction', 'rank_change': 2},
                ],
            }
        )
        result = export_service.export_weekly_report_pdf(report)
        assert result is not None

    def _real_pdf_with_scope_and_metrics(self, export_service, report):
        """真实生成 PDF，并同时记录 cell / multi_cell 的文本调用。

        指标行 + scope 行会连续调用两次 multi_cell；若光标没有回到左边界，
        第二次调用会抛 FPDFException 并被服务吞成 None，这里必须拿到真实字节流。
        """
        texts = []
        original_cell = FPDF.cell
        original_multi_cell = FPDF.multi_cell

        def record_cell(self, *args, **kwargs):
            if len(args) >= 3 and isinstance(args[2], str):
                texts.append(args[2])
            return original_cell(self, *args, **kwargs)

        def record_multi_cell(self, *args, **kwargs):
            if len(args) >= 3 and isinstance(args[2], str):
                texts.append(args[2])
            return original_multi_cell(self, *args, **kwargs)

        with (
            patch.object(FPDF, 'cell', record_cell),
            patch.object(FPDF, 'multi_cell', record_multi_cell),
        ):
            result = export_service.export_weekly_report_pdf(report)

        assert result is not None, 'PDF 生成失败（多行文本光标未回到左边界？）'
        payload = result.read()
        assert payload.startswith(b'%PDF')
        return payload.decode('latin-1'), texts

    def test_pdf_direct_call_renders_derived_summary_and_metrics(self, export_service, mock_report):
        """直接调用（不传 prepared）：必须自动准备安全值，指标与 scope 行都要渲染出来。"""
        raw_narrative = mock_report.summary
        prepared = prepare_report_presentation(mock_report)
        raw_content = mock_report.content

        _, texts = self._real_pdf_with_scope_and_metrics(export_service, mock_report)

        joined = '\n'.join(texts)
        assert '本周指标' in joined
        assert '本周概览' in joined
        # 指标行取自已校验 content（总量未知 → 数据待补全），scope 行必须存在
        assert '数据待补全' in joined
        assert prepared['content']['scope_label'] in joined
        # 直接调用必须写入派生事实摘要，且不得出现原始未校验叙述
        assert prepared['summary'] in joined
        assert raw_narrative not in joined

        # 不修改 ORM 字段
        assert mock_report.summary == raw_narrative
        assert mock_report.content == raw_content

    def test_pdf_prepared_call_uses_prepared_summary(self, export_service, mock_report):
        """传入 prepared：使用同一套派生摘要，且依旧真实生成 PDF。"""
        prepared = prepare_report_presentation(mock_report)
        prepared = dict(prepared, summary='PREPARED SUMMARY SENTINEL')
        raw_content = mock_report.content

        texts = []
        original_multi_cell = FPDF.multi_cell

        def record_multi_cell(self, *args, **kwargs):
            if len(args) >= 3 and isinstance(args[2], str):
                texts.append(args[2])
            return original_multi_cell(self, *args, **kwargs)

        with patch.object(FPDF, 'multi_cell', record_multi_cell):
            result = export_service.export_weekly_report_pdf(mock_report, prepared=prepared)

        assert result is not None
        assert result.read().startswith(b'%PDF')
        joined = '\n'.join(texts)
        assert 'PREPARED SUMMARY SENTINEL' in joined
        assert prepared['content']['scope_label'] in joined
        assert mock_report.content == raw_content

    def test_pdf_unknown_totals_render_pending_label(self, export_service):
        """未知总量不臆造为 0：指标行显示“数据待补全”，PDF 仍生成成功。"""
        report = MagicMock()
        report.title = 'Unknown Totals Report'
        report.report_date = date(2024, 3, 3)
        report.week_start = date(2024, 2, 26)
        report.week_end = date(2024, 3, 3)
        report.summary = 'raw narrative with X placeholder'
        report.content = json.dumps({'total_books': 'not-a-number', 'featured_books': []})

        prepared = prepare_report_presentation(report)
        _, texts = self._real_pdf_with_scope_and_metrics(export_service, report)
        joined = '\n'.join(texts)

        assert '数据待补全' in joined
        assert prepared['summary'] in joined
        assert report.summary not in joined

    def test_pdf_direct_call_does_not_mutate_orm_fields(self, export_service, mock_report_no_content):
        raw_summary = mock_report_no_content.summary
        result = export_service.export_weekly_report_pdf(mock_report_no_content)
        assert result is not None
        assert mock_report_no_content.summary == raw_summary
        assert mock_report_no_content.content is None

    @patch('app.services.export_service._BUILTIN_FONT_CANDIDATES', [])
    @patch('app.services.export_service._SYSTEM_FONT_CANDIDATES', [])
    @patch('app.services.export_service.CHINESE_FONT')
    def test_pdf_without_any_cjk_font_degrades_to_ascii_instead_of_failing(
        self, mock_chinese_font, export_service, mock_report
    ):
        """环境里没有任何中文字体时的**降级合同**——与本机装没装字体无关的确定性锁。

        导出仍必须产出合法 PDF（不抛异常、不返回 None），中文按既有设计降级为 '?'。
        这是"宁可缺字也不能让导出失败"的取舍；反向的"有字体就必须渲染中文"由
        test_pdf_direct_call_renders_derived_summary_and_metrics 与
        TestInitPdfFont::test_a_cjk_font_is_available_in_this_environment 锁住。
        """
        mock_chinese_font.exists.return_value = False

        _, texts = self._real_pdf_with_scope_and_metrics(export_service, mock_report)
        joined = '\n'.join(texts)

        assert '本周指标' not in joined, '缺字体时不应出现中文（会渲染成豆腐块或问号）'
        assert '?' in joined, '缺字体时中文应降级为 ? 而不是被整段丢弃'


class TestExportWeeklyReportExcel:
    """测试 export_weekly_report_excel（真实 openpyxl 工作簿断言）"""

    def _load(self, export_service, report, prepared=None):
        result = export_service.export_weekly_report_excel(report, prepared=prepared)
        assert result is not None, 'Excel 导出返回 None（row/header_font 未定义？）'
        assert isinstance(result, BytesIO)
        return load_workbook(result)

    @staticmethod
    def _column(ws, letter, limit=40):
        return [ws[f'{letter}{r}'].value for r in range(1, limit + 1)]

    def test_excel_export_success(self, export_service, mock_report):
        result = export_service.export_weekly_report_excel(mock_report)
        assert result is not None
        assert isinstance(result, BytesIO)
        content = result.read()
        assert len(content) > 0

    def test_excel_export_exception(self, export_service, mock_report):
        with patch('app.services.export_service.Workbook', side_effect=Exception('Excel failed')):
            result = export_service.export_weekly_report_excel(mock_report)
        assert result is None

    def test_excel_export_with_positive_rank_change(self, export_service, mock_report):
        result = export_service.export_weekly_report_excel(mock_report)
        assert result is not None

    def test_excel_direct_call_keeps_summary_and_both_tables(self, export_service, mock_report):
        """直接调用：摘要保留在 A9:D9，两张表从第 10 行起且数据完整。"""
        prepared = prepare_report_presentation(mock_report)
        raw_summary = mock_report.summary
        raw_content = mock_report.content

        ws = self._load(export_service, mock_report).active

        # 标题 / 指标 / 概览标题保持在预留行
        assert ws['A1'].value == mock_report.title
        assert ws['A6'].value == '本周指标'
        assert ws['A8'].value == '本周概览'
        assert '数据待补全' in ws['A7'].value
        assert prepared['content']['scope_label'] in ws['A7'].value

        # 事实摘要未被表格覆盖
        assert ws['A9'].value == prepared['summary']
        assert ws['A9'].value != raw_summary

        # 重要变化表
        assert ws['A10'].value == '重要变化'
        assert [ws[f'{c}11'].value for c in 'ABCD'] == ['书名', '作者', '类别', '排名变化']
        assert [ws[f'A{r}'].value for r in (12, 13, 14)] == ['Book A', 'Book B', 'Book C']
        assert ws['D12'].value == '↑ 5'
        assert ws['D13'].value == '↓ 3'
        assert ws['D14'].value == '→ 无变化'

        # 推荐书籍表（第 15 行留空行，表头 16，数据 17）
        assert ws['A16'].value == '推荐书籍'
        assert [ws[f'{c}17'].value for c in 'ABC'] == ['书名', '作者', '推荐理由']
        assert ws['A18'].value == 'Featured Book'
        assert ws['B18'].value == 'Featured Author'
        assert ws['C18'].value == 'Great reviews'

        # 页脚在表格之后，不与摘要冲突
        footer_rows = [
            r for r in range(1, 41) if isinstance(ws[f'A{r}'].value, str) and 'BookRank' in ws[f'A{r}'].value
        ]
        assert footer_rows and footer_rows[0] > 18

        # ORM 字段未被改写
        assert mock_report.summary == raw_summary
        assert mock_report.content == raw_content

    def test_excel_prepared_call_preserves_prepared_summary(self, export_service, mock_report):
        prepared = prepare_report_presentation(mock_report)
        ws = self._load(export_service, mock_report, prepared=prepared).active
        assert ws['A9'].value == prepared['summary']
        assert ws['A10'].value == '重要变化'
        assert ws['A18'].value == 'Featured Book'

    def test_excel_featured_only_starts_below_summary(
        self,
        export_service,
    ):
        """仅推荐书籍：表格从第 10 行起，不覆盖 A9 摘要，且不再返回 None。"""
        report = MagicMock()
        report.title = 'Report'
        report.report_date = date(2024, 1, 21)
        report.week_start = date(2024, 1, 15)
        report.week_end = date(2024, 1, 21)
        report.summary = 'Summary'
        report.content = json.dumps(
            {'featured_books': [{'title': 'Book X', 'author': 'Author X', 'reason': 'Recommended'}]}
        )

        prepared = prepare_report_presentation(report)
        ws = self._load(export_service, report).active

        assert ws['A9'].value == prepared['summary']
        assert ws['A10'].value == '推荐书籍'
        assert [ws[f'{c}11'].value for c in 'ABC'] == ['书名', '作者', '推荐理由']
        assert ws['A12'].value == 'Book X'
        assert ws['C12'].value == 'Recommended'

    def test_excel_missing_content_still_valid_and_keeps_summary(self, export_service, mock_report_no_content):
        """无 content：仍产出有效工作簿，摘要/指标保留（旧行为返回 None 属缺陷）。"""
        prepared = prepare_report_presentation(mock_report_no_content)
        ws = self._load(export_service, mock_report_no_content).active

        assert ws['A1'].value == 'Simple Report'
        assert ws['A6'].value == '本周指标'
        assert ws['A8'].value == '本周概览'
        assert ws['A9'].value == prepared['summary']
        assert ws['A9'].value != mock_report_no_content.summary

        footer_rows = [
            r for r in range(1, 41) if isinstance(ws[f'A{r}'].value, str) and 'BookRank' in ws[f'A{r}'].value
        ]
        assert footer_rows and footer_rows[0] > 9

    def test_excel_unknown_totals_show_pending_not_zero(self, export_service):
        report = MagicMock()
        report.title = 'Unknown Totals Report'
        report.report_date = date(2024, 3, 3)
        report.week_start = date(2024, 2, 26)
        report.week_end = date(2024, 3, 3)
        report.summary = 'raw narrative with X placeholder'
        report.content = json.dumps({'total_books': None, 'total_new': 4})

        prepared = prepare_report_presentation(report)
        ws = self._load(export_service, report).active

        assert ws['A7'].value.startswith('上榜记录: 数据待补全')
        assert '新书: 4' in ws['A7'].value
        assert ws['A9'].value == prepared['summary']
        assert report.summary not in str(ws['A9'].value)

        # 未知项一律待补全，绝不臆造为 0：total_books/rising/falling 未知、total_new=4 已知。
        for key in ('total_books', 'total_rising', 'total_falling'):
            assert prepared['content'][f'{key}_known'] is False
            assert prepared['content'][f'{key}_display'] == '数据待补全'
        assert prepared['content']['total_new_known'] is True
        summary = str(ws['A9'].value)
        # 未知项数 = 摘要中“待补全”出现次数（上榜记录 1 + 排名变动 1）。
        unknown_keys = [
            k
            for k in ('total_books', 'total_new', 'total_rising', 'total_falling')
            if not prepared['content'][f'{k}_known']
        ]
        assert summary.count('待补全') == 2  # 标题句 + 排名变动句（上升与下降合为一处）
        assert len(unknown_keys) == 3
        # 已知的新上榜计数按权威值呈现。
        assert '新书: 4' in str(ws['A7'].value)
        assert '4' in summary
        # 未知的计数绝不出现在摘要里被当作 0。
        for phrase in ('0 条上升', '0 条下降', '0 条上榜记录'):
            assert phrase not in summary

    def test_excel_orm_fields_unchanged_after_export(self, export_service, mock_report):
        raw_summary = mock_report.summary
        raw_content = mock_report.content
        self._load(export_service, mock_report)
        assert mock_report.summary == raw_summary
        assert mock_report.content == raw_content

    @staticmethod
    def _merged_width(ws):
        """A7:D7 / A9:D9 合并区的可用宽度（字符口径），与服务端估算口径一致。"""
        return sum(ws.column_dimensions[c].width for c in 'ABCD') + 2.0

    @staticmethod
    def _visual_width(text):
        return sum(2 if ord(ch) > 0x2E7F else 1 for ch in text)

    def test_excel_summary_row_height_fits_wrapped_factual_text(self, export_service, mock_report):
        """合并单元格的自动换行不会自动撑高行高：A9 事实摘要行必须给出足够行高。

        回归：默认单行高度会把换行后的新文案在视觉上裁掉。
        """
        prepared = prepare_report_presentation(mock_report)
        ws = self._load(export_service, mock_report).active

        summary = ws['A9'].value
        assert summary == prepared['summary']
        assert ws['A9'].alignment.wrap_text is True

        height = ws.row_dimensions[9].height
        assert height is not None, '摘要行未设置行高（换行文本会被裁掉）'
        # A9:D9 跨四列合并，可用宽度远大于单列：摘要按合计宽度折行后仍超一行。
        merged_width = self._merged_width(ws)
        assert summary and self._visual_width(summary) > merged_width
        assert height > 15.0

        # 估算行数应覆盖实际折行需求，而不是固定值。
        assert height >= -(-self._visual_width(summary) // int(merged_width)) * 15.0

    def test_excel_summary_row_height_not_inflated_by_single_column_width(self, export_service, mock_report):
        """摘要行高必须按四列合计宽度估算，不能按 A 列宽度虚高（会撑坏导出排版）。"""
        ws = self._load(export_service, mock_report).active
        summary = ws['A9'].value

        merged_width = self._merged_width(ws)
        height = ws.row_dimensions[9].height

        assert height is not None
        assert height > 15.0, '摘要长于合并区一行宽度，行高必须超过单行'
        # 按 A 列宽度估算会得到大得多的行高：两者必须不同，且实际值更小。
        column_a_lines = -(-self._visual_width(summary) // int(ws.column_dimensions['A'].width))
        assert column_a_lines > 1
        assert height < column_a_lines * 15.0

    def test_excel_metrics_row_height_uses_merged_width(self, export_service, mock_report):
        """A7 指标行同样是 A7:D7 合并 + 自动换行，必须一并设置行高。"""
        prepared = prepare_report_presentation(mock_report)
        ws = self._load(export_service, mock_report).active

        metrics = ws['A7'].value
        assert metrics.startswith('上榜记录:')
        assert prepared['content']['scope_label'] in metrics
        assert ws['A7'].alignment.wrap_text is True

        merged_width = self._merged_width(ws)
        height = ws.row_dimensions[7].height
        assert height is not None, '指标行未设置行高（scope 说明行会被裁掉）'
        # 指标行含换行的 scope 说明：行数按每段单独估算后相加。
        expected_lines = sum(max(1, -(-self._visual_width(line) // int(merged_width))) for line in metrics.split('\n'))
        assert expected_lines > 1
        assert height == expected_lines * 15.0
        # 不是被 A 列宽度撑出来的虚高行高。
        assert height < self._visual_width(metrics) // int(ws.column_dimensions['A'].width) * 15.0
