"""
初始化模块
"""

from .awards import init_awards_data
from .sample_award_books import init_sample_award_books
from .sample_books import init_sample_books

__all__ = ['init_awards_data', 'init_sample_award_books', 'init_sample_books']
