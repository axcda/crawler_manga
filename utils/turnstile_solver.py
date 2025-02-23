import sys
import time
import logging
import asyncio
from typing import Dict, Optional, Any
from dataclasses import dataclass
from playwright.async_api import async_playwright

@dataclass
class TurnstileResult:
    cookies: Dict[str, str]
    user_agent: str
    elapsed_time: float

class CustomLogger(logging.Logger):
    COLORS = {
        'DEBUG': '\033[35m',  # Magenta
        'INFO': '\033[34m',   # Blue
        'SUCCESS': '\033[32m', # Green
        'WARNING': '\033[33m', # Yellow
        'ERROR': '\033[31m',   # Red
    }
    RESET = '\033[0m'  # Reset color

    def format_message(self, level, message):
        timestamp = time.strftime('%H:%M:%S')
        return f"[{timestamp}] [{self.COLORS.get(level, '')}{level}{self.RESET}] -> {message}"

    def debug(self, message, *args, **kwargs):
        super().debug(self.format_message('DEBUG', message), *args, **kwargs)

    def info(self, message, *args, **kwargs):
        super().info(self.format_message('INFO', message), *args, **kwargs)

    def success(self, message, *args, **kwargs):
        super().info(self.format_message('SUCCESS', message), *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        super().warning(self.format_message('WARNING', message), *args, **kwargs)

    def error(self, message, *args, **kwargs):
        super().error(self.format_message('ERROR', message), *args, **kwargs)

logging.setLoggerClass(CustomLogger)
logger = logging.getLogger("TurnstileSolver")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)

class TurnstileSolver:
    def __init__(self, debug: bool = False, headless: bool = True):
        self.debug = debug
        self.headless = headless  # 确保使用无头模式
        self.browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-gpu",
            "--ignore-certificate-errors"
        ]

    async def solve(self, url: str) -> Optional[TurnstileResult]:
        """
        解决 Turnstile 验证
        
        Args:
            url: 目标URL
            
        Returns:
            Optional[TurnstileResult]: 包含cookies和user-agent的结果
        """
        start_time = time.time()
        try:
            logger.info(f"启动浏览器...")
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=self.headless,
                    args=self.browser_args
                )
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                )

                try:
                    page = await context.new_page()
                    page.set_default_timeout(30000)
                    
                    # 访问页面
                    logger.info(f"访问页面: {url}")
                    await page.goto(url, wait_until='domcontentloaded')
                    
                    # 等待 Turnstile iframe 加载
                    logger.info("等待 Turnstile iframe 加载...")
                    turnstile_frame = None
                    try:
                        turnstile_frame = await page.wait_for_selector(
                            'iframe[src*="challenges.cloudflare.com"]',
                            timeout=10000
                        )
                    except Exception as e:
                        logger.warning(f"未找到 Turnstile iframe: {str(e)}")
                    
                    if turnstile_frame:
                        logger.info("找到 Turnstile iframe，等待验证完成...")
                        await page.wait_for_timeout(5000)
                    
                    # 获取 cookies
                    cookies = await context.cookies()
                    cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
                    
                    # 获取 user agent
                    user_agent = await page.evaluate('() => navigator.userAgent')
                    
                    logger.success("验证完成")
                    return TurnstileResult(
                        cookies=cookie_dict,
                        user_agent=user_agent,
                        elapsed_time=time.time() - start_time
                    )
                    
                except Exception as e:
                    logger.error(f"页面操作出错: {str(e)}")
                    return None
                    
                finally:
                    await context.close()
                    await browser.close()
                    
        except Exception as e:
            logger.error(f"解决验证时出错: {str(e)}")
            return None 