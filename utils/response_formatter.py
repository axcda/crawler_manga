from quart import jsonify
from datetime import datetime

class ResponseFormatter:
    @staticmethod
    def success(data, message="success", code=200):
        """格式化成功响应"""
        return jsonify({
            'code': code,
            'message': message,
            'data': data,
            'timestamp': int(datetime.now().timestamp())
        })
        
    @staticmethod
    def error(message, code=500, data=None):
        """格式化错误响应"""
        return jsonify({
            'code': code,
            'message': message,
            'data': data,
            'timestamp': int(datetime.now().timestamp())
        }), code
        
    @staticmethod
    def not_found(message="资源未找到"):
        """格式化404响应"""
        return ResponseFormatter.error(message, 404)
        
    @staticmethod
    def bad_request(message="无效的请求"):
        """格式化400响应"""
        return ResponseFormatter.error(message, 400)
        
    @staticmethod
    def server_error(message="服务器内部错误"):
        """格式化500响应"""
        return ResponseFormatter.error(message, 500) 