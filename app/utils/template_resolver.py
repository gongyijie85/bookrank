"""根据设备类型自动选择模板的渲染工具

移动端优先尝试 mobile/ 子目录下的模板，缺失时自动回退到桌面版，
实现渐进式迁移：未做移动版的页面仍可正常访问桌面版。
"""
from flask import render_template
from jinja2 import TemplateNotFound

from app.utils.device_detect import is_mobile


def render_adaptive(template_name: str, **context) -> str:
    """自适应渲染：移动端优先尝试 mobile/ 模板，缺失则回退桌面版。

    Args:
        template_name: 桌面模板名（如 'index.html'）
        **context: 传递给模板的上下文变量

    Returns:
        渲染后的 HTML 字符串
    """
    if is_mobile():
        mobile_template = f'mobile/{template_name}'
        try:
            return render_template(mobile_template, **context)
        except TemplateNotFound:
            pass  # 移动模板未实现，回退桌面版
    return render_template(template_name, **context)
