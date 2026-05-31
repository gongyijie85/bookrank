"""
预置获奖图书数据

用于 Render 等云平台部署时快速初始化，
避免首次部署时页面显示"暂无数据"。

数据来源: Wikipedia 交叉验证 (2026-05)
"""

import logging

from ..utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)


SAMPLE_AWARD_BOOKS = [
    # ==================== 2026 ====================
    {
        'award_name': '普利策奖',
        'year': 2026,
        'category': '小说',
        'title': 'Angel Down',
        'title_zh': '天使陨落',
        'author': 'Daniel Kraus',
        'isbn13': '9781668068458',
        'description': 'A World War I stream-of-consciousness novel about survival, supernatural wonders, and moral conflict on the battlefield.',
        'description_zh': '一部一战意识流小说，讲述战场上的生存、超自然奇观与道德冲突。',
    },
    {
        'award_name': '普利策奖',
        'year': 2026,
        'category': '非虚构 (获奖)',
        'title': 'There Is No Place for Us',
        'title_zh': '无处安身',
        'author': 'Brian Goldstone',
        'isbn13': '9780593237144',
        'description': 'A feat of reportage, analysis and storytelling focusing on the issues that have created a national crisis of family homelessness among the so-called working poor.',
        'description_zh': '聚焦美国家庭无家可归危机的深度报道与分析，揭示"在职穷人"群体的困境。',
    },
    {
        'award_name': '普利策奖',
        'year': 2026,
        'category': '非虚构 (入围)',
        'title': 'A Flower Traveled in My Blood',
        'title_zh': '血中流淌的花',
        'author': 'Haley Cohen Gilliland',
        'isbn13': '9781668017159',
        'description': 'A beautifully written and well-reported book on Argentina\'s Dirty War, told through the eyes of the mothers and grandmothers who sought the truth about their "disappeared" loved ones.',
        'description_zh': '关于阿根廷"肮脏战争"的深度报道，通过寻找"失踪"亲人的母亲和祖母们的眼睛，揭示政治镇压的真相。',
    },
    {
        'award_name': '普利策奖',
        'year': 2026,
        'category': '非虚构 (入围)',
        'title': 'Mother Emanuel',
        'title_zh': '以马内利教堂',
        'author': 'Kevin Sack',
        'isbn13': '9781524761301',
        'description': 'A sensitive exploration of a church massacre in Charleston, South Carolina, a rigorously researched story of faith, African American institutions, the legacy of slavery and what remains after devastating losses.',
        'description_zh': '对南卡罗来纳州查尔斯顿教堂枪击案的深度探索，讲述信仰、非裔美国人机构、奴隶制遗产与灾难后幸存的故事。',
    },
    {
        'award_name': '国际布克奖',
        'year': 2026,
        'category': '翻译小说',
        'title': 'Taiwan Travelogue',
        'title_zh': '台湾漫游录',
        'author': 'Yáng Shuāng-zǐ',
        'isbn13': '9781913505974',
        'description': 'A novel set in 1930s Japanese-colonized Taiwan, exploring food, culture, and identity. First Chinese-language work to win the International Booker Prize.',
        'description_zh': '一部设定在1930年代日治台湾的小说，探讨美食、文化与身份认同。首部获得国际布克奖的中文作品。',
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2026,
        'category': '最佳小说',
        'title': 'The Big Empty',
        'title_zh': '空城',
        'author': 'Robert Crais',
        'isbn13': '9780525535799',
        'description': 'A gripping mystery novel by the bestselling author of the Cole & Pike series.',
        'description_zh': '畅销书作家罗伯特·克莱斯的悬疑小说，Cole与Pike系列续作。',
    },
    # ==================== 2025 ====================
    {
        'award_name': '普利策奖',
        'year': 2025,
        'category': '小说',
        'title': 'James',
        'title_zh': '詹姆斯',
        'author': 'Percival Everett',
        'isbn13': '9780385550369',
        'description': 'A brilliant reimagining of Adventures of Huckleberry Finn from the perspective of Jim, the enslaved man.',
        'description_zh': '从黑奴吉姆的视角重构《哈克贝利·费恩历险记》，获2025年普利策小说奖。',
    },
    {
        'award_name': '布克奖',
        'year': 2025,
        'category': '小说',
        'title': 'Flesh',
        'title_zh': '肉体',
        'author': 'David Szalay',
        'isbn13': '9780224099790',
        'description': 'A novel by Canadian-Hungarian author David Szalay exploring masculinity and identity, winner of the 2025 Booker Prize.',
        'description_zh': '加拿大-匈牙利裔作家大卫·萨莱的小说，探讨男性气质与身份认同，获2025年布克奖。',
    },
    {
        'award_name': '雨果奖',
        'year': 2025,
        'category': '最佳长篇小说',
        'title': 'The Tainted Cup',
        'title_zh': '染杯',
        'author': 'Robert Jackson Bennett',
        'isbn13': '9781984820709',
        'description': 'A mystery fantasy novel featuring a Holmes-like detective in a world where magic is powered by parasitic infection.',
        'description_zh': '一部奇幻推理小说，在寄生虫感染驱动魔法的世界中，一位福尔摩斯式的侦探展开调查。',
    },
    {
        'award_name': '诺贝尔文学奖',
        'year': 2025,
        'category': '文学',
        'title': 'Satantango',
        'title_zh': '撒旦探戈',
        'author': 'László Krasznahorkai',
        'isbn13': '9780811219297',
        'description': 'A haunting novel set in a decaying Hungarian village. Representative work of László Krasznahorkai, winner of the 2025 Nobel Prize in Literature.',
        'description_zh': '以衰败的匈牙利村庄为背景的迷人小说。拉斯洛·卡撒兹纳霍凯的代表作，作者获2025年诺贝尔文学奖。',
    },
    {
        'award_name': '国际布克奖',
        'year': 2025,
        'category': '翻译小说',
        'title': 'Heart Lamp',
        'title_zh': '心灯',
        'author': 'Banu Mushtaq',
        'isbn13': '9781916751040',
        'description': 'A collection of 12 stories depicting the lives of marginalized Muslim women in southern India. First short story collection and first Kannada translation to win the International Booker Prize.',
        'description_zh': '12篇短篇小说集，描绘印度南部边缘化穆斯林女性的生活。首部获得国际布克奖的短篇小说集和卡纳达语翻译作品。',
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2025,
        'category': '最佳小说',
        'title': 'The In Crowd',
        'title_zh': '圈内人',
        'author': 'Charlotte Vassell',
        'isbn13': '9780385549516',
        'description': 'A mystery novel set among the British elite, exploring privilege and deception.',
        'description_zh': '一部设定在英国精英阶层的悬疑小说，探讨特权与欺骗。',
    },
    # ==================== 2024 ====================
    {
        'award_name': '普利策奖',
        'year': 2024,
        'category': '小说',
        'title': 'Night Watch',
        'title_zh': '夜巡',
        'author': 'Jayne Anne Phillips',
        'isbn13': '9780451493330',
        'description': 'A novel set in a West Virginia asylum after the Civil War, following a mother and daughter recovering from the trauma of war.',
        'description_zh': '以内战后西弗吉尼亚精神病院为背景，讲述一对母女从战争创伤中恢复的故事。获2024年普利策小说奖。',
    },
    {
        'award_name': '布克奖',
        'year': 2024,
        'category': '小说',
        'title': 'Orbital',
        'title_zh': '轨道',
        'author': 'Samantha Harvey',
        'isbn13': '9780802163784',
        'description': 'A novel set on the International Space Station, exploring the lives of six astronauts over a single day. First book set in space to win the Booker Prize.',
        'description_zh': '以国际空间站为背景，六名宇航员在一天中的生活与思考。首部以太空为背景的布克奖获奖作品。',
    },
    {
        'award_name': '雨果奖',
        'year': 2024,
        'category': '最佳长篇小说',
        'title': 'Some Desperate Glory',
        'title_zh': '绝望荣耀',
        'author': 'Emily Tesh',
        'isbn13': '9781250834989',
        'description': "A space opera about a young woman raised on a space station to avenge Earth's destruction, who must question everything she's been taught.",
        'description_zh': '一部太空歌剧，讲述在空间站长大的年轻女性为地球复仇的故事，她必须质疑所学的一切。',
    },
    {
        'award_name': '诺贝尔文学奖',
        'year': 2024,
        'category': '文学',
        'title': 'The Vegetarian',
        'title_zh': '素食者',
        'author': 'Han Kang',
        'isbn13': '9780553448184',
        'description': 'A dark and surreal novel about a woman who decides to stop eating meat and the violent consequences that follow. Representative work of Han Kang, winner of the 2024 Nobel Prize in Literature.',
        'description_zh': '一部黑暗而超现实的小说，讲述一位女性决定不再吃肉后引发的连锁反应。韩江的代表作，作者获2024年诺贝尔文学奖。',
    },
    {
        'award_name': '星云奖',
        'year': 2024,
        'category': '最佳长篇小说',
        'title': 'Someone You Can Build a Nest In',
        'title_zh': '可筑巢之人',
        'author': 'John Wiswell',
        'isbn13': '9780756418854',
        'description': 'A cozy horror fantasy about a shape-shifting monster who falls in love with a human woman and must protect her from her abusive family.',
        'description_zh': '一部温馨恐怖奇幻小说，讲述一个变形怪物爱上人类女性并保护她免受虐待家庭伤害的故事。',
    },
    {
        'award_name': '国际布克奖',
        'year': 2024,
        'category': '翻译小说',
        'title': 'Kairos',
        'title_zh': '凯洛斯',
        'author': 'Jenny Erpenbeck',
        'isbn13': '9780811232011',
        'description': 'A love story set in East Germany before the fall of the Berlin Wall, exploring personal and political transformation.',
        'description_zh': '以柏林墙倒塌前的东德为背景的爱情故事，探索个人与政治的转变。',
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2024,
        'category': '最佳小说',
        'title': 'Flags on the Bayou',
        'title_zh': '河湾之旗',
        'author': 'James Lee Burke',
        'isbn13': '9780802161697',
        'description': 'A historical thriller set in Civil War-era Louisiana, blending mystery, romance, and the brutal realities of the American South.',
        'description_zh': '以南北战争时期路易斯安那为背景的历史惊悚小说，融合悬疑、爱情与美国南方的残酷现实。',
    },
    # ==================== 2023 ====================
    {
        'award_name': '普利策奖',
        'year': 2023,
        'category': '小说',
        'title': 'Demon Copperhead',
        'title_zh': '恶魔铜斑蛇',
        'author': 'Barbara Kingsolver',
        'isbn13': '9780063251922',
        'description': 'A modern retelling of David Copperfield set in Appalachia, following a boy born to a teenage single mother in the opioid crisis.',
        'description_zh': '以阿巴拉契亚为背景的《大卫·科波菲尔》现代重述，讲述一个在阿片类药物危机中成长的男孩的故事。',
    },
    {
        'award_name': '普利策奖',
        'year': 2023,
        'category': '非虚构',
        'title': 'His Name Is George Floyd',
        'title_zh': '他的名字是乔治·弗洛伊德',
        'author': 'Robert Samuels, Toluse Olorunnipa',
        'isbn13': '9780593491930',
        'description': 'A biography of George Floyd that explores the racial justice movement and systemic inequality in America.',
        'description_zh': '乔治·弗洛伊德传记，探索美国种族正义运动与系统性不平等。',
    },
    {
        'award_name': '布克奖',
        'year': 2023,
        'category': '小说',
        'title': 'Prophet Song',
        'title_zh': '先知之歌',
        'author': 'Paul Lynch',
        'isbn13': '9780802161506',
        'description': 'A dystopian novel about a mother searching for her son in a collapsing Ireland under totalitarian rule.',
        'description_zh': '一部反乌托邦小说，讲述一位母亲在极权统治下崩溃的爱尔兰寻找儿子的故事。',
    },
    {
        'award_name': '雨果奖',
        'year': 2023,
        'category': '最佳长篇小说',
        'title': 'Nettle & Bone',
        'title_zh': '荨麻与骨',
        'author': 'T. Kingfisher',
        'isbn13': '9781250244048',
        'description': 'A dark fantasy about a princess who must save her sister from an abusive prince, with the help of a dust-witch and a bone dog.',
        'description_zh': '一部黑暗奇幻小说，讲述一位公主在尘巫师和骨犬的帮助下，拯救被虐待狂王子囚禁的姐姐的故事。',
    },
    {
        'award_name': '诺贝尔文学奖',
        'year': 2023,
        'category': '文学',
        'title': 'A New Name: Septology VI-VII',
        'title_zh': '新名字：七部曲 VI-VII',
        'author': 'Jon Fosse',
        'isbn13': '9781555978896',
        'description': 'The final installment of the Septology series, exploring the life of an aging painter. Representative work of Jon Fosse, winner of the 2023 Nobel Prize in Literature.',
        'description_zh': '七部曲系列的终章，探索一位年迈画家的生活。约翰·福瑟的代表作，作者获2023年诺贝尔文学奖。',
    },
    {
        'award_name': '星云奖',
        'year': 2023,
        'category': '最佳长篇小说',
        'title': 'The Saint of Bright Doors',
        'title_zh': '光明之门圣人',
        'author': 'Vajra Chandrasekera',
        'isbn13': '9781250842700',
        'description': 'A fantasy novel about a man raised to assassinate a messiah figure, exploring destiny, choice, and the nature of sainthood.',
        'description_zh': '一部奇幻小说，讲述一个被培养来刺杀弥赛亚人物的男人的故事，探索命运、选择与圣徒的本质。',
    },
    {
        'award_name': '国际布克奖',
        'year': 2023,
        'category': '翻译小说',
        'title': 'Time Shelter',
        'title_zh': '时间庇护所',
        'author': 'Georgi Gospodinov',
        'isbn13': '9781324008372',
        'description': "A novel about a clinic that recreates past decades to help Alzheimer's patients, exploring memory, nostalgia, and European identity.",
        'description_zh': '一部关于诊所重现过去年代以帮助阿尔茨海默症患者的小说，探索记忆、怀旧与欧洲身份。',
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2023,
        'category': '最佳小说',
        'title': 'Notes on an Execution',
        'title_zh': '行刑笔记',
        'author': 'Danya Kukafka',
        'isbn13': '9780063052734',
        'description': 'A psychological thriller about a serial killer on death row, told through the perspectives of the women who shaped his life.',
        'description_zh': '一部心理惊悚小说，通过塑造凶手人生的女性视角，讲述死囚连环杀手的故事。',
    },
    # ==================== 2022 ====================
    {
        'award_name': '普利策奖',
        'year': 2022,
        'category': '小说',
        'title': 'The Netanyahus',
        'title_zh': '内塔尼亚胡一家',
        'author': 'Joshua Cohen',
        'isbn13': '9781681376070',
        'description': 'A comic novel about a Jewish historian who meets the Netanyahu family in 1959 when the future Israeli prime minister\'s father applies for a teaching position.',
        'description_zh': '一部喜剧小说，讲述一位犹太历史学家在1959年遇见内塔尼亚胡一家的故事。',
    },
    {
        'award_name': '布克奖',
        'year': 2022,
        'category': '小说',
        'title': 'The Seven Moons of Maali Almeida',
        'title_zh': '马里·阿尔梅达的七月',
        'author': 'Shehan Karunatilaka',
        'isbn13': '9781324035910',
        'description': 'A satirical novel about a war photographer who wakes up dead in a celestial visa office and must discover who killed him.',
        'description_zh': '一部讽刺小说，讲述一位战地摄影师死后在天国签证处醒来，必须找出谁杀了他。',
    },
    {
        'award_name': '雨果奖',
        'year': 2022,
        'category': '最佳长篇小说',
        'title': 'A Desolation Called Peace',
        'title_zh': '名为和平的荒芜',
        'author': 'Arkady Martine',
        'isbn13': '9781250186461',
        'description': 'A space opera about first contact with a terrifying alien species. Sequel to A Memory Called Empire.',
        'description_zh': '一部关于与恐怖外星物种首次接触的太空歌剧。《名为帝国的记忆》的续作。',
    },
    {
        'award_name': '诺贝尔文学奖',
        'year': 2022,
        'category': '文学',
        'title': 'The Years',
        'title_zh': '岁月',
        'author': 'Annie Ernaux',
        'isbn13': '9781609808927',
        'description': 'A memoir that blends personal and collective history from 1941 to 2006. Representative work of Annie Ernaux, winner of the 2022 Nobel Prize in Literature.',
        'description_zh': '一部融合个人与集体历史的回忆录，跨越1941年至2006年。安妮·埃尔诺的代表作，作者获2022年诺贝尔文学奖。',
    },
    {
        'award_name': '星云奖',
        'year': 2022,
        'category': '最佳长篇小说',
        'title': 'Babel: Or the Necessity of Violence',
        'title_zh': '巴别塔：或暴力的必要性',
        'author': 'R.F. Kuang',
        'isbn13': '9780063021426',
        'description': 'A dark academia fantasy about a magical translation institute in 1830s Oxford, exploring colonialism, language, and revolution.',
        'description_zh': '一部黑暗学院风奇幻小说，以1830年代牛津的魔法翻译学院为背景，探索殖民主义、语言与革命。',
    },
    {
        'award_name': '国际布克奖',
        'year': 2022,
        'category': '翻译小说',
        'title': 'Tomb of Sand',
        'title_zh': '沙墓',
        'author': 'Geetanjali Shree',
        'isbn13': '9781953861162',
        'description': 'An 80-year-old Indian widow defies expectations and travels to Pakistan to confront her past, translated from Hindi.',
        'description_zh': '一位80岁印度寡妇打破常规，前往巴基斯坦面对过去。首部从印地语翻译获得国际布克奖的作品。',
    },
    {
        'award_name': '爱伦·坡奖',
        'year': 2022,
        'category': '最佳小说',
        'title': 'Five Decembers',
        'title_zh': '五个十二月',
        'author': 'James Kestrel',
        'isbn13': '9781789096118',
        'description': 'A hardboiled crime novel set during World War II, following a detective investigating a murder across the Pacific from Honolulu to Hong Kong.',
        'description_zh': '一部以二战为背景的硬汉派犯罪小说，侦探跨越太平洋从檀香山到香港追查一桩谋杀案。',
    },
]


