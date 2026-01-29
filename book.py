import pandas as pd

# 完整的图书数据（包含翻译）
data = [
    {
        "ISBN": "9780241529713",
        "书名": "Why Has Nobody Told Me this Before?",
        "英文介绍": "Give your mind the one thing it needs in 2024 with the book everyone is STILL talking about, from clinical psychologist and TikTok sensation Dr Julie Smith 'A brilliant book' Steven Bartlett, Diary of a CEO podcast 'Full of sound, helpful advice with life skills, from building confidence to managing stress' Sunday Times AS FEATURED IN THE OBSERVER, STYLIST, EVENING STANDARD, WOMEN'S HEALTH, MARIE CLAIRE AND GRAZIA ________ Drawing on years of experience as a clinical psychologist, online sensation Dr Julie Smith shares all the skills you need to get through life's ups and downs. Filled with secrets from a therapist's toolkit, this is a must-have handbook for optimising your mental health. Dr Julie's simple but expert advice and powerful coping techniques will help you stay resilient no matter what life throws your way. Written in short, bite-sized entries, you can turn straight to the section you need depending on the challenge you're facing - and immediately find the appropriate tools to help with . . . - Managing anxiety - Dealing with criticism - Battling low mood - Building self-confidence - Finding motivation - Learning to forgive yourself This book tackles the everyday issues that affect us all and offers easy, practical solutions that might just change your life. ________ 'Sound wisdom, easy to gulp down. I'm sure this book is already helping lots of people. Great work, Dr Julie' Matt Haig, bestselling author of Reasons To Stay Alive 'I'm blown away by her ability to communicate difficult ideas with ease, simplicity and practicality. Amazing. Go and buy it now!' Jay Shetty 'It's real, it's authentic . . . Very practical and very, very helpful' Lorraine Kelly 'Relatable, real and easy to digest . . . As if your wise best friend is chatting to you. An essential mental-health bible for adults and teenagers' YOU Magazine, Daily Mail 'If you want to feel like you have a therapist sitting across from you, empowering you with how to be your best self, this book is for you!' Nicole LePera, New York Times bestselling author of How to Do the Work Sunday Times bestseller, June 2024 Why Has Nobody Told Me This Before? has sold over one million copies across all formats, The Bookseller, January 2024",
        "中文介绍": "为你的心灵提供2024年所需的一切，这本来自临床心理学家和TikTok红人Julie Smith博士的书依然是大家热议的话题。Steven Bartlett在《CEO日记》播客中称其为“一本精彩的书”。《星期日泰晤士报》评价其“充满了关于生活技能的合理且有益的建议，从建立自信到管理压力”。本书曾在《观察家报》、《Stylist》、《标准晚报》、《女性健康》、《嘉人》和《红秀》中被推荐。________ 网络红人Julie Smith博士凭借多年的临床心理学家经验，分享了你度过人生起伏所需的所有技能。这就如同一个治疗师的工具箱，充满了秘密，是优化心理健康的必备手册。Julie博士简单而专业的建议以及强大的应对技巧将帮助你保持韧性，无论生活向你抛来什么。本书以简短的条目编写，你可以根据面临的挑战直接翻到所需的部分，并立即找到合适的工具来帮助处理…… - 管理焦虑 - 应对批评 - 对抗低落情绪 - 建立自信 - 寻找动力 - 学会原谅自己。这本书解决了影响我们所有人的日常问题，并提供了可能改变你生活的简单、实用的解决方案。________ “明智的智慧，易于消化。我相信这本书已经在帮助很多人了。干得好，Julie博士”——Matt Haig，《活下去的理由》畅销书作者。“她能够以轻松、简单和实用的方式传达困难的想法，这让我震惊。太棒了。现在就去买吧！”——Jay Shetty。“它是真实的，它是地道的……非常实用，非常有帮助”——Lorraine Kelly。“相关性强，真实且易于消化……就像你睿智的好朋友在和你聊天。成人和青少年的必备心理健康圣经”——YOU Magazine，《每日邮报》。“如果你想感觉像有一位治疗师坐在你对面，赋予你成为最好自己的力量，这本书就是为你准备的！”——Nicole LePera，《How to Do the Work》纽约时报畅销书作者。2024年6月《星期日泰晤士报》畅销书。根据The Bookseller 2024年1月的数据，《Why Has Nobody Told Me This Before?》所有格式的销量已超过一百万册。",
        "亚马逊链接": "https://www.amazon.com/dp/9780241529713"
    },
    {
        "ISBN": "9781472292155",
        "书名": "Atalanta",
        "英文介绍": "When a daughter is born to the King of Arcadia, she brings only disappointment. Left exposed on a mountainside, the defenceless infant Atalanta is left to the mercy of a passing mother bear and raised alongside the cubs under the protective eye of the goddess Artemis. Swearing that she will prove her worth alongside the famed heroes of Greece, Atalanta leaves her forest to join Jason's band of Argonauts. But can she carve out her own place in the legends in a world made for men?",
        "中文介绍": "当阿卡迪亚国王诞下一女时，带来的只有失望。无助的婴儿阿塔兰忒被遗弃在山坡上，听天由命，幸而被一只路过的母熊收养，并在女神阿耳忒弥斯的保护下与幼崽一起长大。阿塔兰忒发誓要与希腊著名的英雄们一起证明自己的价值，她离开森林加入了杰森的阿尔戈英雄队。但在一个为男人打造的世界里，她能在传奇中开辟出属于自己的一席之地吗？",
        "亚马逊链接": "https://www.amazon.com/dp/9781472292155"
    },
    {
        "ISBN": "9780099529934",
        "书名": "The Complete Sherlock Holmes",
        "英文介绍": "From The Adventure of the Gloria Scott to His Last Bow we follow the illustrious career of this quintessential British hero from his university days to his final case. Sherlock Holmes's efforts to uncover the truth take him all over the world and into conflict with all manner of devious criminals and dangerous villains, but thankfully his legendary powers of deduction and his faithful companion Dr. Watson are more than up to the challenge. Sir Arthur Conan Doyle (1859–1930) produced more than 30 books, 150 short stories, poems, plays and essays across a wide range of genres. His most famous creation is the detective Sherlock Holmes, who he introduced in his first novel A Study in Scarlet. P. D. James is an award-winning author whose titles include Death in Holy Orders, The Lighthouse, and The Murder Room.",
        "中文介绍": "从《格洛里亚斯科特号三桅帆船》到《最后致意》，我们要追随这位典型的英国英雄辉煌的职业生涯，从他的大学时代一直到他的最后一个案件。夏洛克·福尔摩斯揭露真相的努力将他带到了世界各地，并与各种狡猾的罪犯和危险的恶棍发生冲突，但值得庆幸的是，他传奇的演绎能力和他忠实的伙伴华生医生完全能够应对挑战。阿瑟·柯南·道尔爵士（1859-1930）创作了30多本书、150篇短篇小说、诗歌、戏剧和散文，涵盖了广泛的体裁。他最著名的创作是侦探夏洛克·福尔摩斯，他在第一部小说《血字的研究》中介绍了这个人物。P. D. James是一位屡获殊荣的作家，其作品包括《神职人员之死》、《灯塔》和《谋杀室》。",
        "亚马逊链接": "https://www.amazon.com/dp/9780099529934"
    },
    {
        "ISBN": "9780374608538",
        "书名": "Intermezzo",
        "英文介绍": "An exquisitely moving story about grief, love, and family, from the global phenomenon Sally Rooney. Aside from the fact that they are brothers, Peter and Ivan Koubek seem to have little in common. Peter is a Dublin lawyer in his thirties--successful, competent, and apparently unassailable. But in the wake of their father's death, he's medicating himself to sleep and struggling to manage his relationships with two very different women--his enduring first love, Sylvia, and Naomi, a college student for whom life is one long joke. Ivan is a twenty-two-year-old competitive chess player. He has always seen himself as socially awkward, a loner, the antithesis of his glib elder brother. Now, in the early weeks of his bereavement, Ivan meets Margaret, an older woman emerging from her own turbulent past, and their lives become rapidly and intensely intertwined. For two grieving brothers and the people they love, this is a new interlude--a period of desire, despair, and possibility; a chance to find out how much one life might hold inside itself without breaking.",
        "中文介绍": "这是一个关于悲伤、爱和家庭的动人故事，出自全球现象级作家萨利·鲁尼之手。除了是兄弟这一事实外，彼得·库贝克和伊万·库贝克似乎没有什么共同点。彼得是都柏林的一名三十多岁的律师——成功、能干，表面上无懈可击。但在父亲去世后，他靠药物入睡，并努力处理与两个截然不同的女人的关系——他持久的初恋西尔维亚，以及大学生娜奥米，对娜奥米来说生活就是一个漫长的玩笑。伊万是一名二十二岁的竞技棋手。他一直认为自己社交笨拙，是一个孤独的人，与其油嘴滑舌的哥哥截然相反。现在，在丧亲之痛的最初几周，伊万遇到了玛格丽特，一位刚从自己动荡的过去中走出来的年长女性，他们的生活迅速而紧密地交织在一起。对于这两个悲伤的兄弟和他们所爱的人来说，这是一个新的插曲——一段充满欲望、绝望和可能性的时期；一个发现生命在不破碎的情况下能承载多少东西的机会。",
        "亚马逊链接": "https://www.amazon.com/dp/9780374608538"
    },
    {
        "ISBN": "9780141442228",
        "书名": "Grimm Tales",
        "英文介绍": "In this book of classic fairy tales author Philip Pullman has chosen his fifty favourite stories from the Brothers Grimm, presenting them in a 'clear as water' retelling.",
        "中文介绍": "在这本经典童话书中，作者菲利普·普尔曼从格林兄弟的故事中挑选了他最喜欢的五十个故事，并以“清澈如水”的方式重新讲述了它们。",
        "亚马逊链接": "https://www.amazon.com/dp/9780141442228"
    },
    {
        "ISBN": "9781523515646",
        "书名": "There Are Moms Way Worse Than You",
        "英文介绍": "A rhyming illustrated humor book for moms who feel they're not doing a good job (and that's all moms, right?). Packed with scientifically true examples of terrible parents in the animal kingdom, to remind and reassure any mother that there are way worse moms out there.",
        "中文介绍": "这是一本押韵的插图幽默书，献给那些觉得自己做得不够好的妈妈们（其实所有妈妈都这么想，对吧？）。书中充满了动物界糟糕父母的科学真实案例，旨在提醒和安慰每一位母亲：外面的世界里还有比你糟糕得多的妈妈。",
        "亚马逊链接": "https://www.amazon.com/dp/9781523515646"
    },
    {
        "ISBN": "9781444715446",
        "书名": "You Are Here",
        "英文介绍": "The new novel by the author of One Day, now a major Netflix series... Marnie is stuck. Stuck working alone in her London flat... Michael is coming undone... When a persistent mutual friend and some very English weather conspire to bring them together, Marnie and Michael suddenly find themselves alone on the most epic of walks and on the precipice of a new friendship. But can they survive the journey? A new love story by beloved bestseller David Nicholls, You Are Here is a novel of first encounters, second chances and finding the way home...",
        "中文介绍": "这是《一天》（现已改编为Netflix热播剧）作者的新小说……Marnie陷入了困境。她独自在伦敦的公寓里工作，感觉生活正在离她而去。Michael正在崩溃。在妻子离开后，他变得越来越隐居，独自在荒原和丘陵上长途跋涉。当一位执着的共同朋友和典型的英国天气合谋将他们聚在一起时，Marnie和Michael突然发现他们独自踏上了一段史诗般的徒步之旅，处于一段新友谊的边缘。但他们能挺过这段旅程吗？这是深受喜爱的畅销书作家David Nicholls的全新爱情故事，《You Are Here》是一部关于初次相遇、第二次机会和寻找回家之路的小说。",
        "亚马逊链接": "https://www.amazon.com/dp/9781444715446"
    },
    {
        "ISBN": "9780063267916",
        "书名": "The Stranger in the Lifeboat",
        "英文介绍": "Adrift in a raft after a deadly ship explosion, nine people struggle for survival at sea. Three days pass. Short on water, food and hope, they spot a man floating in the waves and pull him in. The man, strange and quiet, claims to be the Lord. Is the man who he claims to be? What actually caused the explosion? Are the survivors already in heaven, or are they in hell? Years later, when the empty life raft washes up on the island of Montserrat-- the events recounted in a notebook-- it falls to the island's chief inspector to solve the mystery of what really happened. -- adapted from jacket",
        "中文介绍": "在一场致命的船舶爆炸后，九个人在救生筏上漂流，在海上挣扎求生。三天过去了。在缺水、缺粮且希望渺茫的情况下，他们发现一个人漂浮在波浪中并将他拉了上来。这个男人奇怪而安静，声称自己是主。这个男人真的是他声称的那个人吗？究竟是什么导致了爆炸？幸存者们是在天堂，还是在地狱？多年后，当空的救生筏被冲上蒙特塞拉特岛——笔记本中记录了这些事件——岛上的总探长不得不解开到底发生了什么的谜团。——改编自护封",
        "亚马逊链接": "https://www.amazon.com/dp/9780063267916"
    },
    {
        "ISBN": "9780008681036",
        "书名": "Maktub",
        "英文介绍": "An essential companion to the inspirational classic The Alchemist, filled with timeless stories of reflection and rediscovery.",
        "中文介绍": "励志经典《牧羊少年奇幻之旅》的重要伴读作品，充满了关于反思和重新发现的永恒故事。",
        "亚马逊链接": "https://www.amazon.com/dp/9780008681036"
    },
    {
        "ISBN": "9781368054966",
        "书名": "RunDisney",
        "英文介绍": "The first-ever official guidebook by RunDisney, the hugely popular road race division of The Walt Disney Company! With this comprehensive guide, readers will learn: The basics of running, while planning a most magical “runcation” to the Walt Disney World Resort or Disneyland. Which race is the best for themselves or their family. What gear is needed for a RunDisney event and what resources are available at the Disney parks...",
        "中文介绍": "这是华特迪士尼公司旗下极受欢迎的路跑部门RunDisney发布的首本官方指南！通过这本全面的指南，读者将学习：跑步的基础知识，同时规划前往华特迪士尼世界度假区或迪士尼乐园的最神奇的“跑步度假”。哪场比赛最适合自己或家人。参加RunDisney活动需要什么装备，以及迪士尼乐园提供哪些资源……",
        "亚马逊链接": "https://www.amazon.com/dp/9781368054966"
    },
    {
        "ISBN": "9780008467357",
        "书名": "Marple: Twelve New Stories",
        "英文介绍": "A brand new collection of short stories featuring the Queen of Crime's legendary detective Jane Marple, penned by twelve remarkable bestselling and acclaimed authors. This collection of twelve original short stories, all featuring Jane Marple, will introduce the character to a whole new generation...",
        "中文介绍": "这是全新的短篇小说集，以“犯罪女王”笔下的传奇侦探简·马普尔为主角，由十二位杰出的畅销书作家和广受好评的作者撰写。这本包含十二个原创短篇故事的集子，都以简·马普尔为主角，将把这个角色介绍给全新的一代读者……",
        "亚马逊链接": "https://www.amazon.com/dp/9780008467357"
    },
    {
        "ISBN": "9780008598174",
        "书名": "A Handheld History",
        "英文介绍": "A Handheld History is a unique celebration of portable platforms and their iconic games.",
        "中文介绍": "《掌机历史》是对便携式游戏平台及其标志性游戏的独特致敬。",
        "亚马逊链接": "https://www.amazon.com/dp/9780008598174"
    },
    {
        "ISBN": "9781526662156",
        "书名": "The Bone Season",
        "英文介绍": "THE TENTH ANNIVERSARY SPECIAL EDITION, FULLY UPDATED WITH NEW MATERIAL A lavishly reimagined tenth anniversary edition of the first novel in the sensational Bone Season series... Welcome to Scion. No safer place. The year is 2059... Paige Mahoney holds a high rank in the criminal underworld... Paige is a dreamwalker, a rare and formidable kind of clairvoyant. Under Scion law, she commits treason simply by breathing...",
        "中文介绍": "十周年特别版，包含新内容并全面更新。这是轰动一时的《骸骨季节》系列第一部小说的十周年豪华重制版……欢迎来到赛昂（Scion）。没有比这更安全的地方了。那是2059年……Paige Mahoney在黑社会中身居高位……Paige是一名“梦行者”，一种罕见而强大的千里眼。根据赛昂的法律，她仅仅是呼吸就构成了叛国罪……",
        "亚马逊链接": "https://www.amazon.com/dp/9781526662156"
    },
    {
        "ISBN": "9781408729465",
        "书名": "Too Late",
        "英文介绍": "The intense, gripping psychological suspense from the author of global smash-hit Verity[Bokinfo].",
        "中文介绍": "来自全球大热作品《Verity》作者的紧张、扣人心弦的心理悬疑小说。",
        "亚马逊链接": "https://www.amazon.com/dp/9781408729465"
    },
    {
        "ISBN": "9780261102378",
        "书名": "The Return of the King",
        "英文介绍": "Part three of the lord of the rings trillogy.",
        "中文介绍": "《指环王》三部曲的第三部。",
        "亚马逊链接": "https://www.amazon.com/dp/9780261102378"
    },
    {
        "ISBN": "9780007902392",
        "书名": "As You Like it",
        "英文介绍": "One of Shakespeare's greatest comedies, As You Like It is presented here with a new introduction and appendices by David Bevington.",
        "中文介绍": "《皆大欢喜》是莎士比亚最伟大的喜剧之一，本版附有David Bevington撰写的新序言和附录。",
        "亚马逊链接": "https://www.amazon.com/dp/9780007902392"
    },
    {
        "ISBN": "9780007934430",
        "书名": "The Taming of the Shrew",
        "英文介绍": "The beautiful Katherina has sworn never to accept the demands of any would-be husband. But when she is pursued by the wily Petruchio, it seems that she has finally met her match...",
        "中文介绍": "美丽的凯瑟琳娜发誓绝不接受任何准丈夫的要求。但当她被狡猾的彼特鲁乔追求时，似乎她终于遇到了对手。当他用假装的残忍来回应她刻薄的言语时，她开始理解自己泼妇行为的荒谬。",
        "亚马逊链接": "https://www.amazon.com/dp/9780007934430"
    },
    {
        "ISBN": "9780007447855",
        "书名": "A Storm of Swords",
        "英文介绍": "The third volume in George R.R. Martin's superb and highly acclaimed epic fantasy A Song of Ice and Fire continues the richest, most exotic and mesmerising saga since The Lord of the Rings.",
        "中文介绍": "乔治·R·R·马丁的史诗奇幻巨著《冰与火之歌》的第三卷，延续了自《指环王》以来最丰富、最具异国情调和最令人着迷的传奇故事。",
        "亚马逊链接": "https://www.amazon.com/dp/9780007447855"
    },
    {
        "ISBN": "9780007920730",
        "书名": "Just So Stories",
        "英文介绍": "HarperCollins is proud to present its incredible range of best-loved, essential classics. How did the leopard get its spots? Why do the tides ebb and flow? How did the elephant get its trunk? And how was the alphabet made? Rudyard Kipling's classic collection of fables answers the great questions of animal- and humankind in a fun, eloquent and magical way...",
        "中文介绍": "哈珀柯林斯自豪地推出其令人难以置信的最受喜爱、必读的经典系列。豹子是怎么得到斑点的？潮汐为什么会涨落？大象是怎么得到长鼻子的？字母表是如何创造的？鲁德亚德·吉卜林的经典寓言集以一种有趣、雄辩和神奇的方式回答了动物和人类的这些重大问题，适合儿童和成人阅读……",
        "亚马逊链接": "https://www.amazon.com/dp/9780007920730"
    },
    {
        "ISBN": "9780007447862",
        "书名": "A Feast for Crows",
        "英文介绍": "HBO's hit series A GAME OF THRONES is based on George R R Martin's internationally bestselling series A SONG OF ICE AND FIRE... A FEAST FOR CROWS is the fourth volume in the series... The Lannisters are in power on the Iron Throne. The war in the Seven Kingdoms has burned itself out, but in its bitter aftermath new conflicts spark to life...",
        "中文介绍": "HBO的热门剧集《权力的游戏》改编自乔治·R·R·马丁的国际畅销系列《冰与火之歌》……《群鸦的盛宴》是该系列的第四卷。兰尼斯特家族掌握了铁王座的权力。七大王国的战争已经平息，但在苦涩的余波中，新的冲突火花再次燃起……",
        "亚马逊链接": "https://www.amazon.com/dp/9780007447862"
    },
    {
        "ISBN": "9780261102361",
        "书名": "The Two Towers",
        "英文介绍": "Begin your journey into Middle-Earth. The inspiration for the upcoming original series on Prime Video... The second part of J.R.R. Tolkien's epic adventure THE LORD OF THE RINGS. The Fellowship is scattered. Some prepare for war against the Dark Lord... Only Frodo and Sam are left to take the accursed Ring to be destroyed in the fires of Mount Doom...",
        "中文介绍": "开启你的中土世界之旅。Prime Video即将推出的原创剧集的灵感来源……J.R.R.托尔金史诗冒险《指环王》的第二部。护戒远征队已经失散。一些人准备与黑魔王开战……只剩下弗罗多和山姆将受诅咒的戒指带到末日火山的火焰中销毁……",
        "亚马逊链接": "https://www.amazon.com/dp/9780261102361"
    },
    {
        "ISBN": "9780593593806",
        "书名": "Spare",
        "英文介绍": "#1 NEW YORK TIMES BESTSELLER • Discover the global phenomenon that tells an unforgettable story of love, loss, courage, and healing. ... It was one of the most searing images of the twentieth century: two young boys, two princes, walking behind their mother’s coffin... For Harry, this is that story at last... For the first time, Prince Harry tells his own story, chronicling his journey with raw, unflinching honesty. A landmark publication, Spare is full of insight, revelation, self-examination, and hard-won wisdom about the eternal power of love over grief.",
        "中文介绍": "纽约时报畅销书排行榜第一名 • 探索这个讲述爱、失去、勇气和治愈的难忘故事的全球现象级作品。……这是二十世纪最令人心痛的画面之一：两个小男孩，两位王子，走在母亲的灵柩后面……对于哈里来说，这终于就是那个故事……哈里王子首次讲述了自己的故事，以原始、毫不退缩的诚实记录了他的旅程。作为一部里程碑式的出版物，《备胎》充满了洞察力、启示、自我审视，以及关于爱战胜悲伤的永恒力量的来之不易的智慧。",
        "亚马逊链接": "https://www.amazon.com/dp/9780593593806"
    },
    {
        "ISBN": "9780007902309",
        "书名": "Collins Classics - Henry IV",
        "英文介绍": "This volume brings parts one and two of 'Henry IV' together, along with literary and historical contextual materials that illuminate the primary texts.",
        "中文介绍": "本卷汇集了《亨利四世》的第一部分和第二部分，以及阐明主要文本的文学和历史背景材料。",
        "亚马逊链接": "https://www.amazon.com/dp/9780007902309"
    },
    {
        "ISBN": "9780007925582",
        "书名": "Selected Short Stories",
        "英文介绍": "Poet, novelist, painter and musician, Rabindranath Tagore (1861-1941) is the grand master of Bengali culture. Written during the 1890s, the stories in this collection recreate vivid images of Bengali life and landscapes in their depiction of peasantry and gentry, casteism, corrupt officaldom and dehumanizing poverty.",
        "中文介绍": "诗人、小说家、画家和音乐家拉宾德拉纳特·泰戈尔（1861-1941）是孟加拉文化的宗师。这本集子里的故事写于1890年代，通过对农民和乡绅、种姓制度、腐败官僚和非人道贫困的描写，重现了孟加拉生活和风景的生动形象。",
        "亚马逊链接": "https://www.amazon.com/dp/9780007925582"
    },
    {
        "ISBN": "9780593539750",
        "书名": "Think of Me",
        "英文介绍": "From the New York Times bestselling author of We Must Be Brave comes a new sweeping historical novel about one couple’s journey through war, love, and loss, and how the people we love never really leave us... During the perils of World War II in Alexandria, Egypt, two people from different worlds will find their way back to each other time and time again... Decades later, and ten years after his wife’s death, James moves to the English village of Upton seeking change...",
        "中文介绍": "来自《We Must Be Brave》的纽约时报畅销书作者的新作，这是一部宏大的历史小说，讲述了一对夫妇经历战争、爱情和失去的旅程，以及我们所爱的人如何从未真正离开我们……在二战期间埃及亚历山大的危险中，两个来自不同世界的人将一次又一次地找到回到彼此身边的路……几十年后，在他妻子去世十年后，詹姆斯搬到英国的厄普顿村寻求改变……",
        "亚马逊链接": "https://www.amazon.com/dp/9780593539750"
    },
    {
        "ISBN": "9781534462540",
        "书名": "Bright",
        "英文介绍": "Now that Girls Forever is the number-one K-pop group in the world, Rachel Kim is famous and happy, but when she meets Alex she considers breaking the rules of fame to fall in love.",
        "中文介绍": "既然Girls Forever已经是世界第一的K-pop组合，Rachel Kim既出名又快乐，但当她遇到Alex时，她考虑打破成名的规则去坠入爱河。",
        "亚马逊链接": "https://www.amazon.com/dp/9781534462540"
    },
    {
        "ISBN": "9781984879868",
        "书名": "Will",
        "英文介绍": "暂无英文介绍",
        "中文介绍": "暂无英文介绍",
        "亚马逊链接": "https://www.amazon.com/dp/9781984879868"
    },
    {
        "ISBN": "9780008122300",
        "书名": "A Dance with Dragons: Part 1 Dreams and Dust",
        "英文介绍": "HBO's hit series A GAME OF THRONES is based on George R.R. Martin's internationally bestselling series... A DANCE WITH DRAGONS: DREAMS AND DUST is the first part of the fifth volume in the series... Tyrion Lannister, having killed his father, and wrongfully accused of killing his nephew... has escaped... Jon Snow has been elected Lord Commander of the Night's Watch... And in the east Daenerys Targaryen struggles to hold a city built on dreams and dust...",
        "中文介绍": "HBO热门剧集《权力的游戏》基于乔治·R·R·马丁的国际畅销系列改编……《魔龙的狂舞：尘与梦》是该系列第五卷的第一部分……提利昂·兰尼斯特杀死了他的父亲，并被错误地指控杀害了他的侄子……已经逃脱……琼恩·雪诺被选为守夜人总司令……而在东方，丹妮莉丝·坦格利安正努力守住一座建立在梦想与尘埃之上的城市……",
        "亚马逊链接": "https://www.amazon.com/dp/9780008122300"
    },
    {
        "ISBN": "9780062905277",
        "书名": "The Adventures of Pinocchio (MinaLima Edition)",
        "英文介绍": "Pinocchio, a wooden puppet full of tricks and mischief, with a talent for getting into trouble, wants more than anything else to become a real boy.",
        "中文介绍": "匹诺曹，一个充满诡计和恶作剧、擅长惹麻烦的木偶，比任何事情都更想成为一个真正的男孩。",
        "亚马逊链接": "https://www.amazon.com/dp/9780062905277"
    },
    {
        "ISBN": "9781472292902",
        "书名": "COMPLETE SHERLOCK HOLMES.",
        "英文介绍": "暂无英文介绍",
        "中文介绍": "暂无英文介绍",
        "亚马逊链接": "https://www.amazon.com/dp/9781472292902"
    },
    {
        "ISBN": "9780747578956",
        "书名": "Desertion",
        "英文介绍": "From the highly acclaimed author of By the Sea.",
        "中文介绍": "出自备受赞誉的《海边》作者之手。",
        "亚马逊链接": "https://www.amazon.com/dp/9780747578956"
    },
    {
        "ISBN": "9781524759117",
        "书名": "Roses",
        "英文介绍": "This gorgeous box of postcards features 100 different roses from The New York Botanical Garden's extensive archives. This elegant, 100-postcard box features beautiful illustrations of roses, the flower world's most iconic bloom...",
        "中文介绍": "这一精美的明信片盒精选了来自纽约植物园丰富档案中的100种不同的玫瑰。这个优雅的100张明信片盒展示了玫瑰的美丽插图，这是花卉界最具标志性的花朵……",
        "亚马逊链接": "https://www.amazon.com/dp/9781524759117"
    },
    {
        "ISBN": "9780241444528",
        "书名": "The Happy Reader - Issue 15",
        "英文介绍": "For avid readers and the uninitiated alike, this is a chance to reengage with classic literature and to stay inspired and entertained. The concept of the magazine is simple: the first half is a long-form interview with a notable book fanatic and the second half explores one classic work of literature from an array of surprising and invigorating angles.",
        "中文介绍": "对于狂热的读者和门外汉来说，这是一个重新接触经典文学并保持灵感和娱乐的机会。这本杂志的概念很简单：前半部分是对一位著名书迷的长篇采访，后半部分则从各种令人惊讶和振奋的角度探索一部经典文学作品。",
        "亚马逊链接": "https://www.amazon.com/dp/9780241444528"
    },
    {
        "ISBN": "9781408881309",
        "书名": "未找到元数据",
        "英文介绍": "Google Books 无记录",
        "中文介绍": "Google Books 无记录",
        "亚马逊链接": "https://www.amazon.com/dp/9781408881309"
    },
    {
        "ISBN": "9781529342055",
        "书名": "The Master",
        "英文介绍": "A major biography of the greatest men's tennis player of the modern era. Widely regarded as one of the greatest ever sportspeople, Roger Federer is a global phenomenon... The Master is the definitive biography of a global icon who is both beloved and yet intensely private... With access to Federer's inner circle... legendary sports reporter Chris Clarey's account will be a must read retrospective...",
        "中文介绍": "这是关于现代最伟大的男子网球运动员的一部重要传记。罗杰·费德勒被广泛认为是有史以来最伟大的运动员之一，是一个全球现象……《大师》是这位既受人爱戴又极度注重隐私的全球偶像的权威传记……传奇体育记者Chris Clarey凭借对费德勒核心圈子的采访……他的叙述将是一本必读的回顾录……",
        "亚马逊链接": "https://www.amazon.com/dp/9781529342055"
    },
    {
        "ISBN": "9780593420768",
        "书名": "Burn After Writing (Floral)",
        "英文介绍": "The national bestseller. Write. Burn. Repeat. Now with new covers to match whatever mood you’re in... Burn After Writing allows you to spend less time scrolling and more time self-reflecting... This is not a diary, and there is no posting required. And when you're finished, toss it, hide it, or Burn After Writing.",
        "中文介绍": "全国畅销书。书写。焚烧。重复。现在有了新封面来匹配你的任何心情……《写后即焚》让你花更少的时间刷屏，更多的时间进行自我反思……这不是日记，也不需要发布。当你写完后，扔掉它，藏起来，或者写后即焚。",
        "亚马逊链接": "https://www.amazon.com/dp/9780593420768"
    },
    {
        "ISBN": "9780593189689",
        "书名": "Burn After Writing (Celestial)",
        "英文介绍": "The national bestseller. Write. Burn. Repeat. Now with new covers to match whatever mood you’re in... Burn After Writing allows you to spend less time scrolling and more time self-reflecting... This is not a diary, and there is no posting required. And when you're finished, toss it, hide it, or Burn After Writing.",
        "中文介绍": "全国畅销书。书写。焚烧。重复。现在有了新封面来匹配你的任何心情……《写后即焚》让你花更少的时间刷屏，更多的时间进行自我反思……这不是日记，也不需要发布。当你写完后，扔掉它，藏起来，或者写后即焚。",
        "亚马逊链接": "https://www.amazon.com/dp/9780593189689"
    },
    {
        "ISBN": "9780593420638",
        "书名": "Burn After Writing (Coral)",
        "英文介绍": "The national bestseller. Write. Burn. Repeat. Now with new covers to match whatever mood you’re in... Burn After Writing allows you to spend less time scrolling and more time self-reflecting... This is not a diary, and there is no posting required. And when you're finished, toss it, hide it, or Burn After Writing.",
        "中文介绍": "全国畅销书。书写。焚烧。重复。现在有了新封面来匹配你的任何心情……《写后即焚》让你花更少的时间刷屏，更多的时间进行自我反思……这不是日记，也不需要发布。当你写完后，扔掉它，藏起来，或者写后即焚。",
        "亚马逊链接": "https://www.amazon.com/dp/9780593420638"
    },
    {
        "ISBN": "9780593420621",
        "书名": "Burn After Writing (Gray)",
        "英文介绍": "The national bestseller. Write. Burn. Repeat. Now with new covers to match whatever mood you’re in... Burn After Writing allows you to spend less time scrolling and more time self-reflecting... This is not a diary, and there is no posting required. And when you're finished, toss it, hide it, or Burn After Writing.",
        "中文介绍": "全国畅销书。书写。焚烧。重复。现在有了新封面来匹配你的任何心情……《写后即焚》让你花更少的时间刷屏，更多的时间进行自我反思……这不是日记，也不需要发布。当你写完后，扔掉它，藏起来，或者写后即焚。",
        "亚马逊链接": "https://www.amazon.com/dp/9780593420621"
    },
    {
        "ISBN": "9780593189672",
        "书名": "Burn After Writing (Yellow)",
        "英文介绍": "The national bestseller. Write. Burn. Repeat. Now with new covers to match whatever mood you’re in... Burn After Writing allows you to spend less time scrolling and more time self-reflecting... This is not a diary, and there is no posting required. And when you're finished, toss it, hide it, or Burn After Writing.",
        "中文介绍": "全国畅销书。书写。焚烧。重复。现在有了新封面来匹配你的任何心情……《写后即焚》让你花更少的时间刷屏，更多的时间进行自我反思……这不是日记，也不需要发布。当你写完后，扔掉它，藏起来，或者写后即焚。",
        "亚马逊链接": "https://www.amazon.com/dp/9780593189672"
    },
    {
        "ISBN": "9780593329917",
        "书名": "Burn After Writing (Pink)",
        "英文介绍": "The national bestseller. Write. Burn. Repeat. Now with new covers to match whatever mood you’re in... Burn After Writing allows you to spend less time scrolling and more time self-reflecting... This is not a diary, and there is no posting required. And when you're finished, toss it, hide it, or Burn After Writing.",
        "中文介绍": "全国畅销书。书写。焚烧。重复。现在有了新封面来匹配你的任何心情……《写后即焚》让你花更少的时间刷屏，更多的时间进行自我反思……这不是日记，也不需要发布。当你写完后，扔掉它，藏起来，或者写后即焚。",
        "亚马逊链接": "https://www.amazon.com/dp/9780593329917"
    },
    {
        "ISBN": "9781302924980",
        "书名": "Conan: Exodus and Other Tales",
        "英文介绍": "Collects Conan the Barbarian: Exodus (2019) #1, Savage Sword of Conan (2019) #12, King-Size Conan (2020) #1. Celebrate 50 years of Conan comics with all-new tales by blockbuster creators! First, Esad Ribić delivers the never-before-told story of Conan's first journey from Cimmeria... Then, Frank Tieri and Andrea Di Vito send Conan on a hunt for a demonic sect in Argos... And legendary Conan scribe Roy Thomas joins an army of top-tier talent...",
        "中文介绍": "收录了《野蛮人柯南：出埃及记》(2019) #1、《野蛮人柯南的野蛮之剑》(2019) #12、《特大号柯南》(2020) #1。由大片创作者带来的全新故事，庆祝柯南漫画50周年！首先，Esad Ribić讲述了柯南从辛梅里亚出发的第一次旅程，这是前所未有的故事……然后，Frank Tieri和Andrea Di Vito让柯南在阿戈斯追捕一个恶魔教派……传奇柯南作家Roy Thomas加入了一群顶级天才的行列……",
        "亚马逊链接": "https://www.amazon.com/dp/9781302924980"
    },
    {
        "ISBN": "9781510766488",
        "书名": "Maradona",
        "英文介绍": "“Sometimes I think that my whole life is on film, that my whole life is in print. But it’s not like that. There are things which are only in my heart—that no one knows. At last I have decided to tell everything.” —Diego Maradona Diego Maradona went from a poor boy in a Buenos Aires shanty town to a genius with the soccer ball... He is one of many famous soccer players, but one of only a few to write their own soccer autobiography... From his poverty-stricken origins to his greatest successes on the field, Maradona remembers, with frankness and insight, the most impactful moments of his life... With a new epilogue that updates Maradona’s amazing story and includes over 80 delightful photographs, Maradona is a confessional, a revelation, an apology, and a celebration.",
        "中文介绍": "“有时我觉得我的一生都在胶卷上，我的一生都在印刷品上。但事实并非如此。有些事情只在我的心里——没人知道。终于，我决定说出一切。”——迭戈·马拉多纳。迭戈·马拉多纳从布宜诺斯艾利斯贫民窟的穷孩子变成了足球天才……他是众多著名足球运动员之一，但却是少数几个亲自撰写足球自传的人之一……从贫困的出身到球场上最伟大的成功，马拉多纳以坦率和洞察力回忆了他一生中最具影响力的时刻……加上一个新的尾声，更新了马拉多纳的惊人故事，并收录了80多张珍贵的照片，《马拉多纳》是一次忏悔、一次启示、一次道歉，也是一次庆祝。",
        "亚马逊链接": "https://www.amazon.com/dp/9781510766488"
    },
    {
        "ISBN": "9780374911034",
        "书名": "Jack",
        "英文介绍": "Marilynne Robinson, winner of the Pulitzer Prize and the National Humanities Medal, returns to the world of Gilead with Jack, the latest novel in one of the great works of contemporary American fiction Jack tells the story of John Ames Boughton, the beloved, erratic, and grieved-over prodigal son of a Presbyterian minister in Gilead, Iowa. In segregated St. Louis sometime after World War II, Jack falls in love with Della Miles, an African American high school teacher who is also the daughter of a preacher... Their fraught, beautiful romance is one of Robinson's greatest achievements...",
        "中文介绍": "普利策奖和国家人文奖章获得者玛丽莲·罗宾逊凭借《杰克》回到了基列的世界，这是当代美国小说杰作之一的最新小说。《杰克》讲述了约翰·艾姆斯·鲍顿的故事，他是爱荷华州基列一位长老会牧师的那个受人喜爱、反复无常且令人悲伤的浪子。在二战后种族隔离的圣路易斯，杰克爱上了黛拉·迈尔斯，一位非裔美国高中教师，同时也是一位传教士的女儿……他们充满忧虑而美丽的罗曼史是罗宾逊最伟大的成就之一……",
        "亚马逊链接": "https://www.amazon.com/dp/9780374911034"
    },
    {
        "ISBN": "9780143129769",
        "书名": "Touched by God",
        "英文介绍": "The story of the most remarkable--and controversial--World Cup triumph in history, told in a long-awaited firsthand account from Diego Maradona, its most legendary player. \"This is Diego Armando Maradona speaking, the man who scored two goals against England and one of the few Argentines who knows how much the World Cup actually weighs\"... Now, thirty years after Argentina's magical victory, Maradona tells his side of the story, vividly recounting how he led the team to win one of the greatest World Cup triumphs of all time.",
        "中文介绍": "历史上最非凡——也最具争议——的世界杯胜利的故事，由其最具传奇色彩的球员迭戈·马拉多纳在期待已久的第一手叙述中讲述。“我是迭戈·阿曼多·马拉多纳，那个对英格兰攻入两球的人，也是少数几个知道大力神杯到底有多重的阿根廷人之一”……现在，在阿根廷神奇夺冠三十年后，马拉多纳讲述了他这一边的故事，生动地回忆了他如何带领球队赢得史上最伟大的世界杯胜利之一。",
        "亚马逊链接": "https://www.amazon.com/dp/9780143129769"
    },
    {
        "ISBN": "9780593356340",
        "书名": "Ready Player Two",
        "英文介绍": "暂无英文介绍",
        "中文介绍": "暂无英文介绍",
        "亚马逊链接": "https://www.amazon.com/dp/9780593356340"
    },
    {
        "ISBN": "9781838660314",
        "书名": "Supreme",
        "英文介绍": "Over the past 25 years, Supreme has transformed itself from a downtown New York skate shop into an iconic global brand. Supreme-the book-looks back on more than two decades of the creations, stories, and convention-defying attitude that are uniquely Supreme... Featuring more than 800 stunning images... The book also features a curated section of lookbooks... Beautifully produced, the book is the epitome of Supreme's dedication to quality and design, including a reversible jacket with the signature red Supreme logo.",
        "中文介绍": "在过去的25年里，Supreme已经从纽约市中心的一家滑板店转变为一个标志性的全球品牌。《Supreme》（本书）回顾了二十多年来独特的Supreme创作、故事和打破常规的态度……收录了800多张令人惊叹的图片……本书还特别收录了精选的Lookbook……本书制作精美，是Supreme致力于质量和设计的缩影，包括带有标志性红色Supreme标志的双面护封。",
        "亚马逊链接": "https://www.amazon.com/dp/9781838660314"
    },
    {
        "ISBN": "9781534462519",
        "书名": "Shine",
        "英文介绍": "An instant New York Times bestseller! Crazy Rich Asians meets Gossip Girl by way of Jenny Han in this knock-out debut about a Korean American teen who is thrust into the competitive, technicolor world of K-pop, from Jessica Jung, K-pop legend and former lead singer of one of the most influential K-pop girl groups of all time, Girls’ Generation... Get ready as Jessica Jung... takes us inside the luxe, hyper-color world of K-pop, where the stakes are high, but for one girl, the cost of success—and love—might be even higher. It’s time for the world to see: this is what it takes to SHINE.",
        "中文介绍": "即时荣登《纽约时报》畅销书榜！这部令人惊叹的处女作像是《摘金奇缘》遇上《绯闻女孩》，由K-pop传奇人物、史上最具影响力的K-pop女团之一少女时代的前主唱Jessica Jung（郑秀妍）创作，讲述了一位韩裔美籍少女闯入竞争激烈、色彩斑斓的K-pop世界的故事……准备好，Jessica Jung带我们走进奢华、超色彩的K-pop世界，那里的赌注很高，但对一个女孩来说，成功——和爱情——的代价可能更高。是时候让世界看到了：这就是《SHINE》所需的代价。",
        "亚马逊链接": "https://www.amazon.com/dp/9781534462519"
    },
    {
        "ISBN": "9780349003634",
        "书名": "Butterfly",
        "英文介绍": "It's here! Number one bestselling author Stephenie Meyer makes a triumphant return to the world of Twilight with this highly-anticipated companion; the iconic love story of Bella and Edward told from the vampire's point of view. When Edward Cullen and Bella Swan met in Twilight, an iconic love story was born. But until now, fans have heard only Bella's side of the story. At last, readers can experience Edward's version in the long-awaited companion novel, MIDNIGHT SUN... In MIDNIGHT SUN, Stephenie Meyer transports us back to a world that has captivated millions of readers and brings us an epic novel about the profound pleasures and devastating consequences of immortal love.",
        "中文介绍": "它来了！排名第一的畅销书作家斯蒂芬妮·梅尔凭借这本备受期待的伴读作品凯旋回归《暮光之城》的世界；从吸血鬼的视角讲述贝拉和爱德华的标志性爱情故事。当爱德华·库伦和贝拉·斯旺在《暮光之城》中相遇时，一个标志性的爱情故事诞生了。但直到现在，粉丝们只听到了贝拉这边的故事。终于，读者可以在这本期待已久的伴读小说《午夜阳光》中体验爱德华的版本……在《午夜阳光》中，斯蒂芬妮·梅尔带我们回到那个迷住了数百万读者的世界，并为我们带来了一部关于不朽爱情的深刻快乐和毁灭性后果的史诗小说。",
        "亚马逊链接": "https://www.amazon.com/dp/9780349003634"
    },
    {
        "ISBN": "9781787630475",
        "书名": "The Ride of a Lifetime",
        "英文介绍": "The CEO of Disney, one of Time's most influential people of 2019, shares the ideas and values he embraced to reinvent one of the most beloved companies in the world and inspire the people who bring the magic to life -- Editor.",
        "中文介绍": "迪士尼CEO，2019年《时代》杂志最具影响力人物之一，分享了他为重塑世界上最受喜爱的公司之一并激励那些将魔法带入生活的人们所拥抱的理念和价值观——编辑。",
        "亚马逊链接": "https://www.amazon.com/dp/9781787630475"
    },
    {
        "ISBN": "9780805209495",
        "书名": "Letters to Friends, Family, and Editors",
        "英文介绍": "Collected after his death by his friend and literary executor Max Brod, here are more than two decades’ worth of Franz Kafka’s letters to the men and women with whom he maintained his closest personal relationships... Sometimes surprisingly humorous, sometimes wrenchingly sad, they include charming notes to school friends; fascinating accounts to Brod about his work... and heartbreaking reports to his parents, sisters, and friends on the declining state of his health in the last months of his life.",
        "中文介绍": "由他的朋友兼文学执行人马克思·布罗德在他去世后收集，这里汇集了弗兰茨·卡夫卡二十多年来写给他保持最亲密私人关系的男女的信件……有时令人惊讶地幽默，有时令人痛苦地悲伤，其中包括给校友的迷人便条；给布罗德关于他工作的迷人叙述……以及在他生命的最后几个月里，给父母、姐妹和朋友关于他健康状况恶化的令人心碎的报告。",
        "亚马逊链接": "https://www.amazon.com/dp/9780805209495"
    },
    {
        "ISBN": "9780805208511",
        "书名": "Letters to Felice",
        "英文介绍": "Kafka's five-year correspondence with the woman he claimed to love reveals much about his complex personality and his literary life.",
        "中文介绍": "卡夫卡与他声称深爱的女人之间为期五年的通信，揭示了他复杂的个性和文学生活。",
        "亚马逊链接": "https://www.amazon.com/dp/9780805208511"
    },
    {
        "ISBN": "9780241359907",
        "书名": "The Jungle Book",
        "英文介绍": "A classic story of friendship between man and beast. Saved from the jaws of the evil tiger Shere Khan, young Mowgli is adopted by a wolf pack and taught the law of the jungle by lovable old Baloo the bear and Bhageera the panther... This special Puffin Classics edition brings together two of the most inspirational collections at the Victoria and Albert Museum, London - the works of Arts and Crafts pioneer William Morris and the literature of Rudyard Kipling. Illustrator Liz Catchpole has selected patterns from the V&A archive and introduced new artwork inspired by the collection to create a beautiful cover which brings Ruddyard Kipling's timeless story to life.",
        "中文介绍": "一个关于人与野兽友谊的经典故事。小毛克利从邪恶老虎谢尔汗的口中获救，被狼群收养，并由可爱的老熊巴鲁和黑豹巴希拉教导丛林法则……这个特别的Puffin Classics版本汇集了伦敦维多利亚和阿尔伯特博物馆（V&A）两个最令人鼓舞的收藏——工艺美术先驱威廉·莫里斯的作品和鲁德亚德·吉卜林的文学作品。插画家Liz Catchpole从V&A档案中选择了图案，并引入了受该系列启发的新艺术作品，创造了一个美丽的封面，使鲁德亚德·吉卜林的永恒故事栩栩如生。",
        "亚马逊链接": "https://www.amazon.com/dp/9780241359907"
    },
    {
        "ISBN": "9780141977997",
        "书名": "Henry III (Penguin Monarchs)",
        "英文介绍": "Henry III was a medieval king whose long reign continues to have a profound impact on us today. He was on the throne for 56 years... Despite Henry's central importance for the birth of parliament... it is Henry's most vociferous opponent, Simon de Montfort, who is in many ways more famous than the monarch himself. Henry is principally known today as the driving force behind the building of Westminster Abbey, but he deserves to be better understood for many reasons... Part of the Penguin Monarchs series: short, fresh, expert accounts of England's rulers in a highly collectible format",
        "中文介绍": "亨利三世是一位中世纪国王，他的长期统治至今仍对我们产生深远影响。他在位56年……尽管亨利对议会的诞生至关重要……但在许多方面，亨利最激烈的对手西蒙·德·蒙特福特比君主本人更出名。亨利今天主要被认为是威斯敏斯特教堂建设的推动者，但他值得被更好地理解，原因有很多……属于企鹅君主系列：以极具收藏价值的格式，对英国统治者进行简短、新鲜、专业的叙述。",
        "亚马逊链接": "https://www.amazon.com/dp/9780141977997"
    },
    {
        "ISBN": "9781250147608",
        "书名": "Me",
        "英文介绍": "INSTANT #1 NEW YORK TIMES BESTSELLER In his first and only official autobiography, music icon Elton John reveals the truth about his extraordinary life, from his rollercoaster lifestyle as shown in the film Rocketman, to becoming a living legend... In Me, Elton also writes powerfully about getting clean and changing his life, about finding love with David Furnish and becoming a father. In a voice that is warm, humble, and open, this is Elton on his music and his relationships, his passions and his mistakes. This is a story that will stay with you by a living legend.",
        "中文介绍": "即时荣登《纽约时报》畅销书榜首。在他的第一本也是唯一一本官方自传中，音乐偶像埃尔顿·约翰揭示了他非凡生活的真相，从电影《火箭人》中展示的过山车般的生活方式，到成为一个活着的传奇……在《Me》中，埃尔顿还有力地描写了戒毒和改变生活，关于与大卫·弗尼什找到爱情并成为父亲。用温暖、谦逊和开放的声音，这是埃尔顿关于他的音乐和关系、他的激情和错误的自述。这是一个由活着的传奇讲述的、将伴随你左右的故事。",
        "亚马逊链接": "https://www.amazon.com/dp/9781250147608"
    },
    {
        "ISBN": "9780062888464",
        "书名": "Untitled",
        "英文介绍": "暂无英文介绍",
        "中文介绍": "暂无英文介绍",
        "亚马逊链接": "https://www.amazon.com/dp/9780062888464"
    },
    {
        "ISBN": "9780141398877",
        "书名": "Little Black Classics Box Set",
        "英文介绍": "A stunning collection of all 80 exquisite Little Black Classics from Penguin This spectacular box set of the 80 books in the Little Black Classics series showcases the many wonderful and varied writers in Penguin Black Classics... The Little Black Classics Box Set includes: - The Atheist's Mass (Honoré de Balzac) - The Beautifull Cassandra (Jane Austen)... [List of titles]... - The Yellow Wall-paper (Charlotte Perkins Gilman) - Wailing Ghosts (Pu Songling) - Well, they are gone, and here must I remain (Samuel Taylor Coleridge)",
        "中文介绍": "企鹅出版社所有80本精致的“小黑书经典”系列的惊人合集。这个壮观的套装展示了企鹅黑色经典中许多精彩多样的作家……小黑书经典套装包括：-《无神论者的弥撒》（巴尔扎克） -《美丽的卡桑德拉》（简·奥斯汀）……[书名列表]…… -《黄墙纸》（夏洛特·帕金斯·吉尔曼） -《鬼哭》（蒲松龄） -《好吧，他们走了，我必须留在这里》（塞缪尔·泰勒·柯勒律治）",
        "亚马逊链接": "https://www.amazon.com/dp/9780141398877"
    },
    {
        "ISBN": "9780062428936",
        "书名": "American Gods + Anansi Boys",
        "英文介绍": "The bestselling author of Neverwhere returns with his biggest, most commercial novel yet—a tour de force of contemporary fiction... Now in American Gods, he works his literary magic to extraordinary results. Shadow dreamed of nothing but leaving prison and starting a new life. But the day before his release, his wife and best friend are killed in an accident. On the plane home to the funeral, he meets Mr. Wednesday—a beguiling stranger who seems to know everything about him... For beneath the placid surface of everyday life a war is being fought —and the prize is the very soul of America.",
        "中文介绍": "《乌有乡》的畅销书作者带着他迄今为止最大、最商业化的小说回归——当代小说的杰作……现在在《美国众神》中，他施展文学魔法，取得了非凡的成果。影子的梦想只是离开监狱，开始新生活。但在他获释的前一天，他的妻子和最好的朋友在一次事故中丧生。在回家的飞机上，他遇到了星期三先生——一个迷人的陌生人，似乎对他的一切了如指掌……因为在日常生活的平静表面之下，一场战争正在进行——而战利品正是美国的灵魂。",
        "亚马逊链接": "https://www.amazon.com/dp/9780062428936"
    },
    {
        "ISBN": "9780062797032",
        "书名": "Illustrated Classics Boxed Set",
        "英文介绍": "Synopsis coming soon.......",
        "中文介绍": "简介即将发布……",
        "亚马逊链接": "https://www.amazon.com/dp/9780062797032"
    },
    {
        "ISBN": "9781538713853",
        "书名": "The President Is Missing",
        "英文介绍": "The White House is the home of the President of the United States, the most guarded, monitored, closely watched person in the world. So how could a U.S. president vanish without a trace? And why would he choose to do so? This collaboration between President Bill Clinton and James Patterson is full of what it truly feels like to be the person in the Oval Office: the mind-boggling pressure, the heartbreaking decisions, the exhilarating opportunities, the soul-wrenching power.",
        "中文介绍": "白宫是美国总统的家，他是世界上受到最严密保护、监控和关注的人。那么，美国总统怎么会消失得无影无踪呢？他为什么要这么做？比尔·克林顿总统和詹姆斯·帕特森的这次合作，充分展现了身处椭圆形办公室的真实感受：令人难以置信的压力、令人心碎的决定、令人兴奋的机会，以及令人灵魂撕裂的权力。",
        "亚马逊链接": "https://www.amazon.com/dp/9781538713853"
    },
    {
        "ISBN": "9780525501640",
        "书名": "未找到元数据",
        "英文介绍": "Google Books 无记录",
        "中文介绍": "Google Books 无记录",
        "亚马逊链接": "https://www.amazon.com/dp/9780525501640"
    },
    {
        "ISBN": "9780425285046",
        "书名": "The Girl Before",
        "英文介绍": "In the tradition of \"The Girl on the Train, The Silent Wife, \"and\" Gone Girl \"comes an enthralling psychological thriller... \"Please make a list of every possession you consider essential to your life.\" The request seems odd, even intrusive and for the two women who answer, the consequences are devastating. EMMA Reeling from a traumatic break-in, Emma wants a new place to live. But none of the apartments she sees are affordable or feel safe. Until One Folgate Street... JANE After a personal tragedy, Jane needs a fresh start. When she finds One Folgate Street she is instantly drawn to the space... As Jane tries to untangle truth from lies, she unwittingly follows the same patterns, makes the same choices... and experiences the same terror, as the girl before.",
        "中文介绍": "继承了《列车上的女孩》、《沉默的妻子》和《消失的爱人》的传统，这是一部迷人的心理惊悚小说……“请列出你认为生活中必不可少的所有物品。”这个要求似乎很奇怪，甚至是侵入性的，对于回答的两个女人来说，后果是毁灭性的。艾玛：刚经历了一次创伤性的入室盗窃，艾玛想找个新住处。但她看的公寓要么买不起，要么感觉不安全。直到弗尔盖特街一号……简：在经历了一场个人悲剧后，简需要一个新的开始。当她发现弗尔盖特街一号时，她立刻被这个空间吸引……当简试图从谎言中解开真相时，她不知不觉地遵循着同样的模式，做出了同样的选择……并经历了同样的恐惧，就像之前的那个女孩一样。",
        "亚马逊链接": "https://www.amazon.com/dp/9780425285046"
    },
    {
        "ISBN": "9781840220957",
        "书名": "Tales of Mystery and the Macabre",
        "英文介绍": "Better known as the writer of pioneering social novels, Elizabeth Gaskell also wrote some fascinating tales of the supernatural and the macabre, which are collected here in this volume.",
        "中文介绍": "伊丽莎白·盖斯凯尔作为开创性社会小说的作家而闻名，但也写了一些关于超自然和恐怖的迷人故事，这些故事都收录在本书中。",
        "亚马逊链接": "https://www.amazon.com/dp/9781840220957"
    },
    {
        "ISBN": "9780062677594",
        "书名": "Dragon Teeth",
        "英文介绍": "Michael Crichton, the #1 New York Times bestselling author of Jurassic Park, returns to the world of paleontology in this recently discovered novel—a thrilling adventure set in the Wild West during the golden age of fossil hunting... Into this treacherous territory plunges the arrogant and entitled William Johnson, a Yale student with more privilege than sense... A page-turner that draws on both meticulously researched history and an exuberant imagination, Dragon Teeth is based on the rivalry between real-life paleontologists Cope and Marsh...",
        "中文介绍": "《侏罗纪公园》的纽约时报第一畅销书作者迈克尔·克莱顿在这部最近发现的小说中重返古生物学世界——这是一场发生在化石狩猎黄金时代狂野西部的惊险冒险……傲慢而有特权的耶鲁学生威廉·约翰逊闯入了这片危险的领土，他的特权比理智更多……《龙牙》是一部引人入胜的小说，取材于精心研究的历史和丰富的想象力，基于现实生活中古生物学家柯普和马什之间的竞争……",
        "亚马逊链接": "https://www.amazon.com/dp/9780062677594"
    },
    {
        "ISBN": "9781250027924",
        "书名": "A Midsummer's Equation",
        "英文介绍": "Detective Galileo, international bestseller Keigo Higashino's most beloved creation, returns in this sequel to the iconic The Devotion of Suspect X",
        "中文介绍": "侦探伽利略，国际畅销书作家东野圭吾最受喜爱的创作，在这部标志性作品《嫌疑人X的献身》的续集中回归。",
        "亚马逊链接": "https://www.amazon.com/dp/9781250027924"
    },
    {
        "ISBN": "9781840221848",
        "书名": "The Castle of Otranto",
        "英文介绍": "Three classic Gothic novels: Horace Walpole's The Castle of Otranto, Thomas Love Peacock's Nightmare Abbey and William Beckford's Vathek",
        "中文介绍": "三部经典哥特小说：贺拉斯·沃尔波尔的《奥特兰托堡》、托马斯·洛夫·皮科克的《噩梦修道院》和威廉·贝克福德的《瓦特克》。",
        "亚马逊链接": "https://www.amazon.com/dp/9781840221848"
    },
    {
        "ISBN": "9781840220674",
        "书名": "Madam Crowl's Ghost",
        "英文介绍": "In 1888 Henry James wrote 'There was the customary novel by Mr Le Fanu for the bedside; the ideal reading in a country house for the hours after midnight'. Madam Crowl's Ghost & Other Stories are tales selected from Le Fanu's stories... The great M.R. James, who collected and introduces the stories in this book, considered that Le Fanu 'stands absolutely in the first rank as a writer of ghost stories.'",
        "中文介绍": "1888年，亨利·詹姆斯写道：“床头放着勒·法努先生的惯常小说；这是乡间别墅午夜后的理想读物。”《克劳尔夫人的鬼魂及其他故事》选自勒·法努的故事……伟大的M.R.詹姆斯收集并介绍了这本书中的故事，他认为勒·法努“绝对是鬼故事作家中的一流人物”。",
        "亚马逊链接": "https://www.amazon.com/dp/9781840220674"
    },
    {
        "ISBN": "9781473671355",
        "书名": "The Dark Tower Boxset - 7 Dark Tower Novels Plus Wind Through the Keyhole",
        "英文介绍": "All of Stephen King's eight Dark Tower novels: one of the most acclaimed and popular series of all time. This collection includes: - The Dark Tower I: The Gunslinger; - The Dark Tower II: The Drawing of the Three; - The Dark Tower III: The Waste Lands; - The Dark Tower IV: Wizard and Glass; - The Dark Tower: The Wind Through the Keyhole; - The Dark Tower V: Wolves of the Calla; - The Dark Tower VI: Song of Susannah; - The Dark Tower VII: The Dark Tower.",
        "中文介绍": "斯蒂芬·金的所有八部《黑暗塔》小说：有史以来最受好评和最受欢迎的系列之一。该合集包括：- 黑暗塔 I：枪侠；- 黑暗塔 II：三张牌；- 黑暗塔 III：荒原；- 黑暗塔 IV：巫师与玻璃；- 黑暗塔：穿过钥匙孔的风；- 黑暗塔 V：卡拉之狼；- 黑暗塔 VI：苏珊娜之歌；- 黑暗塔 VII：黑暗塔。",
        "亚马逊链接": "https://www.amazon.com/dp/9781473671355"
    },
    {
        "ISBN": "9781840221640",
        "书名": "Ghost Stories of Edith Wharton",
        "英文介绍": "Selected & Introduced by David Stuart Davies. Traumatised by ghost stories in her youth, Pulitzer Prize winning author Edith Wharton (1862 -1937) channelled her fear and obsession into creating a series of spine-tingling tales filled with spirits beyond the grave and other supernatural phenomena... In this unique collection of finely wrought tales Wharton demonstrates her mastery of the ghost story genre... Compelling, rich and strange, the ghost stories of Edith Wharton, like vintage wine, have matured and grown more potent with the passing years.",
        "中文介绍": "由大卫·斯图尔特·戴维斯选编并介绍。普利策奖获得者伊迪丝·沃顿（1862-1937）年轻时曾因鬼故事而受创，她将这种恐惧和痴迷转化为创作一系列令人毛骨悚然的故事，充满了死后的灵魂和其他超自然现象……在这个独特的精雕细琢的故事集中，沃顿展示了她对鬼故事体裁的掌握……引人入胜、丰富而离奇，伊迪丝·沃顿的鬼故事就像陈年老酒，随着岁月的流逝而变得更加成熟和有力。",
        "亚马逊链接": "https://www.amazon.com/dp/9781840221640"
    },
    {
        "ISBN": "9780062474216",
        "书名": "Harry Potter: The Artifact Vault",
        "英文介绍": "Throughout the making of the eight Harry Potter movies, designers and craftspeople were tasked with creating fabulous chocolate-fantasy feasts, flying brooms, enchanted maps, and much more... Harry Potter: The Artifact Vault chronicles the work of the graphics department in creating vibrant and imaginative labels for potions bottles, brooms, and candy; the creation of Quidditch Quaffles, Bludgers, and Golden Snitches... This striking full-color compendium includes two exclusive bonus inserts...",
        "中文介绍": "在八部哈利·波特电影的制作过程中，设计师和工匠们的任务是创造梦幻般的巧克力盛宴、飞天扫帚、魔法地图等等……《哈利·波特：道具宝库》记录了图形部门为魔药瓶、扫帚和糖果创造生动且富有想象力的标签的工作；魁地奇鬼飞球、游走球和金色飞贼的制作……这本引人注目的全彩汇编包括两个独家附赠插页……",
        "亚马逊链接": "https://www.amazon.com/dp/9780062474216"
    },
    {
        "ISBN": "9781524732684",
        "书名": "Option B",
        "英文介绍": "#1 NEW YORK TIMES BEST SELLER • From authors of Lean In and Originals: a powerful, inspiring, and practical book about building resilience and moving forward after life’s inevitable setbacks After the sudden death of her husband, Sheryl Sandberg felt certain that she and her children would never feel pure joy again... Option B combines Sheryl’s personal insights with Adam’s eye-opening research on finding strength in the face of adversity... Two weeks after losing her husband, Sheryl was preparing for a father-child activity. “I want Dave,” she cried. Her friend replied, “Option A is not available,” and then promised to help her make the most of Option B. We all live some form of Option B. This book will help us all make the most of it.",
        "中文介绍": "纽约时报畅销书排行榜第一名 • 来自《向前一步》和《离经叛道》的作者：一本关于建立韧性并在生活不可避免的挫折后继续前进的强大、鼓舞人心且实用的书。在丈夫突然去世后，谢丽尔·桑德伯格确信她和她的孩子们再也不会感到纯粹的快乐了……《B选项》结合了谢丽尔的个人见解和亚当关于在逆境中寻找力量的令人大开眼界的研究……在失去丈夫两周后，谢丽尔正在准备一个父子活动。“我想要戴夫，”她哭着说。她的朋友回答说：“A选项已经不存在了，”然后承诺帮助她充分利用B选项。我们都生活在某种形式的B选项中。这本书将帮助我们所有人充分利用它。",
        "亚马逊链接": "https://www.amazon.com/dp/9781524732684"
    },
    {
        "ISBN": "9781840220780",
        "书名": "Tales of Unease",
        "英文介绍": "This gripping set of tales by the master storyteller Arthur Conan Doyle is bound to thrill and unnerve you. In these twilight excursions, Doyle's vivid imagination for the strange, the grotesque and the frightening is given full rein.",
        "中文介绍": "这组由故事大师阿瑟·柯南·道尔创作的引人入胜的故事，注定会让你感到兴奋和不安。在这些黄昏的探索中，道尔对奇怪、怪诞和可怕事物的生动想象得到了充分的发挥。",
        "亚马逊链接": "https://www.amazon.com/dp/9781840220780"
    },
    {
        "ISBN": "9780007902293",
        "书名": "Richard II",
        "英文介绍": "HarperCollins is proud to present its new range of best-loved, essential classics. 'Bear you well in this new spring of time, Lest you be cropp'd before you come to prime.' King Richard II rules England in a wasteful and short-sighted way, spending money unwisely and selecting his counselors foolishly... One of Shakespeare's 'history plays', Richard II explores the notion of the shadow that is cast over a king's reign if the throne is gained in underhand ways.",
        "中文介绍": "哈珀柯林斯自豪地推出其全新的最受喜爱、必读的经典系列。“愿你在这新的春日里安好，免得你在盛年之前就被收割。”理查二世国王以一种浪费和短视的方式统治着英格兰，不明智地花钱，愚蠢地选择顾问……作为莎士比亚的“历史剧”之一，《理查二世》探讨了如果王位是通过不正当手段获得的，那么国王的统治将笼罩在阴影之下的概念。",
        "亚马逊链接": "https://www.amazon.com/dp/9780007902293"
    },
    {
        "ISBN": "9780553419887",
        "书名": "The Complete Gillian Flynn",
        "英文介绍": "This boxed set contains the three novels from bestselling author Gillian Flynn: \"Gone Girl, Sharp Objects, \"and \"Dark Places.\" A #1 \"New York Times \"bestseller, \"Gone Girl \"is an unputdownable masterpiece about a marriage gone terribly, terribly wrong... In \"Sharp Objects, \" Flynn s debut novel, a young journalist returns home to cover a dark assignment and to face her own damaged family history... Flynn s second novel, \"Dark Places, \"is an intricately orchestrated thriller that ravages a family's past to unearth the truth behind a horrifying crime...",
        "中文介绍": "这个套装包含畅销书作家吉莉安·弗林的这三部小说：《消失的爱人》、《利器》和《暗处》。作为《纽约时报》第一畅销书，《消失的爱人》是一部让人爱不释手的杰作，讲述了一段极其糟糕的婚姻……在弗林的处女作《利器》中，一位年轻记者回到家乡报道一项黑暗的任务，并面对自己受损的家族历史……弗林的第二部小说《暗处》是一部精心策划的惊悚片，它摧毁了一个家庭的过去，以挖掘一桩可怕罪行背后的真相……",
        "亚马逊链接": "https://www.amazon.com/dp/9780553419887"
    },
    {
        "ISBN": "9781101972977",
        "书名": "Inferno (Movie Tie-In Edition)",
        "英文介绍": "\"Now a major motion picture\"--Front cover.",
        "中文介绍": "“现已改编为电影大片”——封面。",
        "亚马逊链接": "https://www.amazon.com/dp/9781101972977"
    },
    {
        "ISBN": "9781101973790",
        "书名": "Inferno. Movie Tie-In",
        "英文介绍": "暂无英文介绍",
        "中文介绍": "暂无英文介绍",
        "亚马逊链接": "https://www.amazon.com/dp/9781101973790"
    },
    {
        "ISBN": "9781840221749",
        "书名": "The Complete Fairy Tales of the Brothers Grimm",
        "英文介绍": "Fairy Tales.",
        "中文介绍": "童话故事。",
        "亚马逊链接": "https://www.amazon.com/dp/9781840221749"
    },
    {
        "ISBN": "9780091955106",
        "书名": "The Life-changing Magic of Tidying",
        "英文介绍": "Transform your home into a permanently clear and clutter-free space with the incredible KonMari Method. Japan's expert declutterer and professional cleaner Marie Kondo will help you tidy your rooms once and for all with her inspirational step-by-step method... The KonMari Method will not just transform your space. Once you have your house in order you will find that your whole life will change... Marie Kondo's method is based on a 'once-cleaned, never-messy-again' approach...",
        "中文介绍": "用不可思议的“怦然心动整理法”将你的家变成一个永久整洁、无杂物的空间。日本整理专家和专业清洁工近藤麻理惠将用她鼓舞人心的循序渐进的方法帮助你一劳永逸地整理房间……“怦然心动整理法”不仅会改变你的空间。一旦你把房子整理好，你会发现你的整个生活都会改变……近藤麻理惠的方法基于“一次整理，永不复乱”的理念……",
        "亚马逊链接": "https://www.amazon.com/dp/9780091955106"
    },
    {
        "ISBN": "9780805095159",
        "书名": "Being Mortal",
        "英文介绍": "Gawande, a practicing surgeon, addresses his profession's ultimate limitation, arguing that quality of life is the desired goal for patients and families of the terminally ill.",
        "中文介绍": "葛文德，一位执业外科医生，探讨了他职业的终极局限性，认为对于绝症患者及其家属来说，生活质量才是理想的目标。",
        "亚马逊链接": "https://www.amazon.com/dp/9780805095159"
    },
    {
        "ISBN": "9780141979410",
        "书名": "Queen Elizabeth II (Penguin Monarchs)",
        "英文介绍": "In September 2015 Queen Elizabeth II becomes Britain's longest-reigning monarch. During her long lifetime Britain and the world have changed beyond recognition, yet throughout she has stood steadfast as a lasting emblem of stability, continuity and public service... Hurd creates an arresting portrait of a woman deeply conservative by nature yet possessing a ready acceptance of modern life... With a preface by HRH Prince William, Duke of Cambridge",
        "中文介绍": "2015年9月，伊丽莎白二世女王成为英国在位时间最长的君主。在她漫长的一生中，英国和世界发生了翻天覆地的变化，但她始终坚定不移，成为稳定、连续性和公共服务的持久象征……赫德描绘了一位天性极其保守但又乐于接受现代生活的女性的引人注目的肖像……由剑桥公爵威廉王子殿下作序。",
        "亚马逊链接": "https://www.amazon.com/dp/9780141979410"
    },
    {
        "ISBN": "9780062332585",
        "书名": "Endgame: The Calling",
        "英文介绍": "The New York Times bestseller and international multimedia phenomenon! In each generation, for thousands of years, twelve Players have been ready. But they never thought Endgame would happen. Until now... The Players have been summoned to The Calling. And now they must fight one another in order to survive. All but one will fail. But that one will save the world. This is Endgame.",
        "中文介绍": "《纽约时报》畅销书和国际多媒体现象级作品！几千年来，每一代都有十二名玩家准备就绪。但他们从未想过“终局”会发生。直到现在……玩家们被召唤去响应“召唤”。现在他们必须为了生存而互相战斗。除了一个人，其他所有人都会失败。但那个人将拯救世界。这就是终局。",
        "亚马逊链接": "https://www.amazon.com/dp/9780062332585"
    },
    {
        "ISBN": "9781785150289",
        "书名": "Go Set a Watchman",
        "英文介绍": "From Harper Lee comes a landmark new novel set two decades after her beloved Pulitzer Prize-winning masterpiece, To Kill a Mockingbird. Maycomb, Alabama. Twenty-six-year-old Jean Louise Finch - `Scout' - returns home from New York City to visit her ageing father, Atticus. Set against the backdrop of the civil rights tensions and political turmoil that were transforming the South, Jean Louise's homecoming turns bittersweet when she learns disturbing truths about her close-knit family, the town and the people dearest to her... Written in the mid-1950s, Go Set a Watchman imparts a fuller, richer understanding and appreciation of Harper Lee...",
        "中文介绍": "哈珀·李带来了一部具有里程碑意义的新小说，背景设定在她备受喜爱的普利策奖获奖杰作《杀死一只知更鸟》的二十年后。阿拉巴马州梅科姆。26岁的吉恩·路易丝·芬奇——“斯库特”——从纽约市回到家乡探望她年迈的父亲阿提克斯。在改变南方的民权紧张局势和政治动荡的背景下，吉恩·路易丝的归乡变得苦乐参半，因为她得知了关于她关系紧密的家庭、小镇和她最亲爱的人的令人不安的真相……写于1950年代中期的《设立守望者》让人对哈珀·李有了更全面、更丰富的理解和欣赏……",
        "亚马逊链接": "https://www.amazon.com/dp/9781785150289"
    },
    {
        "ISBN": "9780857053503",
        "书名": "The Girl in the Spider's Web",
        "英文介绍": "暂无英文介绍",
        "中文介绍": "暂无英文介绍",
        "亚马逊链接": "https://www.amazon.com/dp/9780857053503"
    },
    {
        "ISBN": "9780062294418",
        "书名": "The Magic Strings of Frankie Presto",
        "英文介绍": "Mitch Albom creates his most unforgettable fictional character—Frankie Presto, the greatest guitarist to ever walk the earth—in this magical novel about the bands we join in life and the power of talent to change our lives. An epic story of the greatest guitar player to ever live, and the six lives he changed with his magical blue strings... With its Forest Gump-like romp through the music world, The Magic Strings of Frankie Presto is a classic in the making. A lifelong musician himself, Mitch Albom delivers a remarkable novel, infused with the message that “everyone joins a band in this life” and those connections change us all.",
        "中文介绍": "米奇·阿尔博姆创造了他最难忘的虚构角色——弗兰基·普雷斯托，地球上最伟大的吉他手——这部神奇的小说是关于我们在生活中加入的乐队以及天赋改变我们生活的力量。一个关于史上最伟大吉他手的史诗故事，以及他用神奇的蓝色琴弦改变的六条生命……《弗兰基·普雷斯托的魔法琴弦》像阿甘正传一样在音乐世界中穿梭，是一部正在形成的经典。作为一生的音乐家，米奇·阿尔博姆带来了一部非凡的小说，传达了“每个人在这一生中都会加入一个乐队”的信息，而这些联系改变了我们所有人。",
        "亚马逊链接": "https://www.amazon.com/dp/9780062294418"
    },
    {
        "ISBN": "9780316268394",
        "书名": "Twilight Tenth Anniversary/Life and Death Dual Edition",
        "英文介绍": "Celebrate the tenth anniversary of Twilight with this special double-feature book! This new edition pairs the classic love story with Stephenie Meyer's bold and surprising reimagining of the complete novel with the characters' genders reversed. In Life and Death, readers will be thrilled to experience this iconic tale told through the eyes of a human teenage boy in love with a female vampire. Packaged as an oversize, jacketed hardcover \"flip book,\" this edition features nearly 400 pages of new content as well as exquisite new cover art...",
        "中文介绍": "用这本特别的双重特写书来庆祝《暮光之城》十周年！这个新版本将经典爱情故事与斯蒂芬妮·梅尔大胆而令人惊讶的、角色性别互换的完整小说重构配对。在《生与死》中，读者将兴奋地体验这个通过爱上女吸血鬼的人类少年的眼睛讲述的标志性故事。包装成超大号、带护封的精装“翻转书”，此版本包含近400页的新内容以及精美的新封面艺术……",
        "亚马逊链接": "https://www.amazon.com/dp/9780316268394"
    },
    {
        "ISBN": "9781405923392",
        "书名": "My Story",
        "英文介绍": "Steven Gerrard - legendary captain of Liverpool and England - tells the story of the highs and lows of a twenty-year career at the top of English and world football... In My Story Gerrard dissects his full playing career. He examines the defining games such as the 2005 Champion's League Final... He talks about his 114 caps for England... He also has an incredible and rare personal story, telling us of the extraordinary ups and downs of staying loyal to one club for your entire career.",
        "中文介绍": "史蒂文·杰拉德——利物浦和英格兰的传奇队长——讲述了他在英格兰和世界足坛顶峰二十年职业生涯的高潮和低谷……在《我的故事》中，杰拉德剖析了他的整个职业生涯。他审视了决定性的比赛，如2005年欧冠决赛……他谈到了他为英格兰出场的114次……他还讲述了一个令人难以置信且罕见的个人故事，告诉我们整个职业生涯忠于一家俱乐部的非凡起伏。",
        "亚马逊链接": "https://www.amazon.com/dp/9781405923392"
    },
    {
        "ISBN": "9780141977379",
        "书名": "George VI (Penguin Monarchs)",
        "英文介绍": "Written by Philip Ziegler, one of Britain's most celebrated biographers, George VI is part of the Penguin Monarchs series... If Ethelred was notoriously 'Unready' and Alfred 'Great', King George VI should bear the title of 'George the Dutiful'. Throughout his life, George dedicated himself to the pursuit of what he thought he ought to be doing rather than what he wanted to do... He was not born to be king, but he made an admirable one, and was the figurehead of the nation at the time of its greatest trial, the Second World War...",
        "中文介绍": "由英国最著名的传记作家之一菲利普·齐格勒撰写，《乔治六世》是企鹅君主系列的一部分……如果埃塞尔雷德因“无准备”而臭名昭著，阿尔弗雷德因“伟大”而闻名，那么乔治六世国王应该被称为“尽职的乔治”。在他的一生中，乔治致力于追求他认为应该做的事情，而不是他想做的事情……他并非生来就是国王，但他成为了一位令人钦佩的国王，并在国家面临最大考验——第二次世界大战——时成为了国家的象征……",
        "亚马逊链接": "https://www.amazon.com/dp/9780141977379"
    },
    {
        "ISBN": "9780008122348",
        "书名": "Dance with Dragons: Part 2 After the Feast",
        "英文介绍": "HBO's hit series A GAME OF THRONES is based on George R.R. Martin's internationally bestselling series... Beyond the Wall, Jon Snow's Night's Watch is riven by treachery... In King's Landing Cersei Lannister finds herself abandoned by everyone she trusts. Her brother Tyrion, having fled a death sentence, is making his way ever east towards Meereen, where Daenerys Targaryen struggles to rule a city full of death... The future of the Seven Kingdoms hangs in the balance. The great dance is beginning...",
        "中文介绍": "HBO的热门剧集《权力的游戏》改编自乔治·R·R·马丁的国际畅销系列……在长城之外，琼恩·雪诺的守夜人军团因背叛而四分五裂……在君临城，瑟曦·兰尼斯特发现自己被所有信任的人抛弃。她的兄弟提利昂在逃脱死刑后，正一路向东前往弥林，在那里，丹妮莉丝·坦格利安正努力统治一座充满死亡的城市……七大王国的未来悬而未决。伟大的舞蹈正在开始……",
        "亚马逊链接": "https://www.amazon.com/dp/9780008122348"
    },
    {
        "ISBN": "9780062466792",
        "书名": "Warcraft",
        "英文介绍": "A stunning behind-the-scenes look at the making of Legendary Pictures’ and Universal Pictures’ Warcraft: Behind the Dark Portal... The peaceful realm of Azeroth stands on the brink of war... As a portal opens to connect the two worlds, one army faces destruction and the other faces extinction... Warcraft: Behind the Dark Portal tells the full story of the incredible creative journey that brought Blizzard Entertainment’s beloved epic adventure of world-colliding conflict to the big screen...",
        "中文介绍": "对传奇影业和环球影业的《魔兽：黑暗之门背后》制作过程的惊人幕后观察……和平的艾泽拉斯王国正处于战争边缘……随着连接两个世界的传送门打开，一支军队面临毁灭，另一支面临灭绝……《魔兽：黑暗之门背后》讲述了将暴雪娱乐深受喜爱的关于世界碰撞冲突的史诗冒险搬上大银幕的不可思议的创作旅程的完整故事……",
        "亚马逊链接": "https://www.amazon.com/dp/9780062466792"
    },
    {
        "ISBN": "9780451528537",
        "书名": "Henry IV, Part II",
        "英文介绍": "Picking up where Henry IV, Part One left off after the Battle of Shrewsbury, Henry IV, Part Two is the story of England's King Henry IV during his final months of life, his reconciliation with his wayward heir, and his eventual death.",
        "中文介绍": "紧接《亨利四世（上）》什鲁斯伯里战役之后，《亨利四世（下）》讲述了英格兰国王亨利四世生命最后几个月的故事，他与任性继承人的和解，以及他最终的死亡。",
        "亚马逊链接": "https://www.amazon.com/dp/9780451528537"
    },
    {
        "ISBN": "9781853261404",
        "书名": "Tales from Shakespeare",
        "英文介绍": "Includes Shakespeare's best-loved tales, comic and tragic, rewritten for a younger audience. This title contains the delightful pen-and-ink drawings of Arthur Rackham.",
        "中文介绍": "收录了莎士比亚最受喜爱的故事，包括喜剧和悲剧，专为年轻读者重写。本书包含亚瑟·拉克姆令人愉悦的钢笔画。",
        "亚马逊链接": "https://www.amazon.com/dp/9781853261404"
    },
    {
        "ISBN": "9780007874149",
        "书名": "Cecelia Ahern - the Gift Box",
        "英文介绍": "暂无英文介绍",
        "中文介绍": "暂无英文介绍",
        "亚马逊链接": "https://www.amazon.com/dp/9780007874149"
    }
]

# 创建DataFrame
df = pd.DataFrame(data)

# 将DataFrame导出为Excel文件
output_file = "Book_Info_Translated.xlsx"
df.to_excel(output_file, index=False)

print(f"文件已成功生成: {output_file}")