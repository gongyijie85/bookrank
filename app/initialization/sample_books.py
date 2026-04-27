"""
示例图书数据初始化模块
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


SAMPLE_BOOKS = [
    # 普利策奖 (Pulitzer Prize)
    {'award_name': '普利策奖', 'year': 2025, 'category': '小说', 'rank': 1,
     'title': 'James', 'author': 'Percival Everett',
     'description': 'A brilliant reimagining of Adventures of Huckleberry Finn from the perspective of Jim, the enslaved man.',
     'isbn13': '9780385550369', 'cover_url': None},
    
    {'award_name': '普利策奖', 'year': 2024, 'category': '小说', 'rank': 1,
     'title': 'The Nickel Boys', 'author': 'Colson Whitehead',
     'description': 'Based on the true story of a reform school in Florida that operated for over a century.',
     'isbn13': '9780385537070', 'cover_url': None},
    
    {'award_name': '普利策奖', 'year': 2023, 'category': '小说', 'rank': 1,
     'title': 'Demon Copperhead', 'author': 'Barbara Kingsolver',
     'description': 'A modern retelling of David Copperfield set in Appalachia, following a boy born to a teenage single mother.',
     'isbn13': '9780063251922', 'cover_url': None},
    
    {'award_name': '普利策奖', 'year': 2023, 'category': '非虚构', 'rank': 1,
     'title': 'His Name Is George Floyd', 'author': 'Robert Samuels, Toluse Olorunnipa',
     'description': 'A biography of George Floyd that explores the racial justice movement and systemic inequality in America.',
     'isbn13': '9780593491930', 'cover_url': None},
    
    {'award_name': '普利策奖', 'year': 2022, 'category': '小说', 'rank': 1,
     'title': 'The Netanyahus', 'author': 'Joshua Cohen',
     'description': 'A comic novel about a Jewish historian who meets the Netanyahu family in 1959.',
     'isbn13': '9781681376070', 'cover_url': None},
    
    # 布克奖 (Booker Prize)
    {'award_name': '布克奖', 'year': 2025, 'category': '小说', 'rank': 1,
     'title': 'The Safekeep', 'author': 'Yael van der Wouden',
     'description': 'A debut novel set in the Dutch countryside in the 1960s, exploring desire and betrayal.',
     'isbn13': '9781668052541', 'cover_url': None},
    
    {'award_name': '布克奖', 'year': 2024, 'category': '小说', 'rank': 1,
     'title': 'Orbital', 'author': 'Samantha Harvey',
     'description': 'A novel set on the International Space Station, exploring the lives of six astronauts.',
     'isbn13': '9780802163784', 'cover_url': None},
    
    {'award_name': '布克奖', 'year': 2023, 'category': '小说', 'rank': 1,
     'title': 'Prophet Song', 'author': 'Paul Lynch',
     'description': 'A dystopian novel about a mother searching for her son in a collapsing Ireland.',
     'isbn13': '9780802161506', 'cover_url': None},
    
    {'award_name': '布克奖', 'year': 2022, 'category': '小说', 'rank': 1,
     'title': 'The Seven Moons of Maali Almeida', 'author': 'Shehan Karunatilaka',
     'description': 'A satirical novel about a war photographer who wakes up dead in a celestial visa office.',
     'isbn13': '9781324035910', 'cover_url': None},
    
    # 诺贝尔文学奖 (Nobel Prize in Literature)
    {'award_name': '诺贝尔文学奖', 'year': 2025, 'category': '文学', 'rank': 1,
     'title': 'Human Acts', 'author': 'Han Kang',
     'description': 'A novel about the 1980 Gwangju Uprising in South Korea, exploring trauma and humanity.',
     'isbn13': '9781101906729', 'cover_url': None},
    
    {'award_name': '诺贝尔文学奖', 'year': 2024, 'category': '文学', 'rank': 1,
     'title': 'The Vegetarian', 'author': 'Han Kang',
     'description': 'A dark and surreal novel about a woman who decides to stop eating meat and the consequences that follow.',
     'isbn13': '9780553448184', 'cover_url': None},
    
    {'award_name': '诺贝尔文学奖', 'year': 2023, 'category': '文学', 'rank': 1,
     'title': 'A New Name: Septology VI-VII', 'author': 'Jon Fosse',
     'description': 'The final installment of the Septology series, exploring the life of an aging painter.',
     'isbn13': '9781555978896', 'cover_url': None},
    
    {'award_name': '诺贝尔文学奖', 'year': 2022, 'category': '文学', 'rank': 1,
     'title': 'The Years', 'author': 'Annie Ernaux',
     'description': 'A memoir that blends personal and collective history from 1941 to 2006.',
     'isbn13': '9781609808927', 'cover_url': None},
    
    # 雨果奖 (Hugo Award)
    {'award_name': '雨果奖', 'year': 2025, 'category': '最佳长篇小说', 'rank': 1,
     'title': 'The Tainted Cup', 'author': 'Robert Jackson Bennett',
     'description': 'A mystery fantasy novel featuring a Holmes-like detective in a world where magic is powered by parasitic infection.',
     'isbn13': '9781984820709', 'cover_url': None},
    
    {'award_name': '雨果奖', 'year': 2024, 'category': '最佳长篇小说', 'rank': 1,
     'title': 'Some Desperate Glory', 'author': 'Emily Tesh',
     'description': 'A space opera about a young woman raised on a space station to avenge Earth\'s destruction.',
     'isbn13': '9781250834989', 'cover_url': None},
    
    {'award_name': '雨果奖', 'year': 2023, 'category': '最佳长篇小说', 'rank': 1,
     'title': 'Nettle & Bone', 'author': 'T. Kingfisher',
     'description': 'A fantasy novel about a princess who must save her sister from an abusive husband.',
     'isbn13': '9781250244048', 'cover_url': None},
    
    {'award_name': '雨果奖', 'year': 2022, 'category': '最佳长篇小说', 'rank': 1,
     'title': 'A Desolation Called Peace', 'author': 'Arkady Martine',
     'description': 'A space opera about first contact with a terrifying alien species. Sequel to A Memory Called Empire.',
     'isbn13': '9781250186461', 'cover_url': None},
    
    # 星云奖 (Nebula Award)
    {'award_name': '星云奖', 'year': 2025, 'category': '最佳长篇小说', 'rank': 1,
     'title': 'The Mimicking of Known Successes', 'author': 'Malka Older',
     'description': 'A mystery set on a distant space station, featuring a Holmes-like detective investigating a missing person case.',
     'isbn13': '9781250897472', 'cover_url': None},
    
    {'award_name': '星云奖', 'year': 2024, 'category': '最佳长篇小说', 'rank': 1,
     'title': 'The Saint of Bright Doors', 'author': 'Vajra Chandrasekera',
     'description': 'A fantasy novel about a man raised to assassinate a messiah figure, exploring destiny and choice.',
     'isbn13': '9781250842700', 'cover_url': None},
    
    {'award_name': '星云奖', 'year': 2023, 'category': '最佳长篇小说', 'rank': 1,
     'title': 'Babel: Or the Necessity of Violence', 'author': 'R.F. Kuang',
     'description': 'A dark academia fantasy about a magical translation institute in 1830s Oxford, exploring colonialism and language.',
     'isbn13': '9780063021426', 'cover_url': None},
    
    {'award_name': '星云奖', 'year': 2022, 'category': '最佳长篇小说', 'rank': 1,
     'title': 'A Desolation Called Peace', 'author': 'Arkady Martine',
     'description': 'Sequel to A Memory Called Empire, continuing the story of an interstellar empire and its complex diplomatic relations.',
     'isbn13': '9781250186461', 'cover_url': None},
    
    # 国际布克奖 (International Booker Prize)
    {'award_name': '国际布克奖', 'year': 2025, 'category': '翻译小说', 'rank': 1,
     'title': 'The Details', 'author': 'Ia Genberg',
     'description': 'A Swedish novel about four women whose lives intersect, exploring friendship and identity.',
     'isbn13': '9781662602031', 'cover_url': None},

    {'award_name': '国际布克奖', 'year': 2024, 'category': '翻译小说', 'rank': 1,
     'title': 'Kairos', 'author': 'Jenny Erpenbeck',
     'description': 'A love story set in East Germany before the fall of the Berlin Wall, exploring personal and political transformation.',
     'isbn13': '9780811232011', 'cover_url': None},

    {'award_name': '国际布克奖', 'year': 2023, 'category': '翻译小说', 'rank': 1,
     'title': 'Time Shelter', 'author': 'Georgi Gospodinov',
     'description': 'A novel about a clinic that recreates past decades to help Alzheimer\'s patients, exploring memory and nostalgia.',
     'isbn13': '9781324008372', 'cover_url': None},
    
    {'award_name': '国际布克奖', 'year': 2022, 'category': '翻译小说', 'rank': 1,
     'title': 'Tomb of Sand', 'author': 'Geetanjali Shree',
     'description': 'An Indian widow defies expectations and travels to Pakistan to confront her past, translated from Hindi.',
     'isbn13': '9781953861162', 'cover_url': None},
    
    # 爱伦·坡奖 (Edgar Award)
    {'award_name': '爱伦·坡奖', 'year': 2025, 'category': '最佳小说', 'rank': 1,
     'title': 'King of Ashes', 'author': 'S.A. Cosby',
     'description': 'A gripping crime novel about two brothers on opposite sides of the law in rural Virginia.',
     'isbn13': '9781250867291', 'cover_url': None},

    {'award_name': '爱伦·坡奖', 'year': 2024, 'category': '最佳小说', 'rank': 1,
     'title': 'The River We Remember', 'author': 'William Kent Krueger',
     'description': 'A murder mystery set in 1950s Minnesota, exploring small-town secrets and racial tensions.',
     'isbn13': '9781982178697', 'cover_url': None},

    {'award_name': '爱伦·坡奖', 'year': 2023, 'category': '最佳小说', 'rank': 1,
     'title': 'The Accomplice', 'author': 'Lisa Lutz',
     'description': 'A psychological thriller about two lifelong friends bound by a dark secret from their teenage years.',
     'isbn13': '9781982168322', 'cover_url': None},
    
    {'award_name': '爱伦·坡奖', 'year': 2022, 'category': '最佳小说', 'rank': 1,
     'title': 'Billy Summers', 'author': 'Stephen King',
     'description': 'A hired killer with a conscience takes on one last job, but things go terribly wrong.',
     'isbn13': '9781982173616', 'cover_url': None},
]


def init_sample_books(app):
    """
    初始化示例图书数据
    """
    try:
        from ..models.schemas import Award, AwardBook
        from ..services import AwardBookService
        from ..models.database import db
        
        service = AwardBookService(app)
        
        # Render 启动优化：跳过 Wikidata API 调用，使用本地数据
        # API 刷新将在用户访问奖项页面时按需执行
        app.logger.info("⏭️ 跳过启动时API刷新，将在用户访问时按需获取数据")
        
        # try:
        #     service.fetch_missing_covers(batch_size=20)
        # except Exception as cover_error:
        #     app.logger.warning(f"⚠️ 获取封面失败: {cover_error}")
        app.logger.info("⏭️ 跳过启动时封面获取，将在用户访问时按需获取")
        
        created_count = 0
        updated_count = 0
        
        for book_data in SAMPLE_BOOKS:
            award = Award.query.filter_by(name=book_data['award_name']).first()
            if not award:
                continue
            
            isbn = book_data.get('isbn13')
            
            if isbn:
                existing = AwardBook.query.filter_by(isbn13=isbn).first()
            else:
                existing = AwardBook.query.filter_by(
                    title=book_data['title'],
                    author=book_data['author']
                ).first()
            
            if existing:
                if isbn and not existing.isbn13:
                    existing.isbn13 = isbn
                    updated_count += 1
                if book_data.get('cover_url') and not existing.cover_original_url:
                    existing.cover_original_url = book_data['cover_url']
                    updated_count += 1
            else:
                book = AwardBook(
                    award_id=award.id,
                    year=book_data['year'],
                    category=book_data['category'],
                    rank=book_data['rank'],
                    title=book_data['title'],
                    author=book_data['author'],
                    description=book_data['description'],
                    isbn13=isbn,
                    cover_original_url=book_data.get('cover_url')
                )
                db.session.add(book)
                created_count += 1
        
        if created_count > 0 or updated_count > 0:
            db.session.commit()
            app.logger.info(f"✅ 图书: 新建 {created_count} 本, 更新 {updated_count} 本")
        else:
            app.logger.info("✅ 所有图书已是最新")
        
        app.logger.info("⏭️ 跳过自动封面获取，将在用户查看详情时按需获取")
        
        # 开发环境跳过图书验证，加快启动速度
        app.logger.info("⏭️ 跳过图书验证，加快启动速度")
        # if app.config.get('DEBUG'):
        #     app.logger.info("⏭️ 开发环境：跳过图书验证")
        # else:
        #     app.logger.info("🔍 开始自动验证图书...")
        #     try:
        #         from ..services.book_verification_service import BookVerificationService
        #         verifier = BookVerificationService()
        #         results = verifier.verify_all_pending(limit=20)
        #         
        #         summary = verifier.get_verification_summary()
        #         app.logger.info(f"✅ 图书验证完成: 总计 {summary['total']}, "
        #                       f"已验证 {summary['verified']}, "
        #                       f"待验证 {summary['pending']}, "
        #                       f"失败 {summary['failed']}, "
        #                       f"可展示 {summary['displayable']}")
        #     except Exception as verify_error:
        #         app.logger.error(f"❌ 图书验证失败: {verify_error}")
        
    except Exception as e:
        app.logger.error(f"❌ 初始化示例图书失败: {e}", exc_info=True)
        from ..models.database import db
        db.session.rollback()
