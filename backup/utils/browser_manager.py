from playwright.async_api import async_playwright
import logging
from config.settings import BROWSER_CONFIG, BROWSER_CONTEXT_CONFIG, DEFAULT_HEADERS

logger = logging.getLogger(__name__)

class BrowserManager:
    def __init__(self):
        self.browser = None
        self.context = None
        self.playwright = None
        
    async def init_browser(self):
        """初始化浏览器实例"""
        try:
            if not self.playwright:
                self.playwright = await async_playwright().start()
            if not self.browser:
                self.browser = await self.playwright.chromium.launch(**BROWSER_CONFIG)
            return self.browser
        except Exception as e:
            logger.error(f"初始化浏览器失败: {str(e)}")
            raise
        
    async def init_context(self, browser):
        """初始化浏览器上下文"""
        try:
            if not self.context:
                self.context = await browser.new_context(**BROWSER_CONTEXT_CONFIG)
            return self.context
        except Exception as e:
            logger.error(f"初始化浏览器上下文失败: {str(e)}")
            raise
        
    async def get_page(self):
        """获取配置好的页面实例"""
        try:
            if not self.browser:
                self.browser = await self.init_browser()
            if not self.context:
                self.context = await self.init_context(self.browser)
                
            page = await self.context.new_page()
            await self.setup_page(page)
            return page
        except Exception as e:
            logger.error(f"获取页面实例失败: {str(e)}")
            raise
        
    async def setup_page(self, page):
        """设置页面配置"""
        try:
            await page.set_extra_http_headers(DEFAULT_HEADERS)
            
            # 添加更多反爬虫JavaScript
            await page.add_init_script("""
                // 修改 navigator 属性
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh']
                });
                
                // 添加 Chrome 对象
                window.chrome = {
                    runtime: {}
                };
                
                // 修改 permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // 添加 WebGL
                const getParameter = WebGLRenderingContext.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.'
                    }
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine'
                    }
                    return getParameter(parameter);
                };
            """)
            
            # 设置更多浏览器特征
            await page.evaluate("""
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'MacIntel'
                });
                Object.defineProperty(navigator, 'productSub', {
                    get: () => '20030107'
                });
                Object.defineProperty(navigator, 'vendor', {
                    get: () => 'Google Inc.'
                });
            """)
            
        except Exception as e:
            logger.error(f"设置页面配置失败: {str(e)}")
            raise
        
    async def close(self):
        """关闭浏览器资源"""
        try:
            if self.context:
                await self.context.close()
                self.context = None
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
        except Exception as e:
            logger.error(f"关闭浏览器失败: {str(e)}")
            # 即使出错也要尝试清理资源
            self.context = None
            self.browser = None
            self.playwright = None
            
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close() 