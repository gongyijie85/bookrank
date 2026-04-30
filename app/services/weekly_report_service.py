"""周报服务"""
import json
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

from ..models.schemas import db, WeeklyReport, BookMetadata
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
                logger.warning(f"无法初始化翻译服务: {e}")
        return self._translation_service
    
    def generate_report(self, week_start: date, week_end: date, force_regenerate: bool = False) -> Optional[WeeklyReport]:
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
                WeeklyReport.week_start == week_start,
                WeeklyReport.week_end == week_end
            ).first()

            if existing_report and not force_regenerate:
                logger.info(f"周报已存在: {week_start} 至 {week_end}")
                return existing_report

            # 如果是强制重新生成且旧报告存在，先删除
            if existing_report and force_regenerate:
                logger.info(f"强制重新生成周报: {week_start} 至 {week_end}")
                db.session.delete(existing_report)
                db.session.commit()
            
            # 收集本周数据
            weekly_data = self._collect_weekly_data(week_start, week_end)
            
            # 检查是否有足够的数据
            if not weekly_data.get('books'):
                logger.warning(f"数据不足，无法生成周报: {week_start} 至 {week_end}")
                return None
            
            # 分析变化
            analysis = self._analyze_changes(weekly_data)
            
            # 生成报告标题
            title = f"{week_start.strftime('%Y年%m月%d日')}-{week_end.strftime('%Y年%m月%d日')} 畅销书周报"
            
            # 生成AI摘要
            summary = self._generate_ai_summary(analysis, week_start, week_end)
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
                'total_falling': analysis.get('total_falling', 0)
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
                featured_books=json.dumps(analysis.get('featured_books', []), ensure_ascii=False)
            )
            
            # 保存到数据库
            db.session.add(report)
            db.session.commit()
            
            return report
            
        except Exception as e:
            logger.error(f"生成周报时出错: {str(e)}")
            db.session.rollback()
            # 出错时再次检查是否已存在报告
            existing_report = WeeklyReport.query.filter(
                WeeklyReport.week_start == week_start,
                WeeklyReport.week_end == week_end
            ).first()
            if existing_report:
                return existing_report
            return None
    
    def _collect_weekly_data(self, week_start: date, week_end: date) -> Dict[str, Any]:
        """收集本周数据

        Args:
            week_start: 周开始日期
            week_end: 周结束日期

        Returns:
            Dict: 本周数据
        """
        try:
            # 从纽约时报API获取数据
            from ..models.schemas import Book
            
            # 定义纽约时报书籍分类
            nyt_categories = {
                'hardcover-fiction': '精装小说',
                'paperback-fiction': '平装小说',
                'hardcover-nonfiction': '精装非虚构',
                'paperback-nonfiction': '平装非虚构',
                'advice-how-to-and-miscellaneous': '建议、方法与杂项',
                'graphic-books-and-manga': '漫画与绘本',
                'childrens-middle-grade-hardcover': '儿童中级精装本',
                'young-adult-hardcover': '青少年精装本'
            }
            
            # 构建周报数据
            weekly_data = {
                'books': [],
                'categories': list(nyt_categories.values())
            }
            
            # 从每个分类获取书籍数据
            for category_id, category_name in nyt_categories.items():
                try:
                    books = self._book_service.get_books_by_category(category_id)
                    for i, book in enumerate(books):
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

                        weekly_data['books'].append({
                            'id': book.isbn13 or book.isbn10,
                            'title': book.title_zh or book.title,
                            'author': book.author,
                            'category': category_name,
                            'rank': current_rank,
                            'rank_change': rank_change,
                            'weeks_on_list': weeks_on_list,
                            'is_new': is_new,
                            'cover': book.cover,
                            'original_cover': getattr(book, '_original_cover', '') or ''
                        })
                except Exception as e:
                    logger.error(f"获取分类 {category_name} 数据时出错: {str(e)}")
                    continue
            
            # 如果没有数据，返回空数据
            if not weekly_data['books']:
                logger.info("没有找到实际数据，返回空数据")
                return {
                    'books': [],
                    'categories': list(nyt_categories.values())
                }
            
            return weekly_data
            
        except Exception as e:
            logger.error(f"收集周报数据时出错: {str(e)}")
            # 出错时返回空数据
            return {
                'books': [],
                'categories': ['精装小说', '平装小说', '精装非虚构', '平装非虚构', '建议、方法与杂项', '漫画与绘本', '儿童中级精装本', '青少年精装本']
            }
    

    
    def _analyze_changes(self, weekly_data: Dict[str, Any]) -> Dict[str, Any]:
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
            top_changes = sorted(
                books,
                key=lambda x: abs(x.get('rank_change', 0)),
                reverse=True
            )[:10]
            
            # 新上榜书籍
            new_books = [book for book in books if book.get('is_new', False)][:10]
            
            # 排名上升最快
            top_risers = sorted(
                [book for book in books if book.get('rank_change', 0) > 0],
                key=lambda x: x.get('rank_change', 0),
                reverse=True
            )[:10]
            
            # 持续上榜最久
            longest_running = sorted(
                books,
                key=lambda x: x.get('weeks_on_list', 0),
                reverse=True
            )[:10]
            
            # 推荐书籍（综合考虑各项指标，生成有意义的推荐理由）
            featured_books = []
            for book in books[:15]:
                reason = self._generate_recommendation_reason(book)
                featured_books.append({
                    'title': book['title'],
                    'author': book['author'],
                    'category': book.get('category', ''),
                    'rank': book.get('rank', 0),
                    'rank_change': book.get('rank_change', 0),
                    'weeks_on_list': book.get('weeks_on_list', 0),
                    'is_new': book.get('is_new', False),
                    'reason': reason,
                    'cover': book.get('cover'),
                    'original_cover': book.get('original_cover', '')
                })
            
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
                'total_falling': len([b for b in books if b.get('rank_change', 0) < 0])
            }
            
        except Exception as e:
            logger.error(f"分析榜单变化时出错: {str(e)}")
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
                'total_falling': 0
            }
    
    def _generate_recommendation_reason(self, book: Dict[str, Any]) -> str:
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
            reasons.append(f"本周新上榜{category}类别")
        if rank <= 3:
            reasons.append(f"{category}榜单第{rank}名")
        if rank_change > 0:
            reasons.append(f"排名上升{rank_change}位")
        if weeks_on_list >= 10:
            reasons.append(f"持续上榜{weeks_on_list}周，读者口碑稳定")
        elif weeks_on_list >= 5:
            reasons.append(f"连续{weeks_on_list}周在榜")
        
        if not reasons:
            if rank <= 10:
                reasons.append(f"{category}类别Top10畅销书")
            else:
                reasons.append(f"{category}类别表现亮眼")
        
        return "，".join(reasons)
    
    def _generate_ai_summary(self, analysis: Dict[str, Any], week_start: date, week_end: date) -> str:
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
            
            # 构建详细提示
            prompt = f"请为{week_start.strftime('%Y年%m月%d日')}至{week_end.strftime('%Y年%m月%d日')}的畅销书周报生成一份详细、专业的摘要，要求：\n"
            prompt += "1. 语言流畅，逻辑清晰，信息准确\n"
            prompt += "2. 包含本周的主要趋势和亮点\n"
            prompt += "3. 分析各类别书籍的表现\n"
            prompt += "4. 突出重要变化和值得关注的书籍\n"
            prompt += "5. 提供有洞察力的分析和见解\n\n"
            
            prompt += "基于以下分析结果：\n"
            
            if analysis.get('top_changes'):
                prompt += "\n【重要变化】："
                for book in analysis['top_changes'][:3]:
                    change_type = "上升" if book['rank_change'] > 0 else "下降"
                    change_value = abs(book['rank_change'])
                    prompt += f"{_format_book_title(book['title'])}({book['author']})排名{change_type}{change_value}位；"
            
            if analysis.get('new_books'):
                prompt += "\n【新上榜书籍】："
                for book in analysis['new_books'][:3]:
                    prompt += f"{_format_book_title(book['title'])}({book['author']}) - {book['category']}；"
            
            if analysis.get('top_risers'):
                prompt += "\n【排名上升最快】："
                for book in analysis['top_risers'][:3]:
                    prompt += f"{_format_book_title(book['title'])}({book['author']})上升{book['rank_change']}位；"
            
            if analysis.get('longest_running'):
                prompt += "\n【持续上榜最久】："
                for book in analysis['longest_running'][:3]:
                    prompt += f"{_format_book_title(book['title'])}({book['author']})已上榜{book['weeks_on_list']}周；"
            
            if analysis.get('featured_books'):
                prompt += "\n【推荐书籍】："
                for book in analysis['featured_books'][:3]:
                    prompt += f"{_format_book_title(book['title'])}({book['author']}) - {book['reason']}；"

            # 使用专门的AI摘要生成方法（如果可用），否则回退到翻译接口
            ai_result = None

            # 尝试使用专门的摘要生成方法
            if hasattr(translation_service, 'generate_summary'):
                ai_result = translation_service.generate_summary(prompt)
            else:
                # 回退：使用翻译接口，但明确告知这是摘要生成任务
                summary_prompt = f"【重要】请忽略你的翻译角色设定。现在你需要根据以下信息生成一份中文摘要，不要翻译，直接用中文输出摘要内容：\n\n{prompt}"
                ai_result = translation_service.translate(summary_prompt, "zh", "zh")
            
            # 验证 AI 返回结果是否有效
            # 如果结果为空、太短、或包含 prompt 模板特征文本，则使用默认摘要
            if ai_result and len(ai_result.strip()) > 50:
                # 检查是否包含 prompt 模板特征（说明 AI 原样返回了 prompt）
                prompt_markers = ['请为', '要求：', '基于以下分析结果', '语言流畅']
                is_prompt_like = any(marker in ai_result for marker in prompt_markers)
                
                if not is_prompt_like:
                    return ai_result.strip()
            
            # AI 结果无效时使用格式化的默认摘要
            logger.info("AI摘要无效或包含prompt文本，使用格式化默认摘要")
            return self._generate_default_summary(analysis, week_start, week_end)
                
        except Exception as e:
            logger.error(f"生成AI摘要时出错: {str(e)}")
            return self._generate_default_summary(analysis, week_start, week_end)
    
    def _generate_default_summary(self, analysis: Dict[str, Any], week_start: date, week_end: date) -> str:
        """生成默认摘要
        
        Args:
            analysis: 分析结果
            week_start: 周开始日期
            week_end: 周结束日期
            
        Returns:
            str: 默认摘要
        """
        summary = f"# {week_start.strftime('%Y年%m月%d日')}至{week_end.strftime('%Y年%m月%d日')} 畅销书周报\n\n"
        
        # 总体概览
        total_books = len(analysis.get('top_changes', [])) + len(analysis.get('new_books', []))
        summary += f"## 总体概览\n"
        summary += f"本周共有 {total_books} 本书籍进入榜单，整体呈现出多样化的阅读趋势。\n\n"
        
        # 重要变化
        if analysis.get('top_changes') and len(analysis['top_changes']) > 0:
            summary += "## 📊 重要变化\n"
            for book in analysis['top_changes'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                if book['rank_change'] > 0:
                    summary += f"- {cover_tag}{_format_book_title(book['title'])}({book['author']}) 排名显著上升 {book['rank_change']} 位\n"
                elif book['rank_change'] < 0:
                    summary += f"- {cover_tag}{_format_book_title(book['title'])}({book['author']}) 排名下降 {abs(book['rank_change'])} 位\n"
            summary += "\n"
        
        # 新上榜书籍
        if analysis.get('new_books') and len(analysis['new_books']) > 0:
            summary += "## ✨ 新上榜书籍\n"
            for book in analysis['new_books'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                summary += f"- {cover_tag}{_format_book_title(book['title'])}({book['author']}) - {book['category']} 类别\n"
            summary += "\n"
        
        # 排名上升最快
        if analysis.get('top_risers') and len(analysis['top_risers']) > 0:
            summary += "## 🚀 排名上升最快\n"
            for book in analysis['top_risers'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                summary += f"- {cover_tag}{_format_book_title(book['title'])}({book['author']}) 上升 {book['rank_change']} 位\n"
            summary += "\n"
        
        # 持续上榜最久
        if analysis.get('longest_running') and len(analysis['longest_running']) > 0:
            summary += "## 🏆 持续上榜最久\n"
            for book in analysis['longest_running'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                summary += f"- {cover_tag}{_format_book_title(book['title'])}({book['author']}) 已上榜 {book['weeks_on_list']} 周\n"
            summary += "\n"
        
        # 推荐书籍
        if analysis.get('featured_books') and len(analysis['featured_books']) > 0:
            summary += "## 💡 推荐书籍\n"
            for book in analysis['featured_books'][:5]:
                cover = book.get('cover', '')
                cover_tag = f'<img src="{cover}" style="max-width:60px;height:auto;width:auto;max-height:90px;border-radius:4px;vertical-align:middle;margin-right:10px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">' if cover else ''
                summary += f"- {cover_tag}{_format_book_title(book['title'])}({book['author']}) - {book['reason']}\n"
            summary += "\n"
        
        # 总结
        summary += "## 📈 本周趋势\n"
        summary += "本周畅销书榜单呈现出多元化的阅读偏好，既有经典作品持续霸榜，也有新人新作异军突起。\n"
        summary += "不同类别书籍各有亮点，反映了当前读者对多样化内容的需求。\n\n"
        summary += "详细分析请查看完整报告，了解更多畅销书动态和深度分析。"
        
        return summary
    
    def get_reports(self, limit: int = 10) -> List[WeeklyReport]:
        """获取周报列表
        
        Args:
            limit: 限制数量
            
        Returns:
            List[WeeklyReport]: 周报列表
        """
        try:
            return WeeklyReport.query.order_by(WeeklyReport.report_date.desc()).limit(limit).all()
        except Exception as e:
            logger.error(f"获取周报列表时出错: {str(e)}")
            return []
    
    def get_report_by_date(self, report_date: date) -> Optional[WeeklyReport]:
        """根据日期获取周报
        
        Args:
            report_date: 报告日期
            
        Returns:
            WeeklyReport: 周报
        """
        try:
            return WeeklyReport.query.filter(WeeklyReport.report_date == report_date).first()
        except Exception as e:
            logger.error(f"根据日期获取周报时出错: {str(e)}")
            return None
            
    def get_report_by_week_end(self, week_end: date) -> Optional[WeeklyReport]:
        """根据周结束日期获取周报
        
        Args:
            week_end: 周结束日期
            
        Returns:
            WeeklyReport: 周报
        """
        try:
            return WeeklyReport.query.filter(WeeklyReport.week_end == week_end).first()
        except Exception as e:
            logger.error(f"根据周结束日期获取周报时出错: {str(e)}")
            return None
    
    def get_latest_report(self) -> Optional[WeeklyReport]:
        """获取最新周报
        
        Returns:
            WeeklyReport: 最新周报
        """
        try:
            return WeeklyReport.query.order_by(WeeklyReport.report_date.desc()).first()
        except Exception as e:
            logger.error(f"获取最新周报时出错: {str(e)}")
            return None
