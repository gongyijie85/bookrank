"""周报服务"""

import json
import logging
import re
from datetime import date
from typing import Any

from ..models.schemas import WeeklyReport, db
from .book_service import BookService

logger = logging.getLogger(__name__)


def _format_book_title(title: str) -> str:
    """格式化书名，去除重复书名号并清理翻译污染"""
    if not title:
        return ''
    text = title.strip()
    # 去除markdown标记
    text = re.sub(r'\*{1,2}|_{1,2}|`', '', text)
    # 如果文本中有换行，只取第一行（书名）
    if '\n' in text:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            text = lines[0]
    # 如果文本中已有《》，提取《》内的内容
    book_match = re.search(r'《([^》]+)》', text)
    if book_match:
        text = book_match.group(1).strip()
    # 去除剩余的书名号，统一添加
    text = text.strip('《》').strip()
    return f'《{text}》' if text else ''


def _clean_double_brackets(text: str) -> str:
    """清理文本中所有重复的书名号（《《xxx》》 → 《xxx》）"""
    if not text:
        return text
    text = re.sub(r'《{2,}', '《', text)
    text = re.sub(r'》{2,}', '》', text)
    return text


def _cover_html(cover: str) -> str:
    """生成封面图HTML标签（统一60px宽度，邮件/摘要通用）"""
    if not cover:
        return ''
    return (
        f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;'
        f'max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.1);">'
    )


