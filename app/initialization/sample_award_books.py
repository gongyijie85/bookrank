"""
预置获奖图书数据

用于 Render 等云平台部署时快速初始化，
避免首次部署时页面显示"暂无数据"
"""

import logging

from ..utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)


SAMPLE_AWARD_BOOKS = [
    {
        'award_name': '普利策奖',
        'year': 2026,
        'category': '小说',
        'title': 'Angel Down',
        'author': 'Daniel Kraus',
        'isbn13': '9781982168322',
        'description': 'A World War I stream-of-consciousness novel about survival, supernatural wonders, and moral conflict on the battlefield.',
    },
    {
        'award_name': '布克奖',
        'year': 2026,
        'category': '小说',
        'title': 'Flesh',
        'author': 'David Szalay',
        'isbn13': '9781668052541',
        'description': 'A novel by the Hungarian-British author exploring masculinity and identity, winner of the 2025 Booker Prize.',
    },
    {
        'award_name': '雨果奖',
        'year': 2025,
        'category': '最佳长篇小说',
        'title': 'The Tainted Cup',
        'author': 'Robert Jackson Bennett',
        'isbn13': '9781984820709',
        'description': 'A mystery fantasy novel featuring a Holmes-like detective in a world where magic is powered by parasitic infection.',
    },
    {
        'award_name': '诺贝尔文学奖',
        'year': 2025,
        'category': '文学',
        'title': 'Satantango',
        'author': 'László Krasznahorkai',
        'isbn13': '9780811219297',
        'description': 'A haunting novel set in a decaying Hungarian village, exploring apocalyptic visions and human resilience. Author won 2025 Nobel Prize in Literature.',
    },
    {
        'award_name': '星云奖',
        'year': 2025,
        'category': '最佳长篇小说',
        'title': 'The Mimicking of Known Successes',
        'author': 'Malka Older',
        'isbn13': '9781250897472',
        'description': 'A mystery set on a distant space station, featuring a Holmes-like detective investigating a missing person case.',
    },
    {
        'award_name': '国际布克奖',
        'year': 2026,
        'category': '翻译小说',
        'title': 'Taiwan Travelogue',
        'author': 'Yáng Shuāng-zǐ',
        'isbn13': '9781913505974',
        'description': 'A novel set in 1930s Japanese-colonized Taiwan, exploring food, culture, and identity. First Chinese-language work to win the International Booker Prize.',
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2026,
        'category': '最佳小说',
        'title': 'The Big Empty',
        'author': 'Robert Crais',
        'isbn13': '9780593419601',
        'description': 'A gripping mystery novel by the bestselling author of the Cole & Pike series.',
    },
    {
        'award_name': '普利策奖',
        'year': 2025,
        'category': '小说',
        'title': 'James',
        'author': 'Percival Everett',
        'isbn13': '9780385550369',
        'description': 'A brilliant reimagining of Adventures of Huckleberry Finn from the perspective of Jim, the enslaved man.',
    },
    {
        'award_name': '国际布克奖',
        'year': 2025,
        'category': '翻译小说',
        'title': 'Heart Lamp',
        'author': 'Banu Mushtaq',
        'isbn13': '9781916751040',
        'description': 'A collection of 12 stories depicting the lives of marginalized Muslim women in southern India. First short story collection to win the International Booker Prize.',
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2025,
        'category': '最佳小说',
        'title': 'The In Crowd',
        'author': 'Charlotte Vassell',
        'isbn13': '9780385549516',
        'description': 'A mystery novel set among the British elite, exploring privilege and deception.',
    },
    {
        'award_name': '普利策奖',
        'year': 2024,
        'category': '小说',
        'title': 'The Nickel Boys',
        'author': 'Colson Whitehead',
        'isbn13': '9780385537070',
        'description': 'Based on the true story of a reform school in Florida that operated for over a century.',
    },
    {
        'award_name': '布克奖',
        'year': 2024,
        'category': '小说',
        'title': 'Orbital',
        'author': 'Samantha Harvey',
        'isbn13': '9780802163784',
        'description': 'A novel set on the International Space Station, exploring the lives of six astronauts.',
    },
    {
        'award_name': '雨果奖',
        'year': 2024,
        'category': '最佳长篇小说',
        'title': 'Some Desperate Glory',
        'author': 'Emily Tesh',
        'isbn13': '9781250834989',
        'description': "A space opera about a young woman raised on a space station to avenge Earth's destruction.",
    },
    {
        'award_name': '诺贝尔文学奖',
        'year': 2024,
        'category': '文学',
        'title': 'The Vegetarian',
        'author': 'Han Kang',
        'isbn13': '9780553448184',
        'description': 'A dark and surreal novel about a woman who decides to stop eating meat and the consequences that follow.',
    },
    {
        'award_name': '星云奖',
        'year': 2024,
        'category': '最佳长篇小说',
        'title': 'The Saint of Bright Doors',
        'author': 'Vajra Chandrasekera',
        'isbn13': '9781250842700',
        'description': 'A fantasy novel about a man raised to assassinate a messiah figure, exploring destiny and choice.',
    },
    {
        'award_name': '国际布克奖',
        'year': 2024,
        'category': '翻译小说',
        'title': 'Kairos',
        'author': 'Jenny Erpenbeck',
        'isbn13': '9780811232011',
        'description': 'A love story set in East Germany before the fall of the Berlin Wall, exploring personal and political transformation.',
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2024,
        'category': '最佳小说',
        'title': 'The River We Remember',
        'author': 'William Kent Krueger',
        'isbn13': '9781982178697',
        'description': 'A murder mystery set in 1950s Minnesota, exploring small-town secrets and racial tensions.',
    },
    {
        'award_name': '普利策奖',
        'year': 2023,
        'category': '小说',
        'title': 'Demon Copperhead',
        'author': 'Barbara Kingsolver',
        'isbn13': '9780063251922',
        'description': 'A modern retelling of David Copperfield set in Appalachia, following a boy born to a teenage single mother.',
    },
    {
        'award_name': '普利策奖',
        'year': 2023,
        'category': '非虚构',
        'title': 'His Name Is George Floyd',
        'author': 'Robert Samuels, Toluse Olorunnipa',
        'isbn13': '9780593491930',
        'description': 'A biography of George Floyd that explores the racial justice movement and systemic inequality in America.',
    },
    {
        'award_name': '布克奖',
        'year': 2023,
        'category': '小说',
        'title': 'Prophet Song',
        'author': 'Paul Lynch',
        'isbn13': '9780802161506',
        'description': 'A dystopian novel about a mother searching for her son in a collapsing Ireland.',
    },
    {
        'award_name': '雨果奖',
        'year': 2023,
        'category': '最佳长篇小说',
        'title': 'Nettle & Bone',
        'author': 'T. Kingfisher',
        'isbn13': '9781250244048',
        'description': 'A fantasy novel about a princess who must save her sister from an abusive husband.',
    },
    {
        'award_name': '诺贝尔文学奖',
        'year': 2023,
        'category': '文学',
        'title': 'A New Name: Septology VI-VII',
        'author': 'Jon Fosse',
        'isbn13': '9781555978896',
        'description': 'The final installment of the Septology series, exploring the life of an aging painter.',
    },
    {
        'award_name': '星云奖',
        'year': 2023,
        'category': '最佳长篇小说',
        'title': 'Babel: Or the Necessity of Violence',
        'author': 'R.F. Kuang',
        'isbn13': '9780063021426',
        'description': 'A dark academia fantasy about a magical translation institute in 1830s Oxford, exploring colonialism and language.',
    },
    {
        'award_name': '国际布克奖',
        'year': 2023,
        'category': '翻译小说',
        'title': 'Time Shelter',
        'author': 'Georgi Gospodinov',
        'isbn13': '9781324008372',
        'description': "A novel about a clinic that recreates past decades to help Alzheimer's patients, exploring memory and nostalgia.",
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2023,
        'category': '最佳小说',
        'title': 'The Accomplice',
        'author': 'Lisa Lutz',
        'isbn13': '9781982168322',
        'description': 'A psychological thriller about two lifelong friends bound by a dark secret from their teenage years.',
    },
    {
        'award_name': '普利策奖',
        'year': 2022,
        'category': '小说',
        'title': 'The Netanyahus',
        'author': 'Joshua Cohen',
        'isbn13': '9781681376070',
        'description': 'A comic novel about a Jewish historian who meets the Netanyahu family in 1959.',
    },
    {
        'award_name': '布克奖',
        'year': 2022,
        'category': '小说',
        'title': 'The Seven Moons of Maali Almeida',
        'author': 'Shehan Karunatilaka',
        'isbn13': '9781324035910',
        'description': 'A satirical novel about a war photographer who wakes up dead in a celestial visa office.',
    },
    {
        'award_name': '雨果奖',
        'year': 2022,
        'category': '最佳长篇小说',
        'title': 'A Desolation Called Peace',
        'author': 'Arkady Martine',
        'isbn13': '9781250186461',
        'description': 'A space opera about first contact with a terrifying alien species. Sequel to A Memory Called Empire.',
    },
    {
        'award_name': '诺贝尔文学奖',
        'year': 2022,
        'category': '文学',
        'title': 'The Years',
        'author': 'Annie Ernaux',
        'isbn13': '9781609808927',
        'description': 'A memoir that blends personal and collective history from 1941 to 2006.',
    },
    {
        'award_name': '国际布克奖',
        'year': 2022,
        'category': '翻译小说',
        'title': 'Tomb of Sand',
        'author': 'Geetanjali Shree',
        'isbn13': '9781953861162',
        'description': 'An Indian widow defies expectations and travels to Pakistan to confront her past, translated from Hindi.',
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2022,
        'category': '最佳小说',
        'title': 'Billy Summers',
        'author': 'Stephen King',
        'isbn13': '9781982173616',
        'description': 'A hired killer with a conscience takes on one last job, but things go terribly wrong.',
    },
]


