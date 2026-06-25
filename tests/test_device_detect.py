"""移动设备检测工具单元测试"""

from flask import Flask

from app.utils.device_detect import is_mobile


class TestIsMobile:
    """is_mobile() 函数测试"""

    def test_returns_false_without_request_context(self) -> None:
        """无请求上下文时返回 False"""
        assert is_mobile() is False

    def test_returns_true_for_iphone(self) -> None:
        """iPhone UA 识别为移动端"""
        app = Flask(__name__)
        with app.test_request_context('/', headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'}):
            assert is_mobile() is True

    def test_returns_true_for_android(self) -> None:
        """Android UA 识别为移动端"""
        app = Flask(__name__)
        with app.test_request_context('/', headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7)'}):
            assert is_mobile() is True

    def test_returns_false_for_desktop_chrome(self) -> None:
        """桌面 Chrome UA 识别为非移动端"""
        app = Flask(__name__)
        with app.test_request_context('/', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'}):
            assert is_mobile() is False

    def test_returns_false_for_empty_user_agent(self) -> None:
        """空 UA 识别为非移动端"""
        app = Flask(__name__)
        with app.test_request_context('/', headers={'User-Agent': ''}):
            assert is_mobile() is False

    def test_returns_true_for_ipad_mobile_safari(self) -> None:
        """移动 Safari UA 识别为移动端"""
        app = Flask(__name__)
        with app.test_request_context('/', headers={'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}):
            assert is_mobile() is True
