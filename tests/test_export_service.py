"""导出服务测试"""

import json
from datetime import date
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from app.services.export_service import ExportService


@pytest.fixture
def export_service():
    return ExportService()


@pytest.fixture
def mock_report():
    """模拟周报对象"""
    report = MagicMock()
    report.title = '2024年第3周畅销书排行榜周报'
    report.report_date = date(2024, 1, 21)
    report.week_start = date(2024, 1, 15)
    report.week_end = date(2024, 1, 21)
    report.summary = '本周共有15本新书上榜，3本图书排名大幅上升。'
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

    @patch('app.services.export_service._SYSTEM_FONT_CANDIDATES', [])
    @patch('app.services.export_service.CHINESE_FONT')
    def test_font_not_exists(self, mock_font_path, export_service):
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


class TestExportWeeklyReportPdf:
    """测试 export_weekly_report_pdf"""

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


class TestExportWeeklyReportExcel:
    """测试 export_weekly_report_excel"""

    def test_excel_export_success(self, export_service, mock_report):
        result = export_service.export_weekly_report_excel(mock_report)
        assert result is not None
        assert isinstance(result, BytesIO)
        content = result.read()
        assert len(content) > 0

    def test_excel_export_no_content_returns_none(self, export_service, mock_report_no_content):
        result = export_service.export_weekly_report_excel(mock_report_no_content)
        assert result is None

    @patch('app.services.export_service.Workbook', side_effect=Exception('Excel failed'))
    def test_excel_export_exception(self, mock_wb, export_service, mock_report):
        result = export_service.export_weekly_report_excel(mock_report)
        assert result is None

    def test_excel_export_with_positive_rank_change(self, export_service, mock_report):
        result = export_service.export_weekly_report_excel(mock_report)
        assert result is not None

    def test_excel_export_content_without_changes(self, export_service):
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
        result = export_service.export_weekly_report_excel(report)
        assert result is None
