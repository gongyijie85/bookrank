"""自定义异常类"""


class BookRankException(Exception):
    """基础异常类"""
    pass


class APIRateLimitException(BookRankException):
    """API限流异常"""
    def __init__(self, message="API rate limit exceeded", retry_after=60):
        self.retry_after = retry_after
        super().__init__(message)


class CacheMissException(BookRankException):
    """缓存未命中异常"""
    pass


class APIException(BookRankException):
    """API调用异常"""
    def __init__(self, message="API call failed", status_code=500):
        self.status_code = status_code
        super().__init__(message)


class ValidationException(BookRankException):
    """数据验证异常"""
    pass


class SecurityException(BookRankException):
    """安全相关异常"""
    pass
