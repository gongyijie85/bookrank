"""
CSS 构建脚本 - 压缩并合并样式文件（使用 rcssmin 专业压缩器）
在部署时运行: python build.py
"""
import os
import rcssmin

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static', 'css')

CSS_FILES = [
    'base.css',
    'components.css',
    'animations.css',
]

OUTPUT_FILE = 'all.min.css'


def minify_css(css_text: str) -> str:
    """使用 rcssmin 进行专业 CSS 压缩（替代手工正则，避免误匹配）"""
    return rcssmin.cssmin(css_text)


def build():
    output_path = os.path.join(STATIC_DIR, OUTPUT_FILE)

    source_mtimes = []
    for filename in CSS_FILES:
        filepath = os.path.join(STATIC_DIR, filename)
        if not os.path.exists(filepath):
            print(f'⚠️  文件不存在，跳过: {filename}')
            continue
        source_mtimes.append(os.path.getmtime(filepath))

    if os.path.exists(output_path) and source_mtimes:
        output_mtime = os.path.getmtime(output_path)
        if all(output_mtime >= mtime for mtime in source_mtimes):
            print(f'✅ all.min.css 已是最新，跳过构建')
            return output_path

    combined = ''
    for filename in CSS_FILES:
        filepath = os.path.join(STATIC_DIR, filename)
        if not os.path.exists(filepath):
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        combined += content + '\n'
        print(f'  ✓ {filename} ({len(content)} bytes)')

    minified = minify_css(combined)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(minified)

    original_size = len(combined)
    compressed_size = len(minified)
    saved = original_size - compressed_size
    ratio = (1 - compressed_size / original_size) * 100 if original_size else 0

    print(f'\n✅ CSS 构建完成!')
    print(f'   原始: {original_size:,} bytes')
    print(f'   压缩: {compressed_size:,} bytes')
    print(f'   节省: {saved:,} bytes ({ratio:.1f}%)')

    return output_path


if __name__ == '__main__':
    build()
