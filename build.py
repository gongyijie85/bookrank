"""
CSS + JS 构建脚本 - 压缩静态资源
在部署时运行: python build.py

CSS: 合并 base + components + animations → all.min.css
JS:  各文件独立压缩 → *.min.js
"""

import os
import re

import rcssmin

STATIC_CSS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'css')
STATIC_JS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'js')

CSS_FILES = [
    'base.css',
    'components.css',
    'animations.css',
]

OUTPUT_FILE = 'all.min.css'

JS_FILES = [
    'base.js',
    'api.js',
    'config.js',
    'utils.js',
    'translations.js',
    'book-i18n.js',
]


def minify_css(css_text: str) -> str:
    """使用 rcssmin 进行专业 CSS 压缩（替代手工正则，避免误匹配）"""
    return rcssmin.cssmin(css_text)


def minify_js(js_text: str) -> str:
    """简单 JS 压缩：移除注释和多余空白（安全版，不处理复杂的代码变换）"""
    # 移除单行注释 (// ...)
    js_text = re.sub(r'//.*$', '', js_text, flags=re.MULTILINE)
    # 移除多行注释 (/* ... */)
    js_text = re.sub(r'/\*.*?\*/', '', js_text, flags=re.DOTALL)
    # 移除行首行尾空白
    lines = []
    for line in js_text.split('\n'):
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return '\n'.join(lines)


def build_js():
    """构建 JS 文件"""
    print('\n[JS] 构建 JavaScript...')
    total_original = 0
    total_compressed = 0

    for filename in JS_FILES:
        src = os.path.join(STATIC_JS_DIR, filename)
        if not os.path.exists(src):
            print(f'  [WARN] 文件不存在，跳过: {filename}')
            continue

        name, ext = os.path.splitext(filename)
        dst = os.path.join(STATIC_JS_DIR, f'{name}.min{ext}')

        # 增量构建检查
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            original = os.path.getsize(src)
            compressed = os.path.getsize(dst)
            print(f'  [OK] {filename} → {name}.min{ext} (已是最新)')
            total_original += original
            total_compressed += compressed
            continue

        with open(src, encoding='utf-8') as f:
            original = f.read()

        compressed = minify_js(original)
        with open(dst, 'w', encoding='utf-8') as f:
            f.write(compressed)

        orig_size = len(original)
        comp_size = len(compressed)
        ratio = (1 - comp_size / orig_size) * 100 if orig_size else 0
        print(f'  [OK] {filename}: {orig_size:,} → {comp_size:,} bytes ({ratio:.1f}%)')
        total_original += orig_size
        total_compressed += comp_size

    if total_original:
        total_ratio = (1 - total_compressed / total_original) * 100
        print(f'  [OK] JS 构建完成: {total_original:,} → {total_compressed:,} bytes ({total_ratio:.1f}%)')
    return total_compressed > 0


def build():
    """构建所有静态资源"""
    build_css()
    build_js()


def build_css():
    """构建 CSS"""
    output_path = os.path.join(STATIC_CSS_DIR, OUTPUT_FILE)
    print('[CSS] 构建样式...')

    source_mtimes = []
    for filename in CSS_FILES:
        filepath = os.path.join(STATIC_CSS_DIR, filename)
        if not os.path.exists(filepath):
            print(f'[WARN] 文件不存在，跳过: {filename}')
            continue
        source_mtimes.append(os.path.getmtime(filepath))

    if os.path.exists(output_path) and source_mtimes:
        output_mtime = os.path.getmtime(output_path)
        if all(output_mtime >= mtime for mtime in source_mtimes):
            print('[OK] all.min.css 已是最新，跳过构建')
            return output_path

    combined = ''
    for filename in CSS_FILES:
        filepath = os.path.join(STATIC_CSS_DIR, filename)
        if not os.path.exists(filepath):
            continue
        with open(filepath, encoding='utf-8') as f:
            content = f.read()
        combined += content + '\n'
        print(f'  - {filename} ({len(content)} bytes)')

    minified = minify_css(combined)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(minified)

    original_size = len(combined)
    compressed_size = len(minified)
    saved = original_size - compressed_size
    ratio = (1 - compressed_size / original_size) * 100 if original_size else 0

    print('\n[OK] CSS 构建完成!')
    print(f'   原始: {original_size:,} bytes')
    print(f'   压缩: {compressed_size:,} bytes')
    print(f'   节省: {saved:,} bytes ({ratio:.1f}%)')

    return output_path


if __name__ == '__main__':
    build()