def init_sample_award_books(app):
    """
    初始化预置获奖图书数据

    逐条检查 award_id + year + title 是否已存在，
    缺失的条目自动补种，避免重复插入。
    数据已通过 Wikipedia 交叉验证 (2026-05)。
    """
    try:
        from ..models.database import db
        from ..models.schemas import Award, AwardBook

        app.logger.info('📚 检查预置获奖图书完整性...')

        added_count = 0
        skipped_count = 0

        for book_data in SAMPLE_AWARD_BOOKS:
            # 查找对应的奖项
            award = Award.query.filter_by(name=book_data['award_name']).first()
            if not award:
                app.logger.warning(f'⚠️ 找不到奖项: {book_data["award_name"]}，跳过')
                continue

            # 检查图书是否已存在（按 award_id + year + title 去重）
            existing = AwardBook.query.filter_by(
                award_id=award.id, year=book_data['year'], title=book_data['title']
            ).first()

            if existing:
                # Update verification status and data for existing entries
                if existing.verification_status not in ('verified', 'wikidata'):
                    existing.verification_status = 'verified'
                existing.is_displayable = True
                # Update fields that may have been corrected
                if book_data.get('author') and existing.author != book_data['author']:
                    existing.author = book_data['author']
                if book_data.get('isbn13') and existing.isbn13 != book_data['isbn13']:
                    existing.isbn13 = book_data['isbn13']
                if book_data.get('description') and existing.description != book_data['description']:
                    existing.description = book_data['description']
                if book_data.get('description_zh') and existing.description_zh != book_data.get('description_zh'):
                    existing.description_zh = book_data.get('description_zh')
                if book_data.get('title_zh') and existing.title_zh != book_data.get('title_zh'):
                    existing.title_zh = book_data.get('title_zh')
                skipped_count += 1
                continue

            # 创建新图书
            book = AwardBook(
                award_id=award.id,
                year=book_data['year'],
                category=book_data['category'],
                rank=1,
                title=book_data['title'],
                title_zh=book_data.get('title_zh'),
                author=book_data['author'],
                description=book_data['description'],
                description_zh=book_data.get('description_zh'),
                isbn13=book_data['isbn13'],
                is_displayable=True,
                verification_status='verified',
            )

            db.session.add(book)
            added_count += 1

        # 清理旧错误条目：在同一年份+奖项下，标题不在种子数据中的条目标记为 deprecated
        cleaned_count = 0
        seed_titles_by_key: dict[tuple[int, int], set[str]] = {}
        for book_data in SAMPLE_AWARD_BOOKS:
            award = Award.query.filter_by(name=book_data['award_name']).first()
            if award:
                key = (award.id, book_data['year'])
                if key not in seed_titles_by_key:
                    seed_titles_by_key[key] = set()
                seed_titles_by_key[key].add(book_data['title'])

        for (award_id, year), valid_titles in seed_titles_by_key.items():
            stale = AwardBook.query.filter(
                AwardBook.award_id == award_id,
                AwardBook.year == year,
                AwardBook.title.notin_(valid_titles),
                AwardBook.verification_status != 'wikidata',  # 保留 Wikidata 来源数据
            ).all()
            for entry in stale:
                entry.is_displayable = False
                entry.verification_status = 'deprecated'
                cleaned_count += 1

        if added_count > 0 or skipped_count > 0 or cleaned_count > 0:
            db.session.commit()
            app.logger.info(
                f'✅ 已补种 {added_count} 本预置获奖图书，'
                f'跳过/更新 {skipped_count} 本已存在，'
                f'清理 {cleaned_count} 本旧错误条目'
            )
        else:
            app.logger.info('✅ 所有预置获奖图书已存在，无需补种')

    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'初始化预置获奖图书失败: {e}', exc_info=True)
