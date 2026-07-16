"""
新书推介页面 i18n 修复 — 计划文档

## 问题清单
1. en.po 中多个新书页翻译键完全缺失，导致英文模式下回退到中文 msgid：
   - 当前结果 / 按出版日期筛选最近 / 天已出版图书
   - 近7天出版 / 最近7天出版 / 最近30天出版 / 最近90天出版 / 最近半年出版 / 最近一年出版
   - 当前出版时间范围暂无新书... / 尝试放宽出版时间范围...
   - 搜索书名、作者、 / 本（已有但翻译为空）

2. 出版社名称切换语言没变化：模板用 `{{ pub.name }}`（中文），英文模式应显示 `pub.name_en`

3. JS 端切换语言时，未带 data-i18n 属性的 SSR 元素不会更新

4. min.js 与 src.js 同步问题（v0.9.56 教训）

## 修复方案

### Phase 1：补全翻译
- 在 translations/zh/messages.po + en/messages.po 添加所有缺失键
- pybabel compile 重新生成 .mo

### Phase 2：TRANSLATIONS 字典
- translations.js + translations.min.js 各添加 ~20 个新书相关 key

### Phase 3：new_books.html 模板
- 给所有可翻译元素加 data-i18n / data-i18n-placeholder 属性
- publisher 链接添加 data-pub-name-zh + data-pub-name-en
- 添加 applyNewBooksLanguage(lang) 函数：调用 applyPageTranslation + 重渲染 publisher 名称 + 重渲染动态 select option 文案
- select option 文本需要特殊处理（option 是子元素，没法直接 data-i18n 到 option）

### Phase 4：测试与文档
- scripts/_verify_new_books_i18n.py Playwright 验证
- 更新 CHANGELOG.md / VERSION.md
"""
