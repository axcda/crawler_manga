from quart import jsonify, make_response
from datetime import datetime

class ResponseFormatter:
    @staticmethod
    async def success(data, message="success", code=200):
        """格式化成功响应"""
        response = {
            'code': code,
            'message': message,
            'data': data,
            'timestamp': int(datetime.now().timestamp())
        }
        return await make_response(jsonify(response))
        
    @staticmethod
    async def error(message, code=500, data=None):
        """格式化错误响应"""
        response = {
            'code': code,
            'message': message,
            'data': data,
            'timestamp': int(datetime.now().timestamp())
        }
        resp = await make_response(jsonify(response))
        resp.status_code = code
        return resp
        
    @staticmethod
    async def not_found(message="资源未找到"):
        """格式化404响应"""
        return await ResponseFormatter.error(message, 404)
        
    @staticmethod
    async def bad_request(message="无效的请求"):
        """格式化400响应"""
        return await ResponseFormatter.error(message, 400)
        
    @staticmethod
    async def server_error(message="服务器内部错误"):
        """格式化500响应"""
        return await ResponseFormatter.error(message, 500) 