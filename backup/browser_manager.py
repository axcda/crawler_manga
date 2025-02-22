import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import logging
from typing import Optional
import time
from config.settings import BROWSER_CONFIG, BROWSER_CONTEXT_CONFIG

logger = logging.getLogger(__name__)

class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self._init_lock = asyncio.Lock()
        self._max_retries = 3
        self._retry_delay = 1  # 重试延迟（秒）

    async def init_browser(self) -> None:
        """初始化浏览器实例"""
        async with self._init_lock:
            try:
                if self.playwright is None:
                    self.playwright = await async_playwright().start()
                
                if self.browser is None:
                    self.browser = await self.playwright.chromium.launch(
                        headless=True,
                        args=[
                            '--no-sandbox',
                            '--disable-setuid-sandbox',
                            '--disable-dev-shm-usage',
                            '--disable-accelerated-2d-canvas',
                            '--disable-gpu',
                            '--disable-web-security',
                            '--disable-features=IsolateOrigins,site-per-process',
                            '--disable-blink-features=AutomationControlled',
                            '--ignore-certificate-errors',
                            '--window-size=1920,1080',
                            '--start-maximized',
                            '--disable-infobars',
                            '--lang=zh-CN,zh',
                            '--no-first-run',
                            '--no-default-browser-check',
                            '--hide-scrollbars',
                            '--mute-audio',
                            '--disable-notifications',
                            '--disable-popup-blocking',
                            '--disable-extensions',
                            '--disable-component-extensions-with-background-pages',
                            '--disable-default-apps',
                            '--metrics-recording-only',
                            '--ignore-certificate-errors',
                            '--ignore-ssl-errors',
                            '--ignore-certificate-errors-spki-list',
                            '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                        ]
                    )
                
                if self.context is None:
                    self.context = await self.browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                        locale='zh-CN',
                        timezone_id='Asia/Shanghai',
                        geolocation={'latitude': 31.2304, 'longitude': 121.4737},
                        permissions=['geolocation'],
                        color_scheme='dark',
                        reduced_motion='no-preference',
                        has_touch=False,
                        is_mobile=False,
                        device_scale_factor=1,
                        ignore_https_errors=True,
                        bypass_csp=True,
                        extra_http_headers={
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                            'Accept-Encoding': 'gzip, deflate, br',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                            'Sec-Fetch-Site': 'none',
                            'Sec-Fetch-Mode': 'navigate',
                            'Sec-Fetch-User': '?1',
                            'Sec-Fetch-Dest': 'document',
                            'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                            'sec-ch-ua-mobile': '?0',
                            'sec-ch-ua-platform': '"macOS"'
                        }
                    )
                    
                    # 设置默认超时
                    self.context.set_default_timeout(60000)  # 60秒
                    self.context.set_default_navigation_timeout(60000)  # 60秒
                    
                    # 设置 Cookie
                    await self.context.add_cookies([{
                        'name': 'locale',
                        'value': 'zh-CN',
                        'domain': 'g-mh.org',
                        'path': '/'
                    }, {
                        'name': 'timezone',
                        'value': 'Asia/Shanghai',
                        'domain': 'g-mh.org',
                        'path': '/'
                    }, {
                        'name': 'theme',
                        'value': 'dark',
                        'domain': 'g-mh.org',
                        'path': '/'
                    }])
                
                logger.info("浏览器初始化成功")
                
            except Exception as e:
                logger.error(f"浏览器初始化失败: {str(e)}")
                await self.close()
                raise

    async def get_page(self) -> Page:
        """获取新的页面实例"""
        for attempt in range(self._max_retries):
            try:
                await self.init_browser()
                page = await self.context.new_page()
                
                # 设置页面级别的超时
                page.set_default_timeout(60000)  # 60秒
                page.set_default_navigation_timeout(60000)  # 60秒
                
                # 添加反爬虫脚本
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['zh-CN', 'zh', 'en-US', 'en']
                    });
                    Object.defineProperty(navigator, 'platform', {
                        get: () => 'MacIntel'
                    });
                    Object.defineProperty(navigator, 'hardwareConcurrency', {
                        get: () => 8
                    });
                    Object.defineProperty(navigator, 'deviceMemory', {
                        get: () => 8
                    });
                    Object.defineProperty(navigator, 'maxTouchPoints', {
                        get: () => 0
                    });
                    Object.defineProperty(screen, 'colorDepth', {
                        get: () => 24
                    });
                    Object.defineProperty(screen, 'pixelDepth', {
                        get: () => 24
                    });
                    Object.defineProperty(window, 'chrome', {
                        get: () => ({
                            runtime: {},
                            loadTimes: function() {},
                            csi: function() {},
                            app: {}
                        })
                    });
                    Object.defineProperty(navigator, 'connection', {
                        get: () => ({
                            effectiveType: '4g',
                            rtt: 50,
                            downlink: 10,
                            saveData: false
                        })
                    });
                    Object.defineProperty(navigator, 'permissions', {
                        get: () => ({
                            query: async (param) => ({
                                state: param.name === 'notifications' ? 'granted' : 'prompt'
                            })
                        })
                    });
                """)
                
                return page
            except Exception as e:
                logger.error(f"获取页面失败 (尝试 {attempt + 1}/{self._max_retries}): {str(e)}")
                await self.close()
                
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._retry_delay)
                else:
                    raise Exception(f"获取页面失败，已重试 {self._max_retries} 次")

    async def close(self) -> None:
        """关闭所有资源"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.error(f"关闭资源时发生错误: {str(e)}")
        finally:
            self.context = None
            self.browser = None
            self.playwright = None

    async def __aenter__(self):
        await self.init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

browser_manager = BrowserManager() 