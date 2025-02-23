import sys
import time
import logging
import asyncio
from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass
from playwright.async_api import async_playwright, Page, BrowserContext

class CustomLogger(logging.Logger):
    COLORS = {
        'DEBUG': '\033[35m',  # Magenta
        'INFO': '\033[34m',  # Blue
        'SUCCESS': '\033[32m',  # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',  # Red
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
logger = logging.getLogger("ContentExtractor")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)

class ContentExtractor:
    def __init__(self, debug: bool = False, headless: bool = True):
        self.debug = debug
        self.headless = headless
        self.browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",  # 禁用同源策略
            "--disable-gpu",  # 禁用GPU加速
            "--disable-notifications",  # 禁用通知
            "--disable-popup-blocking",  # 禁用弹窗拦截
            "--ignore-certificate-errors"  # 忽略证书错误
        ]

    async def extract_content(self, url: str) -> Dict[str, Any]:
        """
        提取页面内容
        
        Args:
            url: 目标URL
            
        Returns:
            Dict[str, Any]: 包含图片URL和导航信息的字典
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
                    
                    # 设置请求拦截
                    await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff2,woff}", lambda route: route.abort())
                    await page.route("**/*{analytics,tracker,advertisement,ad,stats}*", lambda route: route.abort())
                    
                    # 访问页面
                    logger.info(f"访问页面: {url}")
                    await page.goto(url, wait_until='domcontentloaded')
                    
                    # 等待页面加载
                    logger.info("等待页面加载...")
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    
                    # 提取图片URL
                    logger.info("提取图片URL...")
                    image_urls = await page.evaluate("""() => {
                        const images = [];
                        const seen = new Set();
                        
                        // 图片选择器列表
                        const selectors = [
                            'div.imglist img',
                            'div.chapter-img img',
                            'div.rd-article img',
                            'div.manga-image img',
                            'div.comic-page img',
                            'div.chapter-content img',
                            'div.manga-page img',
                            'div.text-center img',
                            'div[class*="chapter"] img',
                            'div[class*="manga"] img',
                            'div[class*="comic"] img',
                            'img[class*="chapter"]',
                            'img[class*="manga"]',
                            'img[class*="comic"]'
                        ];
                        
                        // 图片属性列表
                        const attributes = ['src', 'data-src', 'data-original', 'data-url', 'data-image', 'data-lazyload'];
                        
                        // 有效域名列表
                        const validDomains = [
                            'g-mh.online/hp/',
                            'baozimh.org',
                            'godamanga.online',
                            'mhcdn.xyz',
                            'mangafuna.xyz',
                            'g-mh.org',
                            'g-mh.online',
                            'g-mh.xyz'
                        ];
                        
                        // 无效关键词列表
                        const invalidKeywords = ['cover', 'avatar', 'logo', 'banner', 'ad', 'icon'];
                        
                        // 遍历所有选择器
                        selectors.forEach(selector => {
                            document.querySelectorAll(selector).forEach(img => {
                                // 检查所有可能的属性
                                attributes.forEach(attr => {
                                    const url = img.getAttribute(attr);
                                    if (url && !seen.has(url)) {
                                        // 检查是否是有效的图片URL
                                        const isValid = validDomains.some(domain => url.includes(domain)) &&
                                                      !invalidKeywords.some(keyword => url.toLowerCase().includes(keyword));
                                        
                                        if (isValid) {
                                            images.push(url);
                                            seen.add(url);
                                        }
                                    }
                                });
                            });
                        });
                        
                        return images;
                    }""")
                    
                    logger.info(f"找到 {len(image_urls)} 个图片URL")
                    
                    # 提取导航链接
                    logger.info("提取导航链接...")
                    nav_data = {'prev': None, 'next': None}
                    try:
                        nav_links = await page.evaluate("""() => {
                            const nav = { prev: null, next: null };
                            
                            // 简单的链接文本匹配
                            document.querySelectorAll('a').forEach(link => {
                                const text = link.textContent.trim();
                                const href = link.href;
                                
                                if (href) {
                                    if (text.includes('上一章') || text.includes('上一話') || text.includes('前一章')) {
                                        nav.prev = href;
                                    } else if (text.includes('下一章') || text.includes('下一話') || text.includes('后一章')) {
                                        nav.next = href;
                                    }
                                }
                            });
                            
                            return nav;
                        }""")
                        
                        nav_data = nav_links
                        logger.info(f"导航链接: prev={nav_data.get('prev')}, next={nav_data.get('next')}")
                    except Exception as e:
                        logger.error(f"提取导航链接时出错: {str(e)}")
                    
                    # 处理导航链接
                    prev_chapter = nav_data.get('prev', '').replace('https://g-mh.org/', '') if nav_data.get('prev') else None
                    next_chapter = nav_data.get('next', '').replace('https://g-mh.org/', '') if nav_data.get('next') else None
                    
                    result = {
                        'images': image_urls,
                        'prev_chapter': prev_chapter,
                        'next_chapter': next_chapter,
                        'elapsed_time': time.time() - start_time
                    }
                    
                    return result
                    
                except Exception as e:
                    logger.error(f"页面操作出错: {str(e)}")
                    return {}
                    
                finally:
                    await context.close()
                    await browser.close()
                    
        except Exception as e:
            logger.error(f"提取内容时出错: {str(e)}")
            return {} 