class WeeklyReportService:
    """周报服务"""

    def __init__(self, book_service: BookService):
        """初始化

        Args:
            book_service: 图书服务实例
        """
        self._book_service = book_service
        self._translation_service = None

    def _get_translation_service(self):
        """获取翻译服务"""
        if not self._translation_service:
            try:
                from .zhipu_translation_service import get_translation_service

                self._translation_service = get_translation_service()
            except Exception as e:
                logger.warning(f'无法初始化翻译服务: {e}')
        return self._translation_service

    def generate_report(self, week_start: date, week_end: date, force_regenerate: bool = False) -> WeeklyReport | None:
        """生成周报

        Args:
            week_start: 周开始日期
            week_end: 周结束日期
            force_regenerate: 是否强制重新生成（即使已存在）

        Returns:
            WeeklyReport: 生成的周报
        """
        try:
            # 检查是否已经生成过该周的报告
            existing_report = WeeklyReport.query.filter(
                WeeklyReport.week_start == week_start, WeeklyReport.week_end == week_end
            ).first()

            if existing_report and not force_regenerate:
                logger.info(f'周报已存在: {week_start} 至 {week_end}')
                return existing_report

            # 如果是强制重新生成且旧报告存在，先删除
            if existing_report and force_regenerate:
                logger.info(f'强制重新生成周报: {week_start} 至 {week_end}')
                db.session.delete(existing_report)
                db.session.commit()

            # 收集本周数据
            weekly_data = self._collect_weekly_data(week_start, week_end)

            has_books = bool(weekly_data.get('books'))
            if not has_books:
                logger.warning(f'数据不足，生成暂无数据周报: {week_start} 至 {week_end}')

            # 分析变化
            analysis = self._analyze_changes(weekly_data)

            # 生成报告标题
            title = f'{week_start.strftime("%Y年%m月%d日")}-{week_end.strftime("%Y年%m月%d日")} 畅销书周报'

            # 生成AI摘要
            if has_books:
                summary = self._generate_ai_summary(analysis, week_start, week_end)
            else:
                summary = '本周暂无可用榜单数据。请检查 NYT API 配置或等待缓存刷新后重新生成。'
            summary = _clean_double_brackets(summary)

            # 构建报告内容
            content = {
                'top_changes': analysis.get('top_changes', []),
                'new_books': analysis.get('new_books', []),
                'top_risers': analysis.get('top_risers', []),
                'longest_running': analysis.get('longest_running', []),
                'featured_books': analysis.get('featured_books', []),
                'category_stats': analysis.get('category_stats', {}),
                'total_books': analysis.get('total_books', 0),
                'total_new': analysis.get('total_new', 0),
                'total_rising': analysis.get('total_rising', 0),
                'total_falling': analysis.get('total_falling', 0),
            }

            # 清理内容数据中的重复书名号
            for key in ['top_changes', 'new_books', 'top_risers', 'longest_running', 'featured_books']:
                for book in content.get(key, []):
                    if 'title' in book:
                        book['title'] = _format_book_title(book['title'])

            # 创建周报记录
            report = WeeklyReport(
                report_date=date.today(),
                week_start=week_start,
                week_end=week_end,
                title=title,
                summary=summary,
                content=json.dumps(content, ensure_ascii=False),
                top_changes=json.dumps(analysis.get('top_changes', []), ensure_ascii=False),
                featured_books=json.dumps(analysis.get('featured_books', []), ensure_ascii=False),
            )

            # 保存到数据库
            db.session.add(report)
            db.session.commit()

            return report

        except Exception as e:
            logger.error(f'生成周报时出错: {e!s}')
            db.session.rollback()
            # 出错时再次检查是否已存在报告
            existing_report = WeeklyReport.query.filter(
                WeeklyReport.week_start == week_start, WeeklyReport.week_end == week_end
            ).first()
            if existing_report:
                return existing_report
            return None

    def _collect_weekly_data(self, week_start: date, week_end: date) -> dict[str, Any]:
        """收集本周数据

        Args:
            week_start: 周开始日期
            week_end: 周结束日期

        Returns:
            Dict: 本周数据
        """
        try:
            # 从纽约时报API获取数据

            # 定义纽约时报书籍分类
            nyt_categories = {
                'hardcover-fiction': '精装小说',
                'paperback-fiction': '平装小说',
                'hardcover-nonfiction': '精装非虚构',
                'paperback-nonfiction': '平装非虚构',
                'advice-how-to-and-miscellaneous': '建议、方法与杂项',
                'graphic-books-and-manga': '漫画与绘本',
                'childrens-middle-grade-hardcover': '儿童中级精装本',
                'young-adult-hardcover': '青少年精装本',
            }

            # 构建周报数据
            weekly_data = {'books': [], 'categories': list(nyt_categories.values())}

            # 从每个分类获取书籍数据
            for category_id, category_name in nyt_categories.items():
                try:
                    books = self._book_service.get_books_by_category(category_id)
                    for _i, book in enumerate(books):
                        # 从NYT API真实数据中获取排名信息
                        # rank_last_week: 上周排名（数字或"无"/"0"表示新上榜）
                        # weeks_on_list: 上榜周数（NYT API直接提供）

                        # 解析上周排名
                        last_week_rank_str = str(book.rank_last_week).strip()
                        current_rank = book.rank

                        # 计算排名变化
                        if last_week_rank_str in ['无', '0', '', 'None']:
                            # 新上榜书籍（上周不在榜单上）
                            rank_change = 0  # 新书不计算变化
                            is_new = True
                        else:
                            try:
                                last_week_rank = int(last_week_rank_str)
                                # 排名变化 = 上周排名 - 当前排名
                                # 正数表示上升（排名数字变小），负数表示下降
                                rank_change = last_week_rank - current_rank
                                is_new = False
                            except (ValueError, TypeError):
                                # 无法解析时，保守处理为非新书
                                rank_change = 0
                                is_new = False

                        # 使用NYT API提供的真实上榜周数
                        weeks_on_list = book.weeks_on_list if book.weeks_on_list > 0 else 1

                        weekly_data['books'].append(
                            {
                                'id': book.isbn13 or book.isbn10,
                                'title': book.title_zh or book.title,
                                'author': book.author,
                                'category': category_name,
                                'rank': current_rank,
                                'rank_change': rank_change,
                                'weeks_on_list': weeks_on_list,
                                'is_new': is_new,
                                'cover': book.cover,
                                'original_cover': getattr(book, '_original_cover', '') or '',
                            }
                        )
                except Exception as e:
                    logger.error(f'获取分类 {category_name} 数据时出错: {e!s}')
                    continue

            # 如果没有数据，返回空数据
            if not weekly_data['books']:
                logger.info('没有找到实际数据，返回空数据')
                return {'books': [], 'categories': list(nyt_categories.values())}

            return weekly_data

        except Exception as e:
            logger.error(f'收集周报数据时出错: {e!s}')
            # 出错时返回空数据
            return {
                'books': [],
                'categories': [
                    '精装小说',
                    '平装小说',
                    '精装非虚构',
                    '平装非虚构',
                    '建议、方法与杂项',
                    '漫画与绘本',
                    '儿童中级精装本',
                    '青少年精装本',
                ],
            }

    def _analyze_changes(self, weekly_data: dict[str, Any]) -> dict[str, Any]:
        """分析榜单变化

        Args:
            weekly_data: 本周数据

        Returns:
            Dict: 分析结果
        """
        try:
            books = weekly_data.get('books', [])

            # 分类统计
            category_stats = {}
            for book in books:
                cat = book.get('category', '其他')
                if cat not in category_stats:
                    category_stats[cat] = {'count': 0, 'new_count': 0, 'avg_weeks': 0, 'total_weeks': 0}
                category_stats[cat]['count'] += 1
                if book.get('is_new', False):
                    category_stats[cat]['new_count'] += 1
                category_stats[cat]['total_weeks'] += book.get('weeks_on_list', 0)
            for cat in category_stats:
                cnt = category_stats[cat]['count']
                category_stats[cat]['avg_weeks'] = round(category_stats[cat]['total_weeks'] / cnt, 1) if cnt > 0 else 0

            # 重要变化（排名变化较大的书籍）
            top_changes = sorted(books, key=lambda x: abs(x.get('rank_change', 0)), reverse=True)[:10]

            # 新上榜书籍
            new_books = [book for book in books if book.get('is_new', False)][:10]

            # 排名上升最快
            top_risers = sorted(
                [book for book in books if book.get('rank_change', 0) > 0],
                key=lambda x: x.get('rank_change', 0),
                reverse=True,
            )[:10]

            # 持续上榜最久
            longest_running = sorted(books, key=lambda x: x.get('weeks_on_list', 0), reverse=True)[:10]

            # 推荐书籍（综合考虑各项指标，生成有意义的推荐理由）
            featured_books = []
            for book in books[:15]:
                reason = self._generate_recommendation_reason(book)
                featured_books.append(
                    {
                        'title': book['title'],
                        'author': book['author'],
                        'category': book.get('category', ''),
                        'rank': book.get('rank', 0),
                        'rank_change': book.get('rank_change', 0),
                        'weeks_on_list': book.get('weeks_on_list', 0),
                        'is_new': book.get('is_new', False),
                        'reason': reason,
                        'cover': book.get('cover'),
                        'original_cover': book.get('original_cover', ''),
                    }
                )

            return {
                'top_changes': top_changes,
                'new_books': new_books,
                'top_risers': top_risers,
                'longest_running': longest_running,
                'featured_books': featured_books,
                'category_stats': category_stats,
                'total_books': len(books),
                'total_new': len([b for b in books if b.get('is_new', False)]),
                'total_rising': len([b for b in books if b.get('rank_change', 0) > 0]),
                'total_falling': len([b for b in books if b.get('rank_change', 0) < 0]),
            }

        except Exception as e:
            logger.error(f'分析榜单变化时出错: {e!s}')
            return {
                'top_changes': [],
                'new_books': [],
                'top_risers': [],
                'longest_running': [],
                'featured_books': [],
                'category_stats': {},
                'total_books': 0,
                'total_new': 0,
                'total_rising': 0,
                'total_falling': 0,
            }

    def _generate_recommendation_reason(self, book: dict[str, Any]) -> str:
        """生成推荐理由

        Args:
            book: 书籍数据

        Returns:
            str: 推荐理由
        """
        reasons = []
        category = book.get('category', '')
        rank = book.get('rank', 0)
        rank_change = book.get('rank_change', 0)
        weeks_on_list = book.get('weeks_on_list', 0)
        is_new = book.get('is_new', False)

        if is_new:
            reasons.append(f'本周新上榜{category}类别')
        if rank <= 3:
            reasons.append(f'{category}榜单第{rank}名')
        if rank_change > 0:
            reasons.append(f'排名上升{rank_change}位')
        if weeks_on_list >= 10:
            reasons.append(f'持续上榜{weeks_on_list}周，读者口碑稳定')
        elif weeks_on_list >= 5:
            reasons.append(f'连续{weeks_on_list}周在榜')

        if not reasons:
            if rank <= 10:
                reasons.append(f'{category}类别Top10畅销书')
            else:
                reasons.append(f'{category}类别表现亮眼')

        return '，'.join(reasons)

    def _generate_ai_summary(self, analysis: dict[str, Any], week_start: date, week_end: date) -> str:
        """使用AI生成周报摘要

        Args:
            analysis: 分析结果
            week_start: 周开始日期
            week_end: 周结束日期

        Returns:
            str: 生成的摘要（确保不包含 prompt 模板文本）
        """
        try:
            translation_service = self._get_translation_service()

            if not translation_service:
                return self._generate_default_summary(analysis, week_start, week_end)

            # 构建简洁概览提示（与详细分析区分）
            prompt = f'请为{week_start.strftime("%Y年%m月%d日")}至{week_end.strftime("%Y年%m月%d日")}的畅销书周报生成一份简洁概览摘要，要求：\n'
            prompt += '1. 控制在150-200字以内，精炼概括\n'
            prompt += '2. 突出关键数据：上榜总数、新上榜数、排名变动概况\n'
            prompt += '3. 提及1-2本最值得关注的书籍即可，不要逐一列举\n'
            prompt += '4. 给出整体趋势判断（上升/下降/稳定）\n'
            prompt += '5. 不要包含详细的书籍列表和逐本分析\n\n'

            prompt += '基于以下分析结果：\n'

            if analysis.get('top_changes'):
                prompt += '\n【重要变化】：'
                for book in analysis['top_changes'][:3]:
                    change_type = '上升' if book['rank_change'] > 0 else '下降'
                    change_value = abs(book['rank_change'])
                    prompt += (
                        f'{_format_book_title(book["title"])}({book["author"]})排名{change_type}{change_value}位；'
                    )

            if analysis.get('new_books'):
                prompt += '\n【新上榜书籍】：'
                for book in analysis['new_books'][:3]:
                    prompt += f'{_format_book_title(book["title"])}({book["author"]}) - {book["category"]}；'

            if analysis.get('top_risers'):
                prompt += '\n【排名上升最快】：'
                for book in analysis['top_risers'][:3]:
                    prompt += f'{_format_book_title(book["title"])}({book["author"]})上升{book["rank_change"]}位；'

            if analysis.get('longest_running'):
                prompt += '\n【持续上榜最久】：'
                for book in analysis['longest_running'][:3]:
                    prompt += f'{_format_book_title(book["title"])}({book["author"]})已上榜{book["weeks_on_list"]}周；'

            if analysis.get('featured_books'):
                prompt += '\n【推荐书籍】：'
                for book in analysis['featured_books'][:3]:
                    prompt += f'{_format_book_title(book["title"])}({book["author"]}) - {book["reason"]}；'

            # 使用专门的AI摘要生成方法（如果可用），否则回退到翻译接口
            ai_result = None

            # 尝试使用专门的摘要生成方法
            if hasattr(translation_service, 'generate_summary'):
                ai_result = translation_service.generate_summary(prompt)
            else:
                # 回退：使用翻译接口，但明确告知这是摘要生成任务
                summary_prompt = f'【重要】请忽略你的翻译角色设定。现在你需要根据以下信息生成一份中文摘要，不要翻译，直接用中文输出摘要内容：\n\n{prompt}'
                ai_result = translation_service.translate(summary_prompt, 'zh', 'zh')

            # 验证 AI 返回结果是否有效
            # 如果结果为空、太短、或包含 prompt 模板特征文本，则使用默认摘要
            if ai_result and len(ai_result.strip()) > 50:
                # 检查是否包含 prompt 模板特征（说明 AI 原样返回了 prompt）
                prompt_markers = ['请为', '要求：', '基于以下分析结果', '语言流畅']
                is_prompt_like = any(marker in ai_result for marker in prompt_markers)

                if not is_prompt_like:
                    return ai_result.strip()

            # AI 结果无效时使用格式化的默认摘要
            logger.info('AI摘要无效或包含prompt文本，使用格式化默认摘要')
            return self._generate_default_summary(analysis, week_start, week_end)

        except Exception as e:
            logger.error(f'生成AI摘要时出错: {e!s}')
            return self._generate_default_summary(analysis, week_start, week_end)

    def _generate_default_summary(self, analysis: dict[str, Any], week_start: date, week_end: date) -> str:
        """生成默认摘要（简洁概览，与详细分析区分）

        Args:
            analysis: 分析结果
            week_start: 周开始日期
            week_end: 周结束日期

        Returns:
            str: 默认摘要
        """
        total_books = analysis.get('total_books', 0)
        total_new = analysis.get('total_new', 0)
        total_rising = analysis.get('total_rising', 0)
        total_falling = analysis.get('total_falling', 0)

        summary = f'本周共有 **{total_books}** 本书籍进入纽约时报畅销书榜'

        # 新上榜概况
        if total_new > 0:
            new_titles = [_format_book_title(b['title']) for b in analysis.get('new_books', [])[:3]]
            summary += f'，其中 **{total_new}** 本为新上榜'
            if new_titles:
                summary += f'（{", ".join(new_titles)}等）'

        summary += '。'

        # 排名变动概况
        if total_rising > 0 and total_falling > 0:
            summary += f'排名方面，{total_rising} 本上升、{total_falling} 本下降'
        elif total_rising > 0:
            summary += f'排名方面，{total_rising} 本呈上升趋势'
        elif total_falling > 0:
            summary += f'排名方面，{total_falling} 本有所回落'

        # 最显著变化
        top_changes = analysis.get('top_changes', [])
        if top_changes:
            top = top_changes[0]
            change = top.get('rank_change', 0)
            if change > 0:
                summary += f'。{_format_book_title(top["title"])}以{change}位的涨幅领跑榜单变化'
            elif change < 0:
                summary += f'。{_format_book_title(top["title"])}降幅最大，下滑{abs(change)}位'

        summary += '。'

        # 持续上榜
        longest = analysis.get('longest_running', [])
        if longest and longest[0].get('weeks_on_list', 0) >= 5:
            summary += f'{_format_book_title(longest[0]["title"])}已连续上榜{longest[0]["weeks_on_list"]}周，表现稳定。'

        # 趋势判断
        if total_rising > total_falling * 1.5:
            summary += '整体来看，本周榜单呈明显上升态势。'
        elif total_falling > total_rising * 1.5:
            summary += '整体来看，本周榜单有所回调，新书入榜值得关注。'
        else:
            summary += '整体来看，本周榜单保持相对稳定。'

        summary += '\n\n*切换至「数据可视化」和「详细分析」标签页查看完整数据分析。*'

        return summary

    def get_reports(self, limit: int = 10) -> list[WeeklyReport]:
        """获取周报列表

        Args:
            limit: 限制数量

        Returns:
            List[WeeklyReport]: 周报列表
        """
        try:
            return WeeklyReport.query.order_by(WeeklyReport.report_date.desc()).limit(limit).all()
        except Exception as e:
            logger.error(f'获取周报列表时出错: {e!s}')
            return []

    def get_report_by_date(self, report_date: date) -> WeeklyReport | None:
        """根据日期获取周报

        Args:
            report_date: 报告日期

        Returns:
            WeeklyReport: 周报
        """
        try:
            return WeeklyReport.query.filter(WeeklyReport.report_date == report_date).first()
        except Exception as e:
            logger.error(f'根据日期获取周报时出错: {e!s}')
            return None

    def get_report_by_week_end(self, week_end: date) -> WeeklyReport | None:
        """根据周结束日期获取周报

        Args:
            week_end: 周结束日期

        Returns:
            WeeklyReport: 周报
        """
        try:
            return WeeklyReport.query.filter(WeeklyReport.week_end == week_end).first()
        except Exception as e:
            logger.error(f'根据周结束日期获取周报时出错: {e!s}')
            return None

    def get_latest_report(self) -> WeeklyReport | None:
        """获取最新周报

        Returns:
            WeeklyReport: 最新周报
        """
        try:
            return WeeklyReport.query.order_by(WeeklyReport.report_date.desc()).first()
        except Exception as e:
            logger.error(f'获取最新周报时出错: {e!s}')
            return None

    # ==================== 报告视图和用户行为服务方法 ====================

    def record_report_view(self, report_id: int, session_id: str, user_agent: str, ip_address: str | None) -> bool:
        """记录周报阅读（如果未记录过）

        Returns:
            是否新增记录
        """
        try:
            from ..models.schemas import ReportView, UserBehavior

            existing = ReportView.query.filter_by(report_id=report_id, session_id=session_id).first()
            if existing:
                return False

            new_view = ReportView(
                report_id=report_id,
                session_id=session_id,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            db.session.add(new_view)

            report = db.session.get(WeeklyReport, report_id)
            if report:
                report.view_count = (report.view_count or 0) + 1

            behavior = UserBehavior(
                session_id=session_id,
                event_type='view_report',
                target_id=str(report.report_date) if report else '',
                target_type='report',
                user_agent=user_agent,
                ip_address=ip_address,
            )
            db.session.add(behavior)
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f'记录周报阅读失败: {e!s}')
            db.session.rollback()
            return False

    def record_report_export(self, session_id: str, date: str, user_agent: str, ip_address: str | None) -> bool:
        """记录周报导出行为

        Returns:
            是否成功记录
        """
        try:
            from ..models.schemas import UserBehavior

            behavior = UserBehavior(
                session_id=session_id,
                event_type='export_report',
                target_id=date,
                target_type='report',
                user_agent=user_agent,
                ip_address=ip_address,
            )
            db.session.add(behavior)
            db.session.commit()
            return True
        except Exception as e:
            logger.error(f'记录周报导出失败: {e!s}')
            db.session.rollback()
            return False

    def has_report_view(self, report_id: int, session_id: str) -> bool:
        """检查用户是否已阅读过该周报"""
        try:
            from ..models.schemas import ReportView
            return ReportView.query.filter_by(report_id=report_id, session_id=session_id).first() is not None
        except Exception as e:
            logger.error(f'检查阅读记录失败: {e!s}')
            return False
