from playwright.async_api import async_playwright
import logging
from config.settings import BROWSER_CONFIG, BROWSER_CONTEXT_CONFIG, DEFAULT_HEADERS

logger = logging.getLogger(__name__)

class BrowserManager:
    def __init__(self):
        self.browser = None
        self.context = None
        
    async def init_browser(self):
        """初始化浏览器实例"""
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(**BROWSER_CONFIG)
            return browser
        except Exception as e:
            logger.error(f"初始化浏览器失败: {str(e)}")
            raise
        
    async def init_context(self, browser):
        """初始化浏览器上下文"""
        try:
            context = await browser.new_context(**BROWSER_CONTEXT_CONFIG)
            return context
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
            
            # 添加反爬虫JavaScript
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """)
        except Exception as e:
            logger.error(f"设置页面配置失败: {str(e)}")
            raise
        
    async def close(self):
        """关闭浏览器资源"""
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
                self.context = None
        except Exception as e:
            logger.error(f"关闭浏览器失败: {str(e)}")
            raise 