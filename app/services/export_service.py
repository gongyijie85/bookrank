"""导出服务"""

import json
import logging
from io import BytesIO
from pathlib import Path

from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from ..utils.date_helpers import format_chinese_date
from ..utils.error_handler import ErrorCategory, log_error
from ..utils.weekly_report_presentation import prepare_report_presentation

logger = logging.getLogger(__name__)

# 中文字体路径（项目内置SimHei黑体，回退系统字体）
FONT_DIR = Path(__file__).parent.parent.parent / 'static' / 'fonts'
CHINESE_FONT = FONT_DIR / 'simhei.ttf'
_SYSTEM_FONT_CANDIDATES = [
    Path('C:/Windows/Fonts/simhei.ttf'),
    Path('C:/Windows/Fonts/msyh.ttc'),
    Path('/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'),
    Path('/System/Library/Fonts/PingFang.ttc'),
]

# Excel 行高换算：11pt 字号下单行约 15 磅，CJK 字符按 2 个字符宽度计。
_EXCEL_LINE_HEIGHT_POINTS = 15.0

# A7:D7 / A9:D9 合并区域宽度的安全余量（字符宽度口径）：Excel 列宽换算与会话默认
# 字体存在小数级误差，取整后可能多算一行、把行高撑得过高，留一点余量更贴近实际折行。
_MERGED_WIDTH_ALLOWANCE = 2.0