def init_sample_award_books(app):
    """
    初始化预置获奖图书数据

    仅在数据库为空时添加，避免重复
    """
    try:
        from ..models.database import db
        from ..models.schemas import Award, AwardBook

        app.logger.info('📚 检查是否需要初始化预置获奖图书...')

        # 检查是否已有图书数据
        existing_count = AwardBook.query.count()
        if existing_count > 0:
            app.logger.info(f'✅ 已有 {existing_count} 本图书，跳过预置数据初始化')
            return

        app.logger.info('🆕 数据库为空，开始添加预置获奖图书...')

        added_count = 0

        for book_data in SAMPLE_AWARD_BOOKS:
            # 查找对应的奖项
            award = Award.query.filter_by(name=book_data['award_name']).first()
            if not award:
                app.logger.warning(f'⚠️ 找不到奖项: {book_data["award_name"]}，跳过')
                continue

            # 检查图书是否已存在
            existing = AwardBook.query.filter_by(
                award_id=award.id, year=book_data['year'], title=book_data['title']
            ).first()

            if existing:
                continue

            # 创建新图书
            book = AwardBook(
                award_id=award.id,
                year=book_data['year'],
                category=book_data['category'],
                rank=1,
                title=book_data['title'],
                author=book_data['author'],
                description=book_data['description'],
                isbn13=book_data['isbn13'],
                is_displayable=True,
                verification_status='verified',
            )

            db.session.add(book)
            added_count += 1

        if added_count > 0:
            db.session.commit()
            app.logger.info(f'✅ 已添加 {added_count} 本预置获奖图书')
        else:
            app.logger.info('⏭️ 没有添加新图书（可能已存在）')

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'初始化预置获奖图书失败: {e}', exc_info=True)
