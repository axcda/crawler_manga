from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import logging
import asyncio
from config.settings import BROWSER_CONFIG, BROWSER_CONTEXT_CONFIG, DEFAULT_HEADERS

logger = logging.getLogger(__name__)

class BrowserManager:
    def __init__(self):
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.playwright = None
        self.max_retries = 3
        self.retry_delay = 0.5  # 减少重试延迟
        self._lock = asyncio.Lock()
        self._page_pool = []  # 页面池
        self.max_pool_size = 5  # 最大页面池大小
        
    async def init_browser(self) -> Browser:
        """初始化浏览器实例"""
        async with self._lock:
            for attempt in range(self.max_retries):
                try:
                    if not self.playwright:
                        self.playwright = await async_playwright().start()
                        if not self.playwright:
                            raise Exception("无法初始化playwright")
                    
                    if not self.browser or not self.browser.is_connected():
                        # 优化浏览器配置
                        browser_config = BROWSER_CONFIG.copy()
                        browser_config.update({
                            'args': [
                                '--disable-gpu',
                                '--disable-dev-shm-usage',
                                '--disable-setuid-sandbox',
                                '--no-first-run',
                                '--no-sandbox',
                                '--no-zygote',
                                '--single-process',
                                '--disable-extensions',
                                '--disable-features=site-per-process',
                                '--disable-software-rasterizer',
                                '--window-size=1920,1080',
                                '--start-maximized',
                                '--disable-infobars',
                                '--lang=zh-CN,zh',
                                '--hide-scrollbars',
                                '--mute-audio',
                                '--disable-notifications',
                                '--disable-popup-blocking',
                                '--disable-component-extensions-with-background-pages',
                                '--disable-default-apps',
                                '--metrics-recording-only',
                                '--ignore-certificate-errors',
                                '--ignore-ssl-errors',
                                '--ignore-certificate-errors-spki-list',
                                '--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                            ]
                        })
                        self.browser = await self.playwright.chromium.launch(**browser_config)
                        
                    return self.browser
                except Exception as e:
                    logger.error(f"初始化浏览器失败 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                    await self.cleanup()
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    raise
        
    async def init_context(self, browser: Browser) -> BrowserContext:
        """初始化浏览器上下文"""
        async with self._lock:
            for attempt in range(self.max_retries):
                try:
                    if not self.context:
                        # 优化上下文配置
                        context_config = BROWSER_CONTEXT_CONFIG.copy()
                        context_config.update({
                            'viewport': {'width': 1920, 'height': 1080},
                            'bypass_csp': True,  # 绕过内容安全策略
                            'ignore_https_errors': True,  # 忽略HTTPS错误
                            'java_script_enabled': True,
                            'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                            'locale': 'zh-CN',
                            'timezone_id': 'Asia/Shanghai',
                            'geolocation': {'latitude': 31.2304, 'longitude': 121.4737},
                            'permissions': ['geolocation'],
                            'color_scheme': 'dark',
                            'reduced_motion': 'no-preference',
                            'has_touch': False,
                            'is_mobile': False,
                            'device_scale_factor': 1,
                            'extra_http_headers': {
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
                        })
                        self.context = await browser.new_context(**context_config)
                        
                        # 设置全局超时
                        self.context.set_default_timeout(30000)  # 30秒
                        self.context.set_default_navigation_timeout(30000)  # 30秒
                        
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
                        
                    return self.context
                except Exception as e:
                    logger.error(f"初始化浏览器上下文失败 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    raise
        
    async def get_page(self) -> Page:
        """获取配置好的页面实例"""
        async with self._lock:
            # 尝试从页面池中获取可用页面
            while self._page_pool:
                page = self._page_pool.pop()
                try:
                    if await self._is_page_usable(page):
                        return page
                except:
                    continue
            
            for attempt in range(self.max_retries):
                try:
                    if not self.browser or not self.browser.is_connected():
                        self.browser = await self.init_browser()
                    
                    if not self.context:
                        self.context = await self.init_context(self.browser)
                    
                    page = await self.context.new_page()
                    if not page:
                        raise Exception("无法创建新页面")
                    
                    await self.setup_page(page)
                    return page
                    
                except Exception as e:
                    logger.error(f"获取页面实例失败 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                    await self.cleanup()
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    raise Exception(f"无法获取页面实例: {str(e)}")
    
    async def _is_page_usable(self, page: Page) -> bool:
        """检查页面是否可用"""
        try:
            await page.evaluate("1")  # 简单的JavaScript执行测试
            return True
        except:
            return False
        
    async def setup_page(self, page: Page):
        """设置页面配置"""
        if not page:
            raise Exception("页面实例为空")
            
        try:
            # 设置页面超时
            page.set_default_timeout(30000)  # 30秒
            page.set_default_navigation_timeout(30000)  # 30秒

            # 设置请求拦截
            await page.route("**/*.{png,jpg,jpeg,gif,svg}", lambda route: route.abort())
            
            # 启用JavaScript
            await page.evaluate("""
                // 清除控制台输出
                console.clear();
                // 禁用控制台输出
                console.log = () => {};
                console.error = () => {};
                console.warn = () => {};
            """)
            
            # 添加反爬虫JavaScript
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
                Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
                Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
                Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
                Object.defineProperty(window, 'chrome', {
                    get: () => ({
                        app: { isInstalled: false },
                        runtime: {},
                        loadTimes: function() {},
                        csi: function() {},
                        webstore: {}
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
                
                // 添加Canvas指纹
                const originalGetContext = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(type) {
                    const context = originalGetContext.apply(this, arguments);
                    if (type === '2d') {
                        const originalFillText = context.fillText;
                        context.fillText = function() {
                            return originalFillText.apply(this, arguments);
                        }
                    }
                    return context;
                };

                // 添加WebGL指纹
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    // 伪装WebGL参数
                    const fakeParams = {
                        37445: 'Intel Inc.',
                        37446: 'Intel Iris OpenGL Engine',
                        7937: 'WebKit',
                        35724: 'WebGL 1.0'
                    };
                    return fakeParams[parameter] || getParameter.apply(this, [parameter]);
                };
            """)
            
        except Exception as e:
            logger.error(f"设置页面配置失败: {str(e)}")
            raise
            
    async def _handle_route(self, route):
        """处理资源请求"""
        if route.request.resource_type in ['image', 'stylesheet', 'font']:
            await route.abort()
        elif route.request.resource_type == 'script':
            await route.continue_()
        else:
            await route.continue_()
        
    async def recycle_page(self, page: Page):
        """回收页面到页面池"""
        if len(self._page_pool) < self.max_pool_size:
            try:
                await page.evaluate("window.stop()")  # 停止所有正在进行的请求
                await page.evaluate("window.location.href = 'about:blank'")  # 重置页面
                self._page_pool.append(page)
            except:
                await self._close_page(page)
        else:
            await self._close_page(page)
            
    async def _close_page(self, page: Page):
        """安全关闭页面"""
        try:
            await page.close()
        except Exception as e:
            logger.error(f"关闭页面失败: {str(e)}")
        
    async def cleanup(self):
        """清理资源"""
        async with self._lock:
            try:
                # 清理页面池
                while self._page_pool:
                    page = self._page_pool.pop()
                    await self._close_page(page)
                
                if self.context:
                    try:
                        await self.context.close()
                    except Exception as e:
                        logger.error(f"关闭上下文失败: {str(e)}")
                    self.context = None
                    
                if self.browser:
                    try:
                        await self.browser.close()
                    except Exception as e:
                        logger.error(f"关闭浏览器失败: {str(e)}")
                    self.browser = None
                    
                if self.playwright:
                    try:
                        await self.playwright.stop()
                    except Exception as e:
                        logger.error(f"停止playwright失败: {str(e)}")
                    self.playwright = None
                    
            except Exception as e:
                logger.error(f"清理资源时出错: {str(e)}")
        
    async def close(self):
        """关闭浏览器资源"""
        try:
            await self.cleanup()
        except Exception as e:
            logger.error(f"关闭浏览器失败: {str(e)}")
            raise 