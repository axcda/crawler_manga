import functools
import logging
from typing import Callable, Any
from quart import current_app
from utils.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)

class ApiException(Exception):
    """API异常基类"""
    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(message)

class NotFoundError(ApiException):
    """资源未找到异常"""
    def __init__(self, message: str = "资源未找到"):
        super().__init__(message, 404)

class BadRequestError(ApiException):
    """无效请求异常"""
    def __init__(self, message: str = "无效的请求"):
        super().__init__(message, 400)

class ServerError(ApiException):
    """服务器错误异常"""
    def __init__(self, message: str = "服务器内部错误"):
        super().__init__(message, 500)

def handle_exceptions(f: Callable) -> Callable:
    """异常处理装饰器"""
    @functools.wraps(f)
    async def decorated_function(*args: Any, **kwargs: Any) -> Any:
        try:
            return await f(*args, **kwargs)
        except NotFoundError as e:
            logger.warning(f"NotFoundError in {f.__name__}: {str(e)}")
            return ResponseFormatter.not_found(str(e))
        except BadRequestError as e:
            logger.warning(f"BadRequestError in {f.__name__}: {str(e)}")
            return ResponseFormatter.bad_request(str(e))
        except ApiException as e:
            logger.error(f"ApiException in {f.__name__}: {str(e)}")
            return ResponseFormatter.error(str(e), e.code)
        except Exception as e:
            logger.error(f"Unexpected error in {f.__name__}: {str(e)}", exc_info=True)
            return ResponseFormatter.server_error(str(e))
    return decorated_function 