import cloudscraper
import logging
from typing import Optional
from config.settings import DEFAULT_HEADERS

logger = logging.getLogger(__name__)

class CloudflareSession:
    _instance = None
    _scraper = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        if CloudflareSession._instance is not None:
            raise Exception("CloudflareSession 是单例类，请使用 get_instance() 方法获取实例")
        else:
            CloudflareSession._instance = self
            self._init_scraper()
    
    def _init_scraper(self):
        """初始化 cloudscraper 实例"""
        try:
            self._scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'darwin',
                    'mobile': False
                },
                debug=True
            )
            
            # 设置默认请求头
            self._scraper.headers.update(DEFAULT_HEADERS)
            
            # 设置请求超时
            self._scraper.timeout = 30
            
            # 设置重试次数
            self._scraper.retry = 3
            
            # 设置SSL验证
            self._scraper.verify = False
            
            logger.info("成功创建Cloudflare会话")
            
        except Exception as e:
            logger.error(f"创建Cloudflare会话失败: {str(e)}")
            raise
    
    def get(self, url: str, **kwargs) -> Optional[cloudscraper.Response]:
        """发送GET请求"""
        try:
            # 添加默认参数
            kwargs.setdefault('timeout', 30)
            kwargs.setdefault('allow_redirects', True)
            kwargs.setdefault('verify', False)
            
            # 发送请求
            response = self._scraper.get(url, **kwargs)
            
            # 检查响应状态
            if response.status_code == 200:
                return response
            else:
                logger.error(f"请求失败，状态码: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"请求出错: {str(e)}")
            return None
    
    def post(self, url: str, **kwargs) -> Optional[cloudscraper.Response]:
        """发送POST请求"""
        try:
            # 添加默认参数
            kwargs.setdefault('timeout', 30)
            kwargs.setdefault('allow_redirects', True)
            kwargs.setdefault('verify', False)
            
            # 发送请求
            response = self._scraper.post(url, **kwargs)
            
            # 检查响应状态
            if response.status_code == 200:
                return response
            else:
                logger.error(f"请求失败，状态码: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"请求出错: {str(e)}")
            return None
    
    def __del__(self):
        """清理资源"""
        try:
            if self._scraper:
                self._scraper.close()
        except Exception as e:
            logger.error(f"关闭会话时出错: {str(e)}") 