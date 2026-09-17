"""HuggingFace Space 运行时的资源约束开关。

Space 免费版只有一个 Gunicorn worker：首屏请求里任何阻塞式的 Alembic 升级或
批量翻译调用都会独占该 worker，站点在超时前无法响应第二个请求。Render 和本地
没有这个约束，保持完整行为。
"""

import os


def is_space_runtime() -> bool:
    """HuggingFace 会为每个 Space 自动注入 SPACE_ID，据此判定运行环境。"""
    return bool(os.environ.get('SPACE_ID'))