def excel_wrapped_row_height(
    text: object,
    column_width: float | None = None,
    min_lines: int = 1,
    max_lines: int = 40,
) -> float | None:
    """估算 Excel 单元格自动换行后所需的行高（磅）。

    合并单元格里的自动换行不会自动撑高行高，默认单行高度会把换行后的文本在视觉上
    裁掉。这里按列宽估算折行行数，给出足够行高。文本为空或列宽非法时返回 ``None``，
    表示不设置行高（保持 Excel 默认行为）。跨列合并时传入合并区域各列列宽**之和**
    （见 :meth:`ExportService.export_weekly_report_excel` 里的 ``merged_width``）。
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        width = float(column_width) if column_width else 0.0
    except (TypeError, ValueError):
        return None
    if width <= 0:
        return None

    lines = 0
    for logical_line in text.split('\n'):
        visual_width = sum(2 if ord(ch) > 0x2E7F else 1 for ch in logical_line)
        lines += max(1, -(-visual_width // int(width)))  # ceil
    lines = max(min_lines, min(lines, max_lines))
    return round(lines * _EXCEL_LINE_HEIGHT_POINTS, 2)


class ExportService:
    """导出服务类"""

    def _init_pdf_font(self, pdf: FPDF) -> bool:
        """初始化PDF中文字体（项目字体 -> 系统字体 -> 回退ASCII）"""
        # 1. 尝试项目内置字体
        if CHINESE_FONT.exists():
            try:
                pdf.add_font('SimHei', '', str(CHINESE_FONT))
                pdf.add_font('SimHei', 'B', str(CHINESE_FONT))
                return True
            except Exception as e:
                log_error(ErrorCategory.UNKNOWN, f'加载项目中文字体失败: {e}', level='warning')
        # 2. 尝试系统字体
        for font_path in _SYSTEM_FONT_CANDIDATES:
            if font_path.exists():
                try:
                    pdf.add_font('SimHei', '', str(font_path))
                    pdf.add_font('SimHei', 'B', str(font_path))
                    logger.info(f'使用系统中文字体: {font_path}')
                    return True
                except Exception:
                    continue
        logger.warning('未找到可用的中文字体，PDF将仅支持ASCII字符')
        return False

    @staticmethod
    def _safe_pdf_text(text: str) -> str:
        """Convert text to pure ASCII when Chinese font is missing."""
        try:
            return text.encode('ascii', 'replace').decode('ascii')
        except Exception:
            return text.encode('ascii', 'ignore').decode('ascii')

    def _safe_pdf(self, pdf, font_name, has_chinese_font):
        """Wrap pdf.cell and pdf.multi_cell to auto-sanitize text."""
        if has_chinese_font:
            return pdf
        _orig_cell = pdf.cell
        _orig_multi_cell = pdf.multi_cell
        _safe = self._safe_pdf_text

        def _patched_cell(*args, **kwargs):
            a = list(args)
            if len(a) >= 3 and isinstance(a[2], str):
                a[2] = _safe(a[2])
            return _orig_cell(*a, **kwargs)

        def _patched_multi_cell(*args, **kwargs):
            a = list(args)
            if len(a) >= 3 and isinstance(a[2], str):
                a[2] = _safe(a[2])
            return _orig_multi_cell(*a, **kwargs)

        pdf.cell = _patched_cell
        pdf.multi_cell = _patched_multi_cell
        return pdf

    def export_weekly_report_pdf(self, report, prepared: dict | None = None) -> BytesIO | None:
        """导出周报为PDF

        Args:
            report: 周报对象
            prepared: 可选，presentation 准备数据（安全摘要 / 校验总量）。
                缺省时自动用 prepare_report_presentation(report) 生成，绝不使用
                未校验的 report.summary，也不改写 ORM 字段。

        Returns:
            BytesIO: PDF文件流
        """
        try:
            if prepared is None:
                prepared = prepare_report_presentation(report)

            # 创建PDF对象
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)

            # 添加中文字体支持
            has_chinese_font = self._init_pdf_font(pdf)
            font_name = 'SimHei' if has_chinese_font else 'Arial'
            pdf = self._safe_pdf(pdf, font_name, has_chinese_font)

            pdf.add_page()

            # 标题
            pdf.set_font(font_name, '', 16)
            pdf.cell(0, 10, report.title, new_x='LMARGIN', new_y='NEXT', align='C')

            # 元数据
            pdf.set_font(font_name, '', 10)
            pdf.cell(
                0,
                8,
                f'发布日期: {format_chinese_date(report.report_date)}',
                new_x='LMARGIN',
                new_y='NEXT',
                align='C',
            )
            pdf.cell(
                0,
                8,
                f'统计周期: {report.week_start.strftime("%Y-%m-%d")} 至 {report.week_end.strftime("%Y-%m-%d")}',
                new_x='LMARGIN',
                new_y='NEXT',
                align='C',
            )
            pdf.ln(10)

            # 本周指标（audit04：权威总量来自结构化 content，缺失标“数据待补全”）
            # 展示值直接取 prepared 里已本地化的 total_*_display，绝不臆造为 0。
            prepared_content = (prepared or {}).get('content') or {}
            metric_lines = [
                (
                    f'上榜记录: {prepared_content.get("total_books_display", "")}'
                    f' · 新书: {prepared_content.get("total_new_display", "")}'
                    f' · 上升: {prepared_content.get("total_rising_display", "")}'
                    f' · 下降: {prepared_content.get("total_falling_display", "")}'
                )
            ]
            scope_label = prepared_content.get('scope_label')
            if scope_label:
                metric_lines.append(scope_label)
            pdf.set_font(font_name, 'B', 12)
            pdf.cell(0, 10, '本周指标', new_x='LMARGIN', new_y='NEXT', align='L')
            pdf.set_font(font_name, '', 10)
            # multi_cell 默认 new_x=RIGHT 会把光标留在右边距，导致下一行没有可渲染宽度
            # （scope 行直接报 FPDFException）。显式回到左边界并换行。
            for line in metric_lines:
                pdf.multi_cell(0, 5, line, new_x='LMARGIN', new_y='NEXT')
            pdf.ln(6)

            # 摘要（audit04：一律使用确定性事实摘要，不展示/导出未校验的存储叙述）
            summary = prepared.get('summary')
            pdf.set_font(font_name, 'B', 12)
            pdf.cell(0, 10, '本周概览', new_x='LMARGIN', new_y='NEXT', align='L')
            pdf.set_font(font_name, '', 10)
            pdf.multi_cell(0, 5, summary, new_x='LMARGIN', new_y='NEXT')
            pdf.ln(10)

            # 详细内容
            if report.content:
                content = json.loads(report.content)

                # 重要变化
                if content.get('top_changes'):
                    pdf.set_font(font_name, 'B', 12)
                    pdf.cell(0, 10, '重要变化', new_x='LMARGIN', new_y='NEXT', align='L')
                    pdf.set_font(font_name, '', 10)
                    for change in content['top_changes']:
                        pdf.cell(
                            0, 6, f'• {change["title"]} - {change["author"]}', new_x='LMARGIN', new_y='NEXT', align='L'
                        )
                        pdf.cell(0, 6, f'  类别: {change["category"]}', new_x='LMARGIN', new_y='NEXT', align='L')
                        if change['rank_change'] > 0:
                            pdf.cell(
                                0,
                                6,
                                f'  排名变化: ↑ {change["rank_change"]} 位',
                                new_x='LMARGIN',
                                new_y='NEXT',
                                align='L',
                            )
                        elif change['rank_change'] < 0:
                            pdf.cell(
                                0,
                                6,
                                f'  排名变化: ↓ {abs(change["rank_change"])} 位',
                                new_x='LMARGIN',
                                new_y='NEXT',
                                align='L',
                            )
                        else:
                            pdf.cell(0, 6, '  排名变化: → 无变化', new_x='LMARGIN', new_y='NEXT', align='L')
                        pdf.ln(2)
                    pdf.ln(5)

                # 推荐书籍
                if content.get('featured_books'):
                    pdf.set_font(font_name, 'B', 12)
                    pdf.cell(0, 10, '推荐书籍', new_x='LMARGIN', new_y='NEXT', align='L')
                    pdf.set_font(font_name, '', 10)
                    for book in content['featured_books']:
                        pdf.cell(
                            0, 6, f'• {book["title"]} - {book["author"]}', new_x='LMARGIN', new_y='NEXT', align='L'
                        )
                        pdf.cell(0, 6, f'  推荐理由: {book["reason"]}', new_x='LMARGIN', new_y='NEXT', align='L')
                        pdf.ln(2)
                    pdf.ln(5)

            # 页脚
            pdf.set_font(font_name, '', 8)
            pdf.cell(
                0,
                10,
                f'© {report.report_date.year} BookRank - 纽约时报畅销书排行榜',
                new_x='LMARGIN',
                new_y='NEXT',
                align='C',
            )

            # 输出到内存流
            buffer = BytesIO()
            pdf.output(buffer)
            buffer.seek(0)

            logger.info(f'PDF导出成功: {report.title}')
            return buffer

        except Exception as e:
            log_error(ErrorCategory.UNKNOWN, f'PDF导出失败: {e!s}')
            return None

    def export_weekly_report_excel(self, report, prepared: dict | None = None) -> BytesIO | None:
        """导出周报为Excel

        Args:
            report: 周报对象
            prepared: 可选，presentation 准备数据（安全摘要 / 校验总量）。
                缺省时自动用 prepare_report_presentation(report) 生成，绝不使用
                未校验的 report.summary，也不改写 ORM 字段。

        Returns:
            BytesIO: Excel文件流
        """
        try:
            if prepared is None:
                prepared = prepare_report_presentation(report)

            # 创建工作簿
            wb = Workbook()
            ws = wb.active
            ws.title = '周报'

            # 设置列宽
            ws.column_dimensions['A'].width = 50
            ws.column_dimensions['B'].width = 30
            ws.column_dimensions['C'].width = 20
            ws.column_dimensions['D'].width = 15
            # A7:D7 / A9:D9 都是跨四列的合并单元格，自动换行按「四列合计宽度」折行。
            # 只按 A 列宽度估行会严重高估行数、把行撑得过高（导出排版被撑坏）。
            merged_width = sum(ws.column_dimensions[c].width for c in 'ABCD') + _MERGED_WIDTH_ALLOWANCE

            # 标题
            title_font = Font(bold=True, size=14)
            ws.merge_cells('A1:D1')
            ws['A1'] = report.title
            ws['A1'].font = title_font
            ws['A1'].alignment = Alignment(horizontal='center', vertical='center')

            # 元数据
            meta_font = Font(size=10)
            ws['A3'] = f'发布日期: {format_chinese_date(report.report_date)}'
            ws['A4'] = f'统计周期: {report.week_start.strftime("%Y-%m-%d")} 至 {report.week_end.strftime("%Y-%m-%d")}'
            ws['A3'].font = meta_font
            ws['A4'].font = meta_font

            # 本周指标（audit04：权威总量来自结构化 content，缺失标“数据待补全”）
            # 展示值直接取 prepared 里已本地化的 total_*_display，绝不臆造为 0。
            prepared_content = (prepared or {}).get('content') or {}
            scope_label = prepared_content.get('scope_label')
            summary_font = Font(bold=True, size=12)
            ws['A6'] = '本周指标'
            ws['A6'].font = summary_font
            ws.merge_cells('A6:D6')
            metrics_text = (
                f'上榜记录: {prepared_content.get("total_books_display", "")}'
                f' · 新书: {prepared_content.get("total_new_display", "")}'
                f' · 上升: {prepared_content.get("total_rising_display", "")}'
                f' · 下降: {prepared_content.get("total_falling_display", "")}'
            )
            if scope_label:
                metrics_text += f'\n{scope_label}'
            ws['A7'] = metrics_text
            ws['A7'].font = meta_font
            ws['A7'].alignment = Alignment(wrap_text=True, vertical='top')
            ws.merge_cells('A7:D7')
            # A7:D7 同样跨四列合并：scope_label 单独占一行，窄列宽会把结论行裁掉。
            metrics_row_height = excel_wrapped_row_height(metrics_text, column_width=merged_width)
            if metrics_row_height is not None:
                ws.row_dimensions[7].height = metrics_row_height

            # 摘要（audit04：一律使用确定性事实摘要，不展示/导出未校验的存储叙述）
            # A9:D9 跨四列合并，行高必须按四列合计宽度估算；只按 A 列宽度会高估行数、
            # 把行撑得过高，破坏导出排版。
            summary = prepared.get('summary')
            ws['A8'] = '本周概览'
            ws['A8'].font = summary_font
            ws.merge_cells('A8:D8')
            ws['A9'] = summary
            ws['A9'].alignment = Alignment(wrap_text=True, vertical='top')
            ws.merge_cells('A9:D9')
            summary_row_height = excel_wrapped_row_height(summary, column_width=merged_width)
            if summary_row_height is not None:
                ws.row_dimensions[9].height = summary_row_height

            # 详细内容：从预留的摘要/指标行之后开始。
            # 标题占 A1、指标标题 A6 + 指标 A7、概览标题 A8 + 概览正文 A9，
            # 因此表格必须从第 10 行起，否则会把 A9:D9 的事实摘要覆盖掉。
            # row / header_font 定义在可选分支之外：content 缺失或只有推荐书籍时同样可用。
            row = 10
            header_font = Font(bold=True)
            if report.content:
                content = json.loads(report.content)

                # 重要变化
                if content.get('top_changes'):
                    ws[f'A{row}'] = '重要变化'
                    ws[f'A{row}'].font = summary_font
                    row += 1

                    # 表头
                    ws[f'A{row}'] = '书名'
                    ws[f'B{row}'] = '作者'
                    ws[f'C{row}'] = '类别'
                    ws[f'D{row}'] = '排名变化'
                    for col in ['A', 'B', 'C', 'D']:
                        ws[f'{col}{row}'].font = header_font
                        ws[f'{col}{row}'].alignment = Alignment(horizontal='center')
                    row += 1

                    # 数据
                    for change in content['top_changes']:
                        ws[f'A{row}'] = change['title']
                        ws[f'B{row}'] = change['author']
                        ws[f'C{row}'] = change['category']
                        if change['rank_change'] > 0:
                            ws[f'D{row}'] = f'↑ {change["rank_change"]}'
                        elif change['rank_change'] < 0:
                            ws[f'D{row}'] = f'↓ {abs(change["rank_change"])}'
                        else:
                            ws[f'D{row}'] = '→ 无变化'
                        row += 1
                    row += 1

                # 推荐书籍
                if content.get('featured_books'):
                    ws[f'A{row}'] = '推荐书籍'
                    ws[f'A{row}'].font = summary_font
                    row += 1

                    # 表头
                    ws[f'A{row}'] = '书名'
                    ws[f'B{row}'] = '作者'
                    ws[f'C{row}'] = '推荐理由'
                    for col in ['A', 'B', 'C']:
                        ws[f'{col}{row}'].font = header_font
                        ws[f'{col}{row}'].alignment = Alignment(horizontal='center')
                    row += 1

                    # 数据
                    for book in content['featured_books']:
                        ws[f'A{row}'] = book['title']
                        ws[f'B{row}'] = book['author']
                        ws[f'C{row}'] = book['reason']
                        ws[f'C{row}'].alignment = Alignment(wrap_text=True, vertical='top')
                        row += 1

            # 页脚（无表格内容时承接预留行，不会与摘要/指标重叠）
            footer_row = max(row + 2, 11)
            footer_font = Font(size=8)
            ws[f'A{footer_row}'] = f'© {report.report_date.year} BookRank - 纽约时报畅销书排行榜'
            ws[f'A{footer_row}'].font = footer_font
            ws.merge_cells(f'A{footer_row}:D{footer_row}')
            ws[f'A{footer_row}'].alignment = Alignment(horizontal='center')

            # 输出到内存流
            buffer = BytesIO()
            wb.save(buffer)
            buffer.seek(0)

            logger.info(f'Excel导出成功: {report.title}')
            return buffer

        except Exception as e:
            log_error(ErrorCategory.UNKNOWN, f'Excel导出失败: {e!s}')
            return None
