from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import time
from datetime import datetime
import json
import os
from typing import Optional, Dict, Any, List, Tuple, AsyncGenerator
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
from lxml import etree
import cloudscraper
import asyncio
from playwright.async_api import async_playwright
import re
from asyncio import Semaphore, PriorityQueue
from dataclasses import dataclass, field
from typing import Any
import aiojobs
from contextlib import asynccontextmanager
from threading import Lock
from lxml import html
from utils.turnstile_solver import TurnstileSolver
from utils.content_extractor import ContentExtractor
from utils.db_manager import DBManager
from models.manga import MangaInfo, Chapter, Image, Author, Genre, Type, ChapterInfo

from config.settings import (
    DATA_DIR, API_HOST, API_PORT, LOG_CONFIG,
    MONGO_COLLECTION_MANGA, MONGO_COLLECTION_CHAPTERS, MONGO_COLLECTION_IMAGES
)
from utils.browser_manager import BrowserManager
from utils.cache_manager import CacheManager

# 设置日志
logging.basicConfig(
    level=logging.DEBUG,  # 将日志级别设置为DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_CONFIG['filename'], encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 设置其他模块的日志级别
logging.getLogger('urllib3').setLevel(logging.INFO)
logging.getLogger('playwright').setLevel(logging.DEBUG)  # 设置playwright的日志级别为DEBUG
logging.getLogger('cloudscraper').setLevel(logging.DEBUG)  # 设置cloudscraper的日志级别为DEBUG

# 添加默认请求头
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

# 初始化数据库管理器
db_manager = DBManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时的操作
    global scheduler
    scheduler = await aiojobs.create_scheduler(limit=100)
    await scheduler.spawn(process_request_queue())
    
    # 连接数据库
    await db_manager.connect()
    
    yield
    
    # 关闭时的操作
    if scheduler:
        await scheduler.close()
    # 关闭数据库连接
    await db_manager.close()

app = FastAPI(
    title="漫画API",
    description="提供漫画相关的API服务",
    lifespan=lifespan
)

# 启用CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化工具类
browser_manager = BrowserManager()
cache = CacheManager(ttl=86400)  # 默认缓存时间改为24小时

# 定义请求优先级
class Priority:
    HIGH = 1    # 用户直接请求
    MEDIUM = 2  # 预加载请求
    LOW = 3     # 缓存预热请求

@dataclass(order=True)
class PrioritizedRequest:
    priority: int
    timestamp: float
    request: Any = field(compare=False)

# 初始化请求队列和调度器
request_queue = PriorityQueue()
scheduler = None

# 动态并发控制
MAX_CONCURRENT_REQUESTS = 10
MIN_CONCURRENT_REQUESTS = 3
current_concurrent_requests = 5
request_semaphore = Semaphore(current_concurrent_requests)

# 性能监控
request_metrics = {
    'total_requests': 0,
    'successful_requests': 0,
    'failed_requests': 0,
    'average_response_time': 0
}

async def process_request_queue():
    while True:
        try:
            # 获取优先级最高的请求
            prioritized_request = await request_queue.get()
            request = prioritized_request.request
            
            # 动态调整并发数
            global current_concurrent_requests
            if request_metrics['average_response_time'] > 2.0:  # 如果平均响应时间超过2秒
                current_concurrent_requests = max(MIN_CONCURRENT_REQUESTS, current_concurrent_requests - 1)
            elif request_metrics['average_response_time'] < 1.0:  # 如果平均响应时间小于1秒
                current_concurrent_requests = min(MAX_CONCURRENT_REQUESTS, current_concurrent_requests + 1)
            
            # 处理请求
            async with request_semaphore:
                start_time = time.time()
                try:
                    await request['handler'](**request['params'])
                    request_metrics['successful_requests'] += 1
                except Exception as e:
                    request_metrics['failed_requests'] += 1
                    logger.error(f"处理请求时出错: {str(e)}")
                finally:
                    request_metrics['total_requests'] += 1
                    response_time = time.time() - start_time
                    request_metrics['average_response_time'] = (
                        request_metrics['average_response_time'] * (request_metrics['total_requests'] - 1) +
                        response_time
                    ) / request_metrics['total_requests']
                    
        except Exception as e:
            logger.error(f"队列处理器出错: {str(e)}")
            await asyncio.sleep(1)

# 添加预热缓存的函数
async def warm_up_cache():
    """预热缓存"""
    try:
        # 预热首页数据
        home_data = await get_page_content_with_playwright()
        if home_data:
            cache.set('home_page', home_data)
            
        # 从首页数据中获取热门漫画进行预热
        if home_data and 'hot_updates' in home_data:
            for manga in home_data['hot_updates'][:5]:  # 只预热前5个热门漫画
                if 'link' in manga:
                    manga_path = manga['link'].replace('https://g-mh.org/manga/', '')
                    manga_info, chapters = await get_manga_info_with_playwright(f"https://g-mh.org/manga/{manga_path}")
                    if manga_info or chapters:
                        cache.set(f'chapters_{manga_path}', {
                            'manga_info': manga_info,
                            'chapters': chapters
                        })
    except Exception as e:
        logger.error(f"预热缓存时出错: {str(e)}")

async def get_search_results_with_cloudscraper(search_url: str, page: int = 1) -> Tuple[List[dict], dict]:
    try:
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True,
                'custom': 'Chrome/131.0.0.0'
            }
        )
        
        logger.info("使用 Cloudscraper 访问搜索页面...")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: scraper.get(
                search_url,
                allow_redirects=True,
                timeout=30
            )
        )
        
        if response.status_code == 200:
            if '<html' not in response.text.lower():
                logger.warning("响应内容可能不是有效的HTML")
                return [], {'current_page': page, 'page_links': []}
                
            tree = etree.HTML(str(BeautifulSoup(response.content, 'html.parser')))
            
            # 提取漫画列表
            manga_list = []
            manga_items = tree.xpath('//div[contains(@class, "cardlist")]/div[contains(@class, "pb-2")]')
            logger.info(f"找到 {len(manga_items)} 个漫画")
            
            for item in manga_items:
                try:
                    manga_info = {}
                    
                    # 提取标题和链接
                    link_elem = item.xpath('.//a/@href')
                    title_elem = item.xpath('.//h3[contains(@class, "cardtitle")]/text()')
                    
                    if link_elem and title_elem:
                        manga_info['title'] = title_elem[0].strip()
                        manga_info['link'] = link_elem[0]
                        if manga_info['link'] and not manga_info['link'].startswith('http'):
                            manga_info['link'] = urljoin(search_url, manga_info['link'])
                            
                    # 提取封面图片
                    img_elem = item.xpath('.//img/@src')
                    if img_elem:
                        manga_info['cover'] = img_elem[0]
                        if not manga_info['cover'].startswith('http'):
                            manga_info['cover'] = urljoin(search_url, manga_info['cover'])
                            
                    if manga_info.get('title') and manga_info.get('link'):
                        manga_list.append(manga_info)
                        
                except Exception as e:
                    logger.error(f"处理漫画信息时出错: {str(e)}")
                    continue
                    
            # 提取分页信息
            pagination = {'current_page': page, 'page_links': []}
            page_links = tree.xpath('//div[contains(@class, "flex justify-between items-center")]//a')
            
            if page_links:
                pagination['page_links'] = []
                for link in page_links:
                    href = link.get('href')
                    text = ''.join(link.xpath('.//text()')).strip()
                    if href and text:
                        if not href.startswith('http'):
                            href = urljoin(search_url, href)
                        pagination['page_links'].append({
                            'text': text,
                            'link': href
                        })
                        
            return manga_list, pagination
            
        else:
            logger.warning(f"搜索请求失败，状态码: {response.status_code}")
            return [], {'current_page': page, 'page_links': []}
            
    except Exception as e:
        logger.error(f"使用 Cloudscraper 搜索时出错: {str(e)}")
        return [], {'current_page': page, 'page_links': []}

async def get_search_results_with_playwright(search_url: str, page: int = 1) -> Tuple[List[dict], dict]:
    try:
        browser_page = await browser_manager.get_page()
        try:
            logger.info("使用 Playwright 访问搜索页面...")
            await browser_page.goto(search_url, timeout=30000)
            await browser_page.wait_for_load_state('networkidle')
            await browser_page.wait_for_timeout(3000)
            
            content = await browser_page.content()
            if not content:
                logger.error("无法获取页面内容")
                return [], {'current_page': page, 'page_links': []}
                
            tree = etree.HTML(content)
            
            # 提取漫画列表
            manga_list = []
            manga_items = tree.xpath('//div[contains(@class, "cardlist")]/div[contains(@class, "pb-2")]')
            logger.info(f"找到 {len(manga_items)} 个漫画")
            
            for item in manga_items:
                try:
                    manga_info = {}
                    
                    # 提取标题和链接
                    link_elem = item.xpath('.//a/@href')
                    title_elem = item.xpath('.//h3[contains(@class, "cardtitle")]/text()')
                    
                    if link_elem and title_elem:
                        manga_info['title'] = title_elem[0].strip()
                        manga_info['link'] = link_elem[0]
                        if manga_info['link'] and not manga_info['link'].startswith('http'):
                            manga_info['link'] = urljoin(search_url, manga_info['link'])
                            
                    # 提取封面图片
                    img_elem = item.xpath('.//img/@src')
                    if img_elem:
                        manga_info['cover'] = img_elem[0]
                        if not manga_info['cover'].startswith('http'):
                            manga_info['cover'] = urljoin(search_url, manga_info['cover'])
                            
                    if manga_info.get('title') and manga_info.get('link'):
                        manga_list.append(manga_info)
                        
                except Exception as e:
                    logger.error(f"处理漫画信息时出错: {str(e)}")
                    continue
                    
            # 提取分页信息
            pagination = {'current_page': page, 'page_links': []}
            page_links = tree.xpath('//div[contains(@class, "flex justify-between items-center")]//a')
            
            if page_links:
                pagination['page_links'] = []
                for link in page_links:
                    href = link.get('href')
                    text = ''.join(link.xpath('.//text()')).strip()
                    if href and text:
                        if not href.startswith('http'):
                            href = urljoin(search_url, href)
                        pagination['page_links'].append({
                            'text': text,
                            'link': href
                        })
                        
            return manga_list, pagination
            
        finally:
            await browser_manager.close()
            
    except Exception as e:
        logger.error(f"使用 Playwright 搜索时出错: {str(e)}")
        return [], {'current_page': page, 'page_links': []}

@app.get("/api/manga/url")
async def get_manga_by_url(url: str):
    """
    通过指定URL获取漫画列表
    """
    try:
        if not url:
            raise HTTPException(status_code=400, detail="URL参数不能为空")
            
        logger.info(f"接收到请求: /api/manga/url, URL: {url}")
        
        # 尝试从缓存获取
        cache_key = f'manga_url_{url}'
        cached_data = cache.get(cache_key)
        if cached_data:
            return {
                'code': 200,
                'message': 'success',
                'data': cached_data,
                'timestamp': int(datetime.now().timestamp())
            }
        
        # 首先尝试使用 cloudscraper
        manga_list, pagination = await get_search_results_with_cloudscraper(url, 1)
        
        # 如果 cloudscraper 失败，尝试使用 playwright
        if not manga_list:
            logger.info("Cloudscraper失败，尝试使用Playwright")
            manga_list, pagination = await get_search_results_with_playwright(url, 1)
            
        if not manga_list:
            logger.warning("未找到漫画列表")
            return {
                'code': 200,
                'message': '未找到漫画列表',
                'data': {
                    'manga_list': [],
                    'pagination': {'current_page': 1, 'page_links': []}
                },
                'timestamp': int(datetime.now().timestamp())
            }
            
        result_data = {
            'manga_list': manga_list,
            'pagination': pagination
        }
        
        # 缓存结果
        cache.set(cache_key, result_data)
        
        logger.info("成功获取漫画列表")
        return {
            'code': 200,
            'message': 'success',
            'data': result_data,
            'timestamp': int(datetime.now().timestamp())
        }
        
    except Exception as e:
        logger.error(f"获取漫画列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/manga/search/{keyword}")
async def search_manga(keyword: str, page: int = 1):
    """
    通过关键词搜索漫画
    
    参数:
        keyword: 搜索关键词
        page: 页码，默认为1
    """
    try:
        if not keyword:
            raise HTTPException(status_code=400, detail="搜索关键词不能为空")
            
        logger.info(f"接收到搜索请求: keyword={keyword}, page={page}")
        
        # 构建搜索URL
        search_url = f"https://g-mh.org/s/{quote(keyword)}"
        if page > 1:
            search_url = f"{search_url}?page={page}"
            
        # 尝试从缓存获取
        cache_key = f'search_{keyword}_{page}'
        cached_data = cache.get(cache_key)
        if cached_data:
            return {
                'code': 200,
                'message': 'success',
                'data': cached_data,
                'timestamp': int(datetime.now().timestamp())
            }
        
        # 首先尝试使用 cloudscraper
        manga_list, pagination = await get_search_results_with_cloudscraper(search_url, page)
        
        # 如果 cloudscraper 失败，尝试使用 playwright
        if not manga_list:
            logger.info("Cloudscraper失败，尝试使用Playwright")
            manga_list, pagination = await get_search_results_with_playwright(search_url, page)
            
        if not manga_list:
            logger.warning("未找到漫画列表")
            return {
                'code': 200,
                'message': '未找到搜索结果',
                'data': {
                    'manga_list': [],
                    'pagination': {'current_page': page, 'page_links': []},
                    'keyword': keyword
                },
                'timestamp': int(datetime.now().timestamp())
            }
            
        result_data = {
            'manga_list': manga_list,
            'pagination': pagination,
            'keyword': keyword
        }
        
        # 缓存结果
        cache.set(cache_key, result_data)
        
        logger.info(f"搜索成功，找到 {len(manga_list)} 个结果")
        return {
            'code': 200,
            'message': 'success',
            'data': result_data,
            'timestamp': int(datetime.now().timestamp())
        }
        
    except Exception as e:
        logger.error(f"搜索漫画时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class CloudflareSession:
    _instance = None
    _session = None
    _last_verify_time = 0
    _verify_interval = 300  # 5分钟验证一次
    _lock = Lock()
    _max_retries = 3
    _retry_delay = 2  # 重试延迟（秒）
    
    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        self._create_session()
        
    def _create_session(self):
        try:
            self._session = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'darwin',
                    'mobile': False,
                    'desktop': True,
                    'custom': 'Chrome/122.0.0.0',
                    'app_version': '122.0.0.0',
                    'vendor': 'Google Inc.',
                    'renderer': 'WebKit',
                    'os_name': 'macOS',
                    'os_version': '10.15.7'
                },
                delay=10,  # 增加延迟
                interpreter='nodejs'  # 使用nodejs解释器
            )
            
            # 更新请求头
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
                'Connection': 'keep-alive'
            })
            
            self._last_verify_time = time.time()
            logger.info("成功创建Cloudflare会话")
        except Exception as e:
            logger.error(f"创建Cloudflare会话失败: {str(e)}")
            raise
            
    def _verify_session(self):
        current_time = time.time()
        if current_time - self._last_verify_time > self._verify_interval:
            for attempt in range(self._max_retries):
                try:
                    logger.info(f"验证 Cloudflare 会话 (尝试 {attempt + 1}/{self._max_retries})")
                    response = self._session.get('https://g-mh.org/', timeout=30)
                    if response.status_code == 200:
                        self._last_verify_time = current_time
                        logger.info("Cloudflare会话验证成功")
                        return
                    else:
                        logger.warning(f"Cloudflare会话验证失败，状态码: {response.status_code}")
                        if attempt < self._max_retries - 1:
                            logger.info(f"等待 {self._retry_delay} 秒后重试...")
                            time.sleep(self._retry_delay)
                            self._create_session()
                        else:
                            raise Exception(f"会话验证失败，已重试 {self._max_retries} 次")
                except Exception as e:
                    logger.error(f"Cloudflare会话验证出错 (尝试 {attempt + 1}/{self._max_retries}): {str(e)}")
                    if attempt < self._max_retries - 1:
                        logger.info(f"等待 {self._retry_delay} 秒后重试...")
                        time.sleep(self._retry_delay)
                        self._create_session()
                    else:
                        raise
                
    def get_session(self):
        self._verify_session()
        return self._session

    def get(self, url, **kwargs):
        """发送GET请求，带重试机制"""
        for attempt in range(self._max_retries):
            try:
                logger.info(f"发送 GET 请求到 {url} (尝试 {attempt + 1}/{self._max_retries})")
                self._verify_session()
                response = self._session.get(url, timeout=30, **kwargs)
                
                if response.status_code == 200:
                    logger.info("请求成功")
                    return response
                elif response.status_code == 403:
                    logger.warning(f"收到403响应，重新创建会话 (尝试 {attempt + 1}/{self._max_retries})")
                    self._create_session()
                    if attempt < self._max_retries - 1:
                        logger.info(f"等待 {self._retry_delay} 秒后重试...")
                        time.sleep(self._retry_delay)
                        continue
                else:
                    logger.warning(f"请求失败，状态码: {response.status_code} (尝试 {attempt + 1}/{self._max_retries})")
                    if attempt < self._max_retries - 1:
                        logger.info(f"等待 {self._retry_delay} 秒后重试...")
                        time.sleep(self._retry_delay)
                        continue
                    return response
                    
            except Exception as e:
                logger.error(f"请求失败 (尝试 {attempt + 1}/{self._max_retries}): {str(e)}")
                if attempt < self._max_retries - 1:
                    logger.info(f"等待 {self._retry_delay} 秒后重试...")
                    time.sleep(self._retry_delay)
                    self._create_session()
                else:
                    raise

cloudflare_session = CloudflareSession.get_instance()

async def get_page_content_with_cloudscraper():
    """使用 cloudscraper 获取页面内容"""
    try:
        # 设置代理配置
        proxy_config = {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890'
        }
        
        logger.info("创建 cloudscraper 会话...")
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'mobile': False,
                'desktop': True,
                'custom': 'Chrome/122.0.0.0',
                'app_version': '122.0.0.0',
                'vendor': 'Google Inc.',
                'renderer': 'WebKit',
                'os_name': 'macOS',
                'os_version': '10.15.7'
            },
            delay=10,
            interpreter='nodejs'
        )
        
        # 设置代理
        scraper.proxies = proxy_config
        
        # 更新请求头
        scraper.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1'
        })
        
        # 发送请求
        logger.info("使用 cloudscraper 访问网站...")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: scraper.get(
                'https://g-mh.org/',
                allow_redirects=True,
                timeout=60  # 延长超时时间
            )
        )
        
        if response.status_code == 200:
            logger.info("成功获取响应!")
            # 检查响应内容
            content = response.content
            text = response.text
            
            # 打印响应内容的前1000个字符用于调试
            logger.debug(f"响应内容预览: {text[:1000]}")
            
            # 检查响应内容是否包含预期的HTML结构
            if '<html' not in text.lower():
                logger.warning("响应内容可能不是有效的HTML")
                return None
                
            # 解析HTML
            tree = etree.HTML(str(BeautifulSoup(content, 'html.parser')))
            
            # 提取数据
            logger.info("开始提取数据...")
            updates = extract_updates(tree)
            hot_updates = extract_hot_updates(tree)
            popular = extract_popular_manga(tree)
            new_manga = extract_new_manga(tree)
            
            logger.info(f"找到 {len(updates)} 个最新更新")
            logger.info(f"找到 {len(hot_updates)} 个热门更新")
            logger.info(f"找到 {len(popular)} 个人气排行")
            logger.info(f"找到 {len(new_manga)} 个最新上架")
            
            # 返回所有数据
            home_data = {
                'updates': updates,
                'hot_updates': hot_updates,
                'popular_manga': popular,
                'new_manga': new_manga
            }
            
            return home_data
            
        else:
            logger.warning(f"请求失败，状态码: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Cloudscraper 错误: {str(e)}")
        import traceback
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")
        return None

        
async def get_chapter_content_with_playwright(chapter_url: str) -> Tuple[List[str], Optional[str], Optional[str]]:
    """使用 Playwright 获取章节内容"""
    try:
        logger.info("初始化内容提取器...")
        extractor = ContentExtractor(debug=True, headless=True)
        
        result = await extractor.extract_content(chapter_url)
        
        if result:
            images = result.get('images', [])
            if images:
                logger.info(f"成功提取 {len(images)} 张图片")
                return images, result.get('prev_chapter'), result.get('next_chapter')
            else:
                logger.warning("未找到任何图片")
        else:
            logger.warning("提取内容失败")
            
        return [], None, None
            
    except Exception as e:
        logger.error(f"获取章节内容时出错: {str(e)}")
        import traceback
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")
        return [], None, None

    
def normalize_image_url(url: str) -> str:
    """标准化图片URL"""
    if not url:
        return ''
        
    # 如果是相对路径，添加域名
    if url.startswith('/'):
        url = f'https://g-mh.org{url}'
    elif not url.startswith(('http://', 'https://')):
        url = f'https://g-mh.org/{url}'
    
    return url

def normalize_manga_url(url: str) -> str:
    """标准化漫画URL"""
    if not url:
        return ''
        
    # 如果是相对路径，添加域名
    if url.startswith('/'):
        url = f'https://g-mh.org{url}'
    elif not url.startswith(('http://', 'https://')):
        url = f'https://g-mh.org/{url}'
    
    # 确保URL以/manga/开头
    if '/manga/' not in url:
        url = url.replace('https://g-mh.org/', 'https://g-mh.org/manga/')
    
    return url

def extract_updates(tree) -> List[dict]:
    """提取最新更新列表"""
    updates = []
    try:
        # 尝试不同的选择器
        selectors = [
            '//a[@class="slicarda"]',
            '/html/body/main/div/div[4]/div/div[1]/a',
            '/html/body/main/div/div[4]/div/div[2]/a'
        ]
        
        for selector in selectors:
            items = tree.xpath(selector)
            logger.info(f"使用选择器 '{selector}' 找到 {len(items)} 个更新项")
            
            if items:
                for item in items:
                    try:
                        manga_info = {}
                        
                        # 提取链接
                        href = item.get('href')
                        if href:
                            manga_info['link'] = normalize_image_url(href)
                        
                        # 提取标题
                        title = item.xpath('.//h3[@class="slicardtitle"]/text()')
                        if title:
                            manga_info['title'] = title[0].strip()
                        
                        # 提取时间
                        time_text = item.xpath('.//p[@class="slicardtagp"]/text()')
                        if time_text:
                            manga_info['time'] = time_text[0].strip()
                        
                        # 提取章节
                        chapter = item.xpath('.//p[@class="slicardtitlep"]/text()')
                        if chapter:
                            manga_info['chapter'] = chapter[0].strip()
                        
                        # 提取图片
                        img = item.xpath('.//img[@class="slicardimg"]')
                        if img:
                            src = img[0].get('src') or img[0].get('data-src')
                            if src:
                                manga_info['cover'] = normalize_image_url(src)
                        
                        if manga_info.get('title') and manga_info.get('link'):
                            logger.info(f"找到更新: {manga_info['title']}")
                            updates.append(manga_info)
                            
                    except Exception as e:
                        logger.error(f"处理更新项时出错: {str(e)}")
                        continue
                
                # 如果找到了数据就不再尝试其他选择器
                if updates:
                    break
        
        return updates
    except Exception as e:
        logger.error(f"提取更新列表时出错: {str(e)}")
        return []

def extract_hot_updates(tree) -> List[dict]:
    """提取热门更新列表"""
    hot_updates = []
    try:
        # 尝试不同的选择器
        selectors = [
            '/html/body/main/div/div[6]/div[1]/div[2]/div',
            '//div[contains(@class, "hot-updates")]//div[contains(@class, "manga-item")]',
            '//div[contains(@class, "hot-section")]//a'
        ]
        
        for selector in selectors:
            items = tree.xpath(selector)
            logger.info(f"使用选择器 '{selector}' 找到 {len(items)} 个热门更新")
            
            if items:
                for item in items:
                    try:
                        manga_info = {}
                        
                        # 提取链接
                        link_elem = item.xpath('.//a')
                        if link_elem:
                            href = link_elem[0].get('href')
                            if href:
                                manga_info['link'] = normalize_image_url(href)
                        
                        # 提取标题
                        title = item.xpath('.//h3/text()')
                        if title:
                            manga_info['title'] = title[0].strip()
                        
                        # 提取图片
                        img = item.xpath('.//img')
                        if img:
                            src = img[0].get('src') or img[0].get('data-src')
                            if src:
                                manga_info['cover'] = normalize_image_url(src)
                        
                        if manga_info.get('title') and manga_info.get('link'):
                            logger.info(f"找到热门更新: {manga_info['title']}")
                            hot_updates.append(manga_info)
                            
                    except Exception as e:
                        logger.error(f"处理热门更新项时出错: {str(e)}")
                        continue
                
                # 如果找到了数据就不再尝试其他选择器
                if hot_updates:
                    break
        
        return hot_updates
    except Exception as e:
        logger.error(f"提取热门更新列表时出错: {str(e)}")
        return []

def extract_popular_manga(tree) -> List[dict]:
    """提取人气排行列表"""
    popular = []
    try:
        # 尝试不同的选择器
        selectors = [
            '/html/body/main/div/div[6]/div[2]/div[2]/div',
            '//div[contains(@class, "rank-section")]//div[contains(@class, "manga-item")]',
            '//div[contains(@class, "popular-section")]//a'
        ]
        
        for selector in selectors:
            items = tree.xpath(selector)
            logger.info(f"使用选择器 '{selector}' 找到 {len(items)} 个人气排行")
            
            if items:
                for index, item in enumerate(items, 1):
                    try:
                        manga_info = {}
                        
                        # 提取链接
                        link_elem = item.xpath('.//a')
                        if link_elem:
                            href = link_elem[0].get('href')
                            if href:
                                manga_info['link'] = normalize_image_url(href)
                        
                        # 提取标题
                        title = item.xpath('.//h3/text()')
                        if title:
                            manga_info['title'] = title[0].strip()
                        
                        # 提取图片
                        img = item.xpath('.//img')
                        if img:
                            src = img[0].get('src') or img[0].get('data-src')
                            if src:
                                manga_info['cover'] = normalize_image_url(src)
                        
                        # 添加排名
                        manga_info['rank'] = index
                        
                        if manga_info.get('title') and manga_info.get('link'):
                            logger.info(f"找到人气排行: {manga_info['title']} (第{index}名)")
                            popular.append(manga_info)
                            
                    except Exception as e:
                        logger.error(f"处理人气排行项时出错: {str(e)}")
                        continue
                
                # 如果找到了数据就不再尝试其他选择器
                if popular:
                    break
        
        return popular
    except Exception as e:
        logger.error(f"提取人气排行列表时出错: {str(e)}")
        return []

def extract_new_manga(tree) -> List[dict]:
    """提取最新上架列表"""
    new_manga = []
    try:
        # 尝试不同的选择器
        selectors = [
            '/html/body/main/div/div[6]/div[3]/div[2]/div',
            '//div[contains(@class, "new-manga")]//div[contains(@class, "manga-item")]',
            '//div[contains(@class, "new-section")]//a'
        ]
        
        for selector in selectors:
            items = tree.xpath(selector)
            logger.info(f"使用选择器 '{selector}' 找到 {len(items)} 个最新上架")
            
            if items:
                for item in items:
                    try:
                        manga_info = {}
                        
                        # 提取链接
                        link_elem = item.xpath('.//a')
                        if link_elem:
                            href = link_elem[0].get('href')
                            if href:
                                manga_info['link'] = normalize_image_url(href)
                        
                        # 提取标题
                        title = item.xpath('.//h3/text()')
                        if title:
                            manga_info['title'] = title[0].strip()
                        
                        # 提取图片
                        img = item.xpath('.//img')
                        if img:
                            src = img[0].get('src') or img[0].get('data-src')
                            if src:
                                manga_info['cover'] = normalize_image_url(src)
                        
                        if manga_info.get('title') and manga_info.get('link'):
                            logger.info(f"找到最新上架: {manga_info['title']}")
                            new_manga.append(manga_info)
                            
                    except Exception as e:
                        logger.error(f"处理最新上架项时出错: {str(e)}")
                        continue
                
                # 如果找到了数据就不再尝试其他选择器
                if new_manga:
                    break
        
        return new_manga
    except Exception as e:
        logger.error(f"提取最新上架列表时出错: {str(e)}")
        return []

@app.get("/api/manga/home")
async def get_home_page():
    """获取首页数据"""
    try:
        logger.info("接收到首页数据请求")
        
        # 尝试从缓存获取
        cached_data = cache.get('home_page')
        if cached_data:
            logger.info("从缓存返回首页数据")
            return {
                'code': 200,
                'message': 'success',
                'data': cached_data,
                'timestamp': int(datetime.now().timestamp())
            }
        
        # 首先尝试使用 cloudscraper
        logger.info("尝试使用 Cloudscraper 获取数据...")
        home_data = await get_page_content_with_cloudscraper()
        
        if not home_data or not any([
            home_data.get('updates'),
            home_data.get('hot_updates'),
            home_data.get('popular_manga'),
            home_data.get('new_manga')
        ]):
            logger.info("Cloudscraper 未获取到数据，尝试使用 Playwright...")
            # 获取页面
            page = await browser_manager.get_page()
            try:
                # 设置请求拦截
                logger.info("设置资源拦截...")
                await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff2,woff}", lambda route: route.abort())
                await page.route("**/*{analytics,tracker,advertisement,ad,stats}*", lambda route: route.abort())
                
                # 设置请求头
                await page.set_extra_http_headers(DEFAULT_HEADERS)
                
                # 访问页面，使用较短的超时时间
                logger.info("正在访问页面...")
                try:
                    # 只等待 DOM 加载完成
                    response = await page.goto(
                        'https://g-mh.org/',
                        wait_until='domcontentloaded',
                        timeout=15000
                    )
                    
                    if response:
                        logger.info(f"页面响应状态码: {response.status}")
                        logger.info(f"页面响应头: {response.headers}")
                    
                except Exception as e:
                    logger.error(f"访问页面失败: {str(e)}")
                    return {
                        'code': 500,
                        'message': '访问页面失败',
                        'data': None,
                        'timestamp': int(datetime.now().timestamp())
                    }
                
                # 固定等待 2 秒，让页面有时间渲染
                logger.info("等待页面渲染...")
                await page.wait_for_timeout(2000)
                
                # 获取页面内容
                try:
                    logger.info("获取页面内容...")
                    content = await page.content()
                    if not content:
                        raise Exception("页面内容为空")
                    
                    # 保存页面内容用于调试
                    debug_content_path = os.path.join(DATA_DIR, 'debug_home_page.html')
                    with open(debug_content_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.info(f"页面内容已保存到: {debug_content_path}")
                    
                    # 保存页面截图用于调试
                    debug_screenshot_path = os.path.join(DATA_DIR, 'debug_home_page.png')
                    await page.screenshot(path=debug_screenshot_path, full_page=True)
                    logger.info(f"页面截图已保存到: {debug_screenshot_path}")
                    
                    tree = etree.HTML(content)
                    
                    # 提取数据
                    logger.info("开始提取数据...")
                    updates = extract_updates(tree)
                    hot_updates = extract_hot_updates(tree)
                    popular = extract_popular_manga(tree)
                    new_manga = extract_new_manga(tree)
                    
                    logger.info(f"找到 {len(updates)} 个最新更新")
                    logger.info(f"找到 {len(hot_updates)} 个热门更新")
                    logger.info(f"找到 {len(popular)} 个人气排行")
                    logger.info(f"找到 {len(new_manga)} 个最新上架")
                    
                    home_data = {
                        'updates': updates,
                        'hot_updates': hot_updates,
                        'popular_manga': popular,
                        'new_manga': new_manga
                    }
                    
                except Exception as e:
                    logger.error(f"提取数据时出错: {str(e)}")
                    return {
                        'code': 500,
                        'message': '提取数据失败',
                        'data': None,
                        'timestamp': int(datetime.now().timestamp())
                    }
                    
            finally:
                try:
                    await browser_manager.close()
                except Exception as e:
                    logger.error(f"关闭浏览器失败: {str(e)}")
        
        # 检查是否成功获取数据
        if home_data and any([
            home_data.get('updates'),
            home_data.get('hot_updates'),
            home_data.get('popular_manga'),
            home_data.get('new_manga')
        ]):
            # 缓存结果
            logger.info("缓存首页数据...")
            cache.set('home_page', home_data)
            
            return {
                'code': 200,
                'message': 'success',
                'data': home_data,
                'timestamp': int(datetime.now().timestamp())
            }
        else:
            logger.warning("未获取到有效数据")
            return {
                'code': 404,
                'message': '未找到有效数据',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }
            
    except Exception as e:
        logger.error(f"获取首页数据时出错: {str(e)}")
        import traceback
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")
        return {
            'code': 500,
            'message': str(e),
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }

class LazyJSONResponse:
    """支持懒加载的JSON响应类"""
    def __init__(self):
        self.data = {
            'code': 200,
            'message': 'processing',
            'data': {
                'images': [],
                'prev_chapter': None,
                'next_chapter': None
            },
            'timestamp': int(datetime.now().timestamp())
        }
        
    async def add_image(self, image_url: str):
        """添加图片URL到响应中"""
        self.data['data']['images'].append(image_url)
        
    def set_navigation(self, prev_chapter: str = None, next_chapter: str = None):
        """设置上一章和下一章的链接"""
        self.data['data']['prev_chapter'] = prev_chapter
        self.data['data']['next_chapter'] = next_chapter
        
    def set_status(self, code: int, message: str):
        """设置响应状态"""
        self.data['code'] = code
        self.data['message'] = message
        
    async def stream(self) -> AsyncGenerator[str, None]:
        """生成流式JSON响应"""
        yield json.dumps(self.data, ensure_ascii=False)

@app.get("/api/manga/content/{manga_path:path}")
async def get_chapter_content(manga_path: str, request: Request):
    """获取漫画章节内容"""
    try:
        logger.info(f"请求章节: {manga_path}")
        
        # 构建章节页面URL
        chapter_url = f"https://g-mh.org/manga/{manga_path}"
        
        # 尝试从缓存获取
        cache_key = f'content_{manga_path}'
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info("从缓存返回数据")
            return {
                'code': 200,
                'message': 'success', 
                'data': cached_data,
                'timestamp': int(datetime.now().timestamp())
            }
            
        # 首先尝试使用 cloudscraper
        image_urls, prev_chapter, next_chapter = await get_chapter_content_with_cloudscraper(chapter_url)
        
        # 如果 cloudscraper 失败，尝试使用 playwright
        if not image_urls:
            logger.info("Cloudscraper 失败，尝试使用 Playwright...")
            image_urls, prev_chapter, next_chapter = await get_chapter_content_with_playwright(chapter_url)
            
        if not image_urls:
            logger.warning("未找到任何图片")
            return {
                'code': 404,
                'message': '未找到任何图片',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }
            
        # 保存图片信息到MongoDB
        try:
            # 从manga_path中提取manga_id和chapter_id
            path_parts = manga_path.split('/')
            if len(path_parts) >= 2:
                manga_id = path_parts[0]
                chapter_id = path_parts[1]
                
                # 创建图片对象列表
                images = []
                for idx, url in enumerate(image_urls):
                    image = Image(
                        manga_id=manga_id,
                        chapter_id=chapter_id,
                        url=url,
                        order=idx
                    )
                    images.append(image)
                    
                # 批量保存图片信息
                await db_manager.save_images(images)
                logger.info(f"成功保存 {len(images)} 张图片信息到数据库")
                
        except Exception as e:
            logger.error(f"保存图片信息到MongoDB时出错: {str(e)}")
            # 继续处理,不影响API响应
            
        # 构建返回数据
        result_data = {
            'images': image_urls,
            'prev_chapter': prev_chapter,
            'next_chapter': next_chapter
        }
        
        # 缓存结果
        logger.info("缓存章节内容...")
        cache.set(cache_key, result_data)
        
        return {
            'code': 200,
            'message': 'success',
            'data': result_data,
            'timestamp': int(datetime.now().timestamp())
        }
            
    except Exception as e:
        logger.error(f"获取章节内容时出错: {str(e)}")
        import traceback
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")
        return {
            'code': 500,
            'message': str(e),
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }

@app.get("/api/manga/proxy/{manga_path:path}")
async def proxy_manga(manga_path: str):
    """
    代理漫画章节内容
    """
    try:
        logger.info(f"接收到代理请求: {manga_path}")
        
        # 构建章节页面URL
        if manga_path.startswith('manga/'):
            chapter_url = f"https://g-mh.org/{manga_path}"
        else:
            # 检查路径格式
            parts = manga_path.split('/')
            if len(parts) >= 2:  # 格式应该是: zongyoulaoshiyaoqingjiazhang-19262/29403-7911216-85
                chapter_url = f"https://g-mh.org/manga/{manga_path}"
            else:
                chapter_url = f"https://g-mh.org/manga/{manga_path}"
                
        logger.info(f"获取章节页面: {chapter_url}")
        
        # 尝试从缓存获取
        cache_key = f'proxy_{manga_path}'
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info("从缓存返回数据")
            return {
                'code': 200,
                'message': 'success',
                'data': cached_data,
                'timestamp': int(datetime.now().timestamp())
            }
        
        # 首先尝试使用 cloudscraper
        image_urls, prev_chapter, next_chapter = await get_chapter_content_with_cloudscraper(chapter_url)
        
        # 如果 cloudscraper 失败，尝试使用 playwright
        if not image_urls:
            logger.info("Cloudscraper 失败，尝试使用 Playwright...")
            # 获取页面
            page = await browser_manager.get_page()
            
            try:
                # 访问章节页面
                logger.info("正在访问章节页面...")
                response = await page.goto(chapter_url, wait_until='networkidle', timeout=60000)
                
                if response.status != 200:
                    logger.error(f"页面访问失败，状态码: {response.status}")
                    return {
                        'code': response.status,
                        'message': f"页面访问失败，状态码: {response.status}",
                        'data': None,
                        'timestamp': int(datetime.now().timestamp())
                    }
                
                # 等待页面加载完成
                logger.info("等待页面加载完成...")
                await page.wait_for_load_state('networkidle')
                await page.wait_for_timeout(3000)  # 等待3秒确保动态内容加载完成
                
                # 获取页面内容
                logger.info("获取页面内容...")
                content = await page.content()
                
                # 记录页面内容的一部分用于调试
                logger.debug(f"[Playwright] 页面内容片段: {content[:500]}")
                
                # 解析HTML内容
                logger.info("解析HTML内容...")
                tree = etree.HTML(content)
                
                # 提取所有图片URL
                image_urls = []
                
                # 查找所有可能的图片容器
                logger.info("查找图片容器...")
                selectors = [
                    '//div[contains(@class, "chapter-img")]//img',
                    '//div[contains(@class, "rd-article")]//img',
                    '//div[contains(@class, "chapter-content")]//img',
                    '//div[contains(@class, "manga-page")]//img',
                    '//div[contains(@class, "manga-image")]//img',
                    '//div[contains(@class, "comic-page")]//img',
                    '//div[contains(@class, "rd-article-content")]//img',
                    '//div[contains(@class, "rd-article")]//div[contains(@class, "text-center")]//img',
                    '//div[contains(@class, "rd-article")]//p//img',
                    '//div[contains(@class, "rd-article")]//div//img',
                    '//div[contains(@class, "chapter-content")]//div//img',
                    '//div[contains(@class, "chapter-content")]//p//img',
                    '//img[contains(@class, "chapter-img")]',
                    '//img[contains(@class, "manga-image")]',
                    '//img[contains(@class, "comic-image")]'
                ]
                
                for selector in selectors:
                    containers = tree.xpath(selector)
                    logger.info(f"[Playwright] 使用选择器 '{selector}' 找到 {len(containers)} 个图片容器")
                    
                    for img in containers:
                        # 检查多个可能的属性
                        for attr in ['src', 'data-src', 'data-original', 'data-url', 'data-image', 'data-lazyload', 'data-lazy']:
                            src = img.get(attr)
                            if src:
                                logger.info(f"[Playwright] 找到图片URL ({attr}): {src}")
                                if any(domain in src for domain in ['g-mh.online/hp/', 'baozimh.org', 'godamanga.online', 'mhcdn.xyz', 'mangafuna.xyz']) and not ('cover' in src):
                                    if src not in image_urls:  # 去重
                                        image_urls.append(src)
                                        break
                
                logger.info(f"[Playwright] 总共找到 {len(image_urls)} 个有效图片URL")
                
                # 提取上一章和下一章链接
                prev_chapter = None
                next_chapter = None
                
                # 查找导航链接
                logger.info("查找导航链接...")
                nav_selectors = [
                    '//a[contains(@class, "chapter-nav")]',
                    '//a[contains(@class, "prev-chapter")]',
                    '//a[contains(@class, "next-chapter")]',
                    '//a[contains(text(), "上一章")]',
                    '//a[contains(text(), "下一章")]',
                    '//a[contains(@class, "rd-prev-chapter")]',
                    '//a[contains(@class, "rd-next-chapter")]',
                    '//a[contains(@class, "prev")]',
                    '//a[contains(@class, "next")]',
                    '//a[contains(@class, "pre-chapter")]',
                    '//a[contains(@class, "next-chapter")]',
                    '//a[contains(@title, "上一章")]',
                    '//a[contains(@title, "下一章")]'
                ]
                
                nav_links = []
                for selector in nav_selectors:
                    links = tree.xpath(selector)
                    logger.info(f"[Playwright] 使用选择器 '{selector}' 找到 {len(links)} 个导航链接")
                    nav_links.extend(links)
                
                for link in nav_links:
                    href = link.get('href')
                    if href:
                        text = ''.join(link.xpath('.//text()')).strip()
                        title = link.get('title', '')
                        logger.info(f"[Playwright] 导航链接: text='{text}', title='{title}', href='{href}'")
                        if '上一' in text or '上一' in title:
                            prev_chapter = href.replace('https://g-mh.org/', '')
                        elif '下一' in text or '下一' in title:
                            next_chapter = href.replace('https://g-mh.org/', '')
                
            finally:
                await browser_manager.close()
        
        result_data = {
            'images': image_urls,
            'prev_chapter': prev_chapter,
            'next_chapter': next_chapter
        }
        
        # 缓存结果
        if image_urls:  # 只有在找到图片时才缓存
            logger.info("缓存结果...")
            cache.set(cache_key, result_data)
        else:
            logger.warning("未找到任何图片，不缓存结果")
        
        return {
            'code': 200,
            'message': 'success',
            'data': result_data,
            'timestamp': int(datetime.now().timestamp())
        }
            
    except Exception as e:
        logger.error(f"代理章节内容时出错: {str(e)}")
        return {
            'code': 500,
            'message': str(e),
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }

def extract_chapter_number(chapter_link: str) -> int:
    """
    从章节链接中提取章节序号
    例如：从 '/manga/yishijieluyingliaoyushenghuo/32382-046010880-12' 提取 12
    """
    try:
        # 使用正则表达式提取最后的数字
        match = re.search(r'-(\d+)$', chapter_link)
        if match:
            return int(match.group(1))
        return 0
    except Exception:
        return 0

async def get_chapters_from_list_page(chapter_url: str) -> List[dict]:
    """
    从章节列表页面获取章节信息
    """
    try:
        page = await browser_manager.get_page()
        
        try:
            logger.info(f"访问章节列表页面: {chapter_url}")
            
            # 设置请求头
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
            })
            
            # 访问页面
            await page.goto(chapter_url, timeout=30000)
            await page.wait_for_load_state('networkidle')
            await page.wait_for_load_state('domcontentloaded')
            await page.wait_for_load_state('load')
            
            # 等待章节列表加载
            await page.wait_for_timeout(5000)
            
            # 保存页面截图（用于调试）
            screenshot_path = os.path.join(DATA_DIR, 'chapter_list_page.png')
            await page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"章节列表页面截图已保存到: {screenshot_path}")
            
            # 获取页面内容
            content = await page.content()
            
            # 保存页面内容（用于调试）
            content_path = os.path.join(DATA_DIR, 'chapter_list_page.html')
            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"章节列表页面内容已保存到: {content_path}")
            
            tree = etree.HTML(content)
            
            # 提取章节列表
            chapters = []
            # 在 cloudscraper 函数中增加更灵活的选择器

            chapter_selectors = [
                '//*[contains(@class, "chapter")]//a',  # 更宽松的类名匹配
                '//a[contains(@href, "chapter")]',       # 通过链接特征匹配
                '//*[contains(text(), "第")]//ancestor::a' # 通过章节标题文字特征匹配
            ]
            
            for selector in chapter_selectors:
                chapter_list = tree.xpath(selector)
                if chapter_list:
                    logger.info(f"使用选择器 '{selector}' 找到 {len(chapter_list)} 个章节")
                    for chapter in chapter_list:
                        try:
                            chapter_info = {}
                            
                            # 提取章节链接
                            href = chapter.get('href')
                            if href:
                                chapter_info['link'] = urljoin('https://g-mh.org/', href)
                                
                            # 提取章节标题
                            title = chapter.xpath('.//text()')
                            if title:
                                chapter_info['title'] = ''.join(title).strip()
                                
                            if chapter_info.get('link') and chapter_info.get('title'):
                                # 检查是否已存在相同的章节
                                if not any(c['link'] == chapter_info['link'] for c in chapters):
                                    chapters.append(chapter_info)
                                
                        except Exception as e:
                            logger.error(f"处理章节信息时出错: {str(e)}")
                            continue
                    
                    # 如果找到了章节，就不再继续尝试其他选择器
                    if chapters:
                        break
            
            # 按照章节序号排序
            chapters.sort(key=lambda x: extract_chapter_number(x['link']))
            
            return chapters
            
        finally:
            await browser_manager.close()
            
    except Exception as e:
        logger.error(f"从章节列表页面获取章节信息时出错: {str(e)}")
        return []

async def get_manga_info_with_cloudscraper(manga_url: str) -> Tuple[dict, List[dict]]:
    try:
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True,
                'custom': 'Chrome/131.0.0.0'
            }
        )
        
        logger.info(f"使用 Cloudscraper 访问漫画页面: {manga_url}")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: scraper.get(
                manga_url,
                allow_redirects=True,
                timeout=30
            )
        )
        
        if response.status_code == 200:
            if '<html' not in response.text.lower():
                logger.warning("响应内容可能不是有效的HTML")
                return None, []
                
            tree = etree.HTML(str(BeautifulSoup(response.content, 'html.parser')))
            
            # 保存页面内容用于调试
            debug_time = datetime.now().strftime('%Y%m%d_%H%M%S')
            debug_content_path = os.path.join(DATA_DIR, f'debug_manga_page_{debug_time}.html')
            with open(debug_content_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            logger.info(f"页面内容已保存到: {debug_content_path}")
            
            # 提取漫画信息
            manga_info = {}
            
            # 提取封面图片
            cover_img = tree.xpath('/html/body/main/div[2]/div[2]/div[1]/div/div[1]/div[1]/div/div/img')
            if cover_img:
                manga_info['cover'] = normalize_image_url(cover_img[0].get('src', ''))
                
            # 提取标题和状态
            title_elem = tree.xpath('/html/body/main/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/h1/text()')
            status_elem = tree.xpath('/html/body/main/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/h1/span/text()')
            if title_elem:
                manga_info['title'] = title_elem[0].strip()
            if status_elem:
                manga_info['status'] = status_elem[0].strip()
            
            # 提取作者信息
            author_elem = tree.xpath('/html/body/main/div[2]/div[2]/div[2]/div[1]/div[1]/div[2]/a')
            if author_elem:
                author_info = {
                    'names': [],
                    'links': []
                }
                # 获取所有作者标签
                for author in author_elem:
                    name = ''.join(author.xpath('.//text()')).strip()
                    if name:
                        author_info['names'].append(name)
                        author_info['links'].append(urljoin('https://g-mh.org/', author.get('href', '')))
                manga_info['author'] = author_info
            
            # 提取类型信息
            type_elem = tree.xpath('/html/body/main/div[2]/div[2]/div[2]/div[1]/div[1]/div[3]/a')
            if type_elem:
                type_info = {
                    'names': [],
                    'links': []
                }
                # 获取所有类型标签
                for type_tag in type_elem:
                    name = ''.join(type_tag.xpath('.//text()')).strip()
                    if name:
                        type_info['names'].append(name)
                        type_info['links'].append(urljoin('https://g-mh.org/', type_tag.get('href', '')))
                manga_info['type'] = type_info
            
            # 提取简介
            description = tree.xpath('/html/body/main/div[2]/div[2]/div[2]/div[1]/div[1]/p/text()')
            if description:
                manga_info['description'] = description[0].strip()
                
            # 直接从当前页面提取章节列表
            logger.info("尝试从当前页面提取章节列表...")
            chapters = []
            
            # 使用多个选择器尝试获取章节列表
            chapter_selectors = [
                '//div[contains(@class, "chapter-list")]//a',
                '//div[contains(@class, "chapters")]//a',
                '/html/body/main/div/div[3]/div[3]//a',
                '/html/body/main/div/div[3]/div[3]/div[1]//a',
                '//div[contains(@class, "manga-chapters")]//a',
                '//div[contains(@class, "chapter-items")]//a'
            ]
            
            for selector in chapter_selectors:
                logger.info(f"尝试使用选择器: {selector}")
                chapter_elements = await page.query_selector_all(
                    'xpath=//div[contains(@class, "chapter")]//a >> ' +
                    'css=div.chapter-item > a'
            )
                if chapter_elements:
                    logger.info(f"使用选择器 '{selector}' 找到 {len(chapter_elements)} 个章节")
                    for chapter in chapter_elements:
                        try:
                            href = chapter.get('href')
                            title = ''.join(chapter.xpath('.//text()')).strip()
                            
                            if href and title:
                                chapter_info = {
                                    'title': title,
                                    'link': href.replace('https://g-mh.org/manga/', '')
                                }
                                
                                if not any(c['link'] == chapter_info['link'] for c in chapters):
                                    chapters.append(chapter_info)
                                    logger.info(f"找到章节: {title} - {href}")
                        except Exception as e:
                            logger.error(f"处理章节元素时出错: {str(e)}")
                            continue
                    
                    if chapters:  # 如果找到了章节，就跳出循环
                        break
            
            if not chapters:
                logger.warning("在当前页面未找到章节，尝试获取完整章节列表...")
                # 获取漫画ID
                manga_id = manga_url.split('/')[-1]
                logger.info(f"提取到漫画ID: {manga_id}")
                
                # 尝试不同的章节列表URL格式
                chapter_list_urls = [
                    f"https://m.g-mh.org/chapterlist/{manga_id}",
                    # f"https://g-mh.org/manga/{manga_id}/chapters",
                    # f"https://g-mh.org/manga/{manga_id}/all-chapters"
                ]
                
                for chapter_url in chapter_list_urls:
                    try:
                        logger.info(f"尝试访问章节列表URL: {chapter_url}")
                        chapters_response = await loop.run_in_executor(
                            None,
                            lambda: scraper.get(
                                chapter_url,
                                allow_redirects=True,
                                timeout=30
                            )
                        )
                        
                        if chapters_response.status_code == 200:
                            # 保存章节列表内容用于调试
                            debug_chapters_path = os.path.join(DATA_DIR, f'debug_chapters_{debug_time}_{chapter_list_urls.index(chapter_url)}.html')
                            with open(debug_chapters_path, 'w', encoding='utf-8') as f:
                                f.write(chapters_response.text)
                            logger.info(f"章节列表内容已保存到: {debug_chapters_path}")
                            
                            chapters_tree = etree.HTML(str(BeautifulSoup(chapters_response.content, 'html.parser')))
                            
                            # 尝试不同的选择器
                            for selector in chapter_selectors:
                                chapter_elements = chapters_tree.xpath(selector)
                                if chapter_elements:
                                    logger.info(f"在章节列表页面使用选择器 '{selector}' 找到 {len(chapter_elements)} 个章节")
                                    for chapter in chapter_elements:
                                        try:
                                            href = chapter.get('href')
                                            title = ''.join(chapter.xpath('.//text()')).strip()
                                            
                                            if href and title:
                                                chapter_info = {
                                                    'title': title,
                                                    'link': href.replace('https://g-mh.org/manga/', '')
                                                }
                                                
                                                if not any(c['link'] == chapter_info['link'] for c in chapters):
                                                    chapters.append(chapter_info)
                                                    logger.info(f"找到章节: {title} - {href}")
                                        except Exception as e:
                                            logger.error(f"处理章节元素时出错: {str(e)}")
                                            continue
                                    
                                    if chapters:  # 如果找到了章节，就跳出循环
                                        break
                            
                            if chapters:  # 如果找到了章节，就跳出URL循环
                                break
                            
                    except Exception as e:
                        logger.error(f"访问章节列表URL {chapter_url} 时出错: {str(e)}")
                        continue
            
            logger.info(f"总共找到 {len(chapters)} 个章节")
            
            # 按照章节序号排序
            chapters.sort(key=lambda x: extract_chapter_number(x['link']))
            
            # 保存提取结果到调试文件
            debug_result = {
                'manga_info': manga_info,
                'chapters': chapters
            }
            debug_result_file = os.path.join(DATA_DIR, f'debug_manga_result_{debug_time}.json')
            with open(debug_result_file, 'w', encoding='utf-8') as f:
                json.dump(debug_result, f, ensure_ascii=False, indent=2)
            logger.info(f"提取结果已保存到: {debug_result_file}")
            
            return manga_info, chapters
                
        else:
            logger.warning(f"请求失败，状态码: {response.status_code}")
            return None, []
            
    except Exception as e:
        logger.error(f"获取漫画信息时出错: {str(e)}")
        return None, []

async def get_manga_info_with_playwright(manga_url: str) -> Tuple[dict, List[dict]]:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            )
            
            page = await context.new_page()
            logger.info(f"访问漫画页面: {manga_url}")
            
            try:
                response = await page.goto(manga_url, timeout=30000)
                if not response:
                    raise Exception("页面加载失败")
                    
                # 等待页面加载完成
                await page.wait_for_load_state('networkidle')
                # 等待主要内容加载
                await page.wait_for_selector('main', timeout=10000)
                
                # 获取页面内容
                content = await page.content()
                chapters_tree = etree.HTML(str(BeautifulSoup(content, 'html.parser')))
                
                # 使用更灵活的选择器
                chapter_selectors = [
                    '//div[contains(@class, "chapter-list")]//a',  # 方法1：通过class
                    '//main//div[contains(@class, "chapter")]//a',  # 方法2：通过main下的chapter
                    '/html/body/main/div/div[3]/div[3]/div[1]//a',  # 方法3：直接路径
                    '//div[contains(@class, "manga-chapters")]//a'  # 方法4：其他可能的class
                ]
                
                chapters = []
                for selector in chapter_selectors:
                    chapter_list = chapters_tree.xpath(selector)
                    if chapter_list:
                        logger.info(f"使用选择器 '{selector}' 找到 {len(chapter_list)} 个章节")
                        break
                
                if not chapter_list:
                    logger.warning("未找到章节列表，尝试其他方法")
                    # 尝试使用Playwright的选择器
                    chapter_elements = await page.query_selector_all('div.chapter-list a, div.manga-chapters a')
                    if chapter_elements:
                        chapter_list = []
                        for element in chapter_elements:
                            href = await element.get_attribute('href')
                            text = await element.text_content()
                            chapter_list.append({'href': href, 'text': text})
                        logger.info(f"使用Playwright选择器找到 {len(chapter_list)} 个章节")
                
                # 处理章节信息
                for chapter in chapter_list:
                    try:
                        if isinstance(chapter, dict):
                            # 来自Playwright的结果
                            href = chapter['href']
                            title = chapter['text'].strip()
                        else:
                            # 来自XPath的结果
                            href = chapter.get('href')
                            title = ''.join(chapter.xpath('.//text()')).strip()
                        
                        if href and title:
                            chapter_info = {
                                'title': title,
                                'link': href.replace('https://g-mh.org/manga/', '')
                            }
                            
                            if not any(c['link'] == chapter_info['link'] for c in chapters):
                                chapters.append(chapter_info)
                                logger.info(f"找到章节: {title} - {href}")
                                
                    except Exception as e:
                        logger.error(f"处理章节信息时出错: {str(e)}")
                        continue

                # 获取漫画信息
                manga_info = {}
                
                # 等待标题元素加载
                await page.wait_for_selector('h1', timeout=5000)
                title_element = await page.query_selector('h1')
                if title_element:
                    manga_info['title'] = await title_element.text_content()
                    
                # 提取封面图片
                cover_img = chapters_tree.xpath('//div[contains(@class, "manga-cover")]//img | //div[contains(@class, "cover")]//img')
                if cover_img:
                    manga_info['cover'] = normalize_image_url(cover_img[0].get('src', ''))
                    
                # 提取作者信息
                author_info = {
                    'names': [],
                    'links': []
                }
                # 尝试多个可能的作者选择器
                author_selectors = [
                    '//div[contains(text(), "作者：")]/following-sibling::div//a',
                    '//div[contains(text(), "作者:")]/following-sibling::div//a',
                    '//div[contains(text(), "作者")]/following-sibling::div//a',
                    '//div[contains(text(), "作家")]/following-sibling::div//a',
                    '//div[contains(@class, "author")]//a',
                    '//div[contains(@class, "manga-author")]//a',
                    '//div[contains(@class, "info")]//div[contains(text(), "作者")]/following-sibling::div//a'
                ]
                
                # 记录页面内容用于调试
                debug_content = etree.tostring(chapters_tree, encoding='unicode', pretty_print=True)
                logger.debug(f"页面内容:\n{debug_content}")
                
                for selector in author_selectors:
                    logger.debug(f"尝试作者选择器: {selector}")
                    author_elements = chapters_tree.xpath(selector)
                    if author_elements:
                        logger.info(f"使用选择器 '{selector}' 找到 {len(author_elements)} 个作者")
                        for author in author_elements:
                            name = ''.join(author.xpath('.//text()')).strip()
                            href = author.get('href')
                            logger.debug(f"找到作者: name='{name}', href='{href}'")
                            if name:
                                author_info['names'].append(name)
                                if href:
                                    author_info['links'].append(normalize_manga_url(href))
                        if author_info['names']:  # 如果找到了作者信息，就跳出循环
                            break
                            
                manga_info['author'] = author_info
                
                # 提取类型信息
                type_info = {
                    'names': [],
                    'links': []
                }
                # 尝试多个可能的类型选择器
                type_selectors = [
                    '//div[contains(text(), "类型：")]/following-sibling::div//a',
                    '//div[contains(text(), "类型:")]/following-sibling::div//a',
                    '//div[contains(text(), "类型")]/following-sibling::div//a',
                    '//div[contains(@class, "flex")]//div[text()="类型："]//following-sibling::div//a',
                    '//div[contains(@class, "flex")]//div[text()="类型:"]//following-sibling::div//a',
                    '//div[contains(@class, "flex")]//div[contains(text(), "类型")]//following-sibling::div//a',
                    '//div[contains(@class, "flex")]//div[contains(text(), "分类")]//following-sibling::div//a',
                    '//div[contains(@class, "info")]//div[contains(text(), "类型")]//following-sibling::div//a',
                    '//div[contains(@class, "info")]//div[contains(text(), "分类")]//following-sibling::div//a',
                    '//div[contains(@class, "genre")]//a',
                    '//div[contains(@class, "manga-genre")]//a'
                ]
                
                for selector in type_selectors:
                    logger.debug(f"尝试类型选择器: {selector}")
                    type_elements = chapters_tree.xpath(selector)
                    if type_elements:
                        logger.info(f"使用选择器 '{selector}' 找到 {len(type_elements)} 个类型")
                        for type_tag in type_elements:
                            name = ''.join(type_tag.xpath('.//text()')).strip()
                            href = type_tag.get('href')
                            logger.debug(f"找到类型: name='{name}', href='{href}'")
                            if name:
                                type_info['names'].append(name)
                                if href:
                                    type_info['links'].append(normalize_manga_url(href))
                        if type_info['names']:  # 如果找到了类型信息，就跳出循环
                            break
                            
                manga_info['type'] = type_info
                
                # 提取简介
                description_selectors = [
                    '//div[contains(@class, "flex")]//p[string-length(text()) > 10]/text()',
                    '//div[contains(@class, "description")]//p[string-length(text()) > 10]/text()',
                    '//div[contains(@class, "summary")]//p[string-length(text()) > 10]/text()',
                    '//div[contains(@class, "manga-description")]//p[string-length(text()) > 10]/text()',
                    '//div[contains(@class, "info")]//div[contains(text(), "简介") or contains(text(), "描述")]//following-sibling::div//p/text()'
                ]
                
                for selector in description_selectors:
                    description = chapters_tree.xpath(selector)
                    if description:
                        manga_info['description'] = description[0].strip()
                        break
                
                # 提取状态
                status_selectors = [
                    '//h1//span/text()',
                    '//div[contains(@class, "status")]//text()',
                    '//div[contains(@class, "info")]//div[contains(text(), "状态")]//following-sibling::div//text()'
                ]
                
                for selector in status_selectors:
                    status_element = chapters_tree.xpath(selector)
                    if status_element:
                        manga_info['status'] = status_element[0].strip()
                        break
                
                # 按照章节序号排序
                chapters.sort(key=lambda x: extract_chapter_number(x['link']))
                
                return manga_info, chapters

            except Exception as e:
                logger.error(f"获取漫画信息时出错: {str(e)}")
                raise
            finally:
                await page.close()
                
    except Exception as e:
        logger.error(f"Playwright操作出错: {str(e)}")
        return None, []

@app.get("/api/manga/chapter/{manga_path}")
async def get_manga_chapters(manga_path: str):
    try:
        # 获取章节列表
        chapters = await get_manga_info_with_cloudscraper(f"https://g-mh.org/manga/{manga_path}")
        
        if not chapters[0] and not chapters[1]:
            chapters = await get_manga_info_with_playwright(f"https://g-mh.org/manga/{manga_path}")
        
        manga_info, chapter_list = chapters
        
        if not manga_info and not chapter_list:
            return {"code": 404, "message": "未找到漫画信息", "data": None}
            
        # 创建 manga_info 对象
        manga = MangaInfo(
            manga_id=manga_path,
            title=manga_info.get("title", "").replace("連載中", "").strip(),
            description=manga_info.get("description", ""),
            status=manga_info.get("status", "連載中"),
            author=Author(**manga_info.get("author", {"names": [], "links": []})),
            type=Genre(**manga_info.get("type", {"names": [], "links": []})),
            cover=manga_info.get("cover", "")
        )
        
        # 保存 manga 信息
        await db_manager.save_manga(manga, manga_path)
        
        # 删除旧的章节数据
        await db_manager.db[MONGO_COLLECTION_CHAPTERS].delete_many({"manga_id": manga_path})
        
        # 保存新的章节数据
        for i, chapter in enumerate(chapter_list, 1):
            chapter_data = ChapterInfo(
                manga_id=manga_path,
                chapter_id=f"{manga_path}_chapter_{i}",
                title=chapter.get("title", ""),
                link=chapter.get("link", "").replace("/manga/", ""),
                order=i
            )
            await db_manager.save_chapter(chapter_data)
        
        result = {
            "manga_info": manga.dict(),
            "chapters": chapter_list
        }
        
        return {"code": 200, "message": "success", "data": result}
    except Exception as e:
        logger.error(f"Error in get_manga_chapters: {str(e)}")
        return {"code": 500, "message": str(e)}

@app.get("/api/stats")
async def get_server_stats():
    """获取服务器性能统计信息"""
    return {
        'code': 200,
        'message': 'success',
        'data': {
            'metrics': request_metrics,
            'concurrent_requests': {
                'current': current_concurrent_requests,
                'max': MAX_CONCURRENT_REQUESTS,
                'min': MIN_CONCURRENT_REQUESTS
            },
            'queue_size': request_queue.qsize(),
            'cache_stats': cache.get_stats()
        },
        'timestamp': int(datetime.now().timestamp())
    }

# 修改CacheManager类以支持命中统计
class CacheManager:
    def __init__(self, ttl=86400):  # 默认缓存时间改为24小时
        self.cache = {}
        self.ttl = ttl
        self.hits = 0
        self.misses = 0
        self.lock = Lock()
        
    def get(self, key: str) -> Any:
        """获取缓存数据，带过期检查"""
        with self.lock:
            if key in self.cache:
                data, timestamp = self.cache[key]
                if time.time() - timestamp <= self.ttl:
                    self.hits += 1
                    logger.debug(f"缓存命中: {key}")
                    return data
                else:
                    logger.debug(f"缓存过期: {key}")
                    del self.cache[key]
            self.misses += 1
            logger.debug(f"缓存未命中: {key}")
            return None

    def set(self, key: str, value: Any) -> None:
        """设置缓存数据"""
        with self.lock:
            self.cache[key] = (value, time.time())
            logger.debug(f"设置缓存: {key}")

    def clear(self) -> None:
        """清除所有缓存"""
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
            logger.info("清除所有缓存")
            
    def remove_expired(self) -> None:
        """移除过期的缓存项"""
        with self.lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, timestamp) in self.cache.items()
                if current_time - timestamp > self.ttl
            ]
            for key in expired_keys:
                del self.cache[key]
            if expired_keys:
                logger.info(f"移除 {len(expired_keys)} 个过期缓存项")
                
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            return {
                'size': len(self.cache),
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': f"{hit_rate:.2f}%",
                'total_requests': total_requests
            }
            
    async def warm_up(self):
        """预热缓存"""
        try:
            logger.info("开始预热缓存...")
            # 获取首页数据
            home_data = await get_page_content_with_cloudscraper()
            if not home_data:
                logger.info("使用 Cloudscraper 预热失败，尝试使用 Playwright...")
                home_data = await get_page_content_with_playwright()
                
            if home_data and any([
                home_data.get('updates'),
                home_data.get('hot_updates'),
                home_data.get('popular_manga'),
                home_data.get('new_manga')
            ]):
                self.set('home_page', home_data)
                logger.info("缓存预热成功")
                
                # 预热热门漫画数据
                hot_updates = home_data.get('hot_updates', [])
                for manga in hot_updates[:5]:  # 只预热前5个热门漫画
                    if 'link' in manga:
                        manga_path = manga['link'].replace('https://g-mh.org/manga/', '')
                        manga_info, chapters = await get_manga_info_with_cloudscraper(f"https://g-mh.org/manga/{manga_path}")
                        if manga_info or chapters:
                            self.set(f'chapters_{manga_path}', {
                                'manga_info': manga_info,
                                'chapters': chapters
                            })
                            logger.info(f"预热漫画数据: {manga_path}")
            else:
                logger.warning("缓存预热失败：未获取到有效数据")
        except Exception as e:
            logger.error(f"缓存预热时出错: {str(e)}")

# 添加中间件来记录请求处理时间
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

async def get_chapter_content_with_cloudscraper(chapter_url: str) -> Tuple[List[str], Optional[str], Optional[str]]:
    try:
        # 设置代理配置
        proxy_config = {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890'
        }
        logger.info(f"使用代理配置: {proxy_config}")

        # 创建 cloudscraper 会话
        logger.info("创建 cloudscraper 会话...")
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'mobile': False,
                'custom': 'Chrome/122.0.0.0'
            },
            delay=10
        )
        scraper.proxies = proxy_config
        
        # 设置请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"'
        }
        scraper.headers.update(headers)
        logger.info(f"设置请求头: {headers}")

        # 首先尝试直接请求
        logger.info(f"开始请求章节页面: {chapter_url}")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: scraper.get(chapter_url))

        # 检查是否需要解决 Turnstile
        if response.status_code == 403 or 'cf_clearance' not in scraper.cookies:
            logger.info("检测到需要解决 Turnstile 验证...")
            # 创建 Turnstile 解决器
            solver = TurnstileSolver(headless=True, debug=True)  # 确保使用无头模式
            
            # 获取验证结果
            result = await solver.solve(chapter_url)
            
            # 注释掉有问题的代码
            # if not result or 'cf_clearance' not in result.get('cookies', {}):
            #     logger.warning("Turnstile 验证失败")
            #     return [], None, None
                
            # # 更新 cookies 和 user agent
            # for name, value in result['cookies'].items():
            #     scraper.cookies.set(name, value)
            # scraper.headers['User-Agent'] = result['user_agent']
            
            # 直接返回空结果，让程序转向使用 Playwright
            return [], None, None

        logger.info(f"Cloudscraper 响应状态码: {response.status_code}")
        logger.info(f"响应头: {dict(response.headers)}")
        logger.info(f"响应内容预览: {response.text[:1000]}")

        if response.status_code == 200:
            # 保存响应内容用于调试
            debug_file = os.path.join(DATA_DIR, 'cloudscraper_chapter_debug.html')
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            logger.info(f"调试内容已保存到: {debug_file}")

            # 使用 lxml 解析 HTML
            logger.info("开始解析HTML内容...")
            tree = html.fromstring(response.content)
            
            # 提取图片 URL
            logger.info("开始提取图片URL...")
            image_elements = tree.xpath('//div[@class="imglist"]//img')
            image_urls = []
            for img in image_elements:
                img_url = img.get('src', '')
                if img_url:
                    image_urls.append(img_url)
                    logger.info(f"找到图片URL: {img_url}")
            logger.info(f"总共找到 {len(image_urls)} 张图片")

            # 提取导航链接
            logger.info("开始提取导航链接...")
            prev_chapter = None
            next_chapter = None
            
            prev_link = tree.xpath('//a[@class="prev"]/@href')
            if prev_link:
                prev_chapter = prev_link[0].replace('https://g-mh.org/', '')
                logger.info(f"找到上一章链接: {prev_chapter}")

            next_link = tree.xpath('//a[@class="next"]/@href')
            if next_link:
                next_chapter = next_link[0].replace('https://g-mh.org/', '')
                logger.info(f"找到下一章链接: {next_chapter}")

            # 保存提取结果到调试文件
            debug_result = {
                'image_urls': image_urls,
                'prev_chapter': prev_chapter,
                'next_chapter': next_chapter
            }
            debug_result_file = os.path.join(DATA_DIR, 'cloudscraper_chapter_result.json')
            with open(debug_result_file, 'w', encoding='utf-8') as f:
                json.dump(debug_result, f, ensure_ascii=False, indent=2)
            logger.info(f"提取结果已保存到: {debug_result_file}")

            return image_urls, prev_chapter, next_chapter
        else:
            logger.warning(f"请求失败，状态码: {response.status_code}")
            logger.warning(f"错误响应内容: {response.text[:500]}")
            return [], None, None

    except Exception as e:
        logger.error(f"获取章节内容时出错: {str(e)}")
        import traceback
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")
        return [], None, None

async def get_chapter_content_with_playwright(chapter_url: str) -> Tuple[List[str], Optional[str], Optional[str]]:
    """使用 Playwright 获取章节内容"""
    try:
        logger.info("初始化内容提取器...")
        extractor = ContentExtractor(debug=True, headless=True)
        
        result = await extractor.extract_content(chapter_url)
        
        if result:
            images = result.get('images', [])
            if images:
                logger.info(f"成功提取 {len(images)} 张图片")
                return images, result.get('prev_chapter'), result.get('next_chapter')
            else:
                logger.warning("未找到任何图片")
        else:
            logger.warning("提取内容失败")
            
        return [], None, None
            
    except Exception as e:
        logger.error(f"获取章节内容时出错: {str(e)}")
        import traceback
        logger.error(f"错误堆栈:\n{traceback.format_exc()}")
        return [], None, None

# 添加新的API端点用于从MongoDB获取数据
@app.get("/api/db/manga/{manga_id}")
async def get_manga_from_db(manga_id: str):
    """从数据库获取漫画信息"""
    try:
        manga = await db_manager.get_manga(manga_id)
        if not manga:
            return {
                'code': 404,
                'message': '未找到漫画',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }
            
        chapters = await db_manager.get_chapters(manga_id)
        
        return {
            'code': 200,
            'message': 'success',
            'data': {
                'manga_info': manga,
                'chapters': chapters
            },
            'timestamp': int(datetime.now().timestamp())
        }
        
    except Exception as e:
        logger.error(f"从数据库获取漫画信息时出错: {str(e)}")
        return {
            'code': 500,
            'message': str(e),
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }

@app.get("/api/db/chapter/{chapter_id}/images")
async def get_chapter_images_from_db(chapter_id: str):
    """从数据库获取章节图片"""
    try:
        images = await db_manager.get_chapter_images(chapter_id)
        if not images:
            return {
                'code': 404,
                'message': '未找到章节图片',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }
            
        return {
            'code': 200,
            'message': 'success',
            'data': {
                'images': images
            },
            'timestamp': int(datetime.now().timestamp())
        }
        
    except Exception as e:
        logger.error(f"从数据库获取章节图片时出错: {str(e)}")
        return {
            'code': 500,
            'message': str(e),
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }

@app.get("/api/db/search")
async def search_manga_in_db(
    keyword: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
):
    """在数据库中搜索漫画"""
    try:
        skip = (page - 1) * limit
        manga_list = await db_manager.search_manga(keyword, skip, limit)
        
        return {
            'code': 200,
            'message': 'success',
            'data': {
                'manga_list': manga_list,
                'page': page,
                'limit': limit
            },
            'timestamp': int(datetime.now().timestamp())
        }
        
    except Exception as e:
        logger.error(f"搜索漫画时出错: {str(e)}")
        return {
            'code': 500,
            'message': str(e),
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }

@app.get("/api/db/manga/{manga_path}")
async def get_manga_from_db(manga_path: str):
    """从数据库获取漫画信息"""
    try:
        # 首先尝试通过 manga_id 查找
        manga = await db_manager.get_manga(manga_path)
        if not manga:
            # 如果找不到，尝试通过路径名查找
            manga = await db_manager.get_manga_by_path(manga_path)
            if not manga:
                return {
                    'code': 404,
                    'message': '未找到漫画',
                    'data': None,
                    'timestamp': int(datetime.now().timestamp())
                }
            
        chapters = await db_manager.get_chapters(manga.manga_id)
        
        return {
            'code': 200,
            'message': 'success',
            'data': {
                'manga_info': manga.dict(),
                'chapters': [chapter.dict() for chapter in chapters]
            },
            'timestamp': int(datetime.now().timestamp())
        }
        
    except Exception as e:
        logger.error(f"从数据库获取漫画信息时出错: {str(e)}")
        return {
            'code': 500,
            'message': str(e),
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }

@app.get("/api/manga/images/{manga_id}/{chapter_id}")
async def get_manga_images(manga_id: str, chapter_id: str):
    """获取漫画章节图片"""
    try:
        logger.info(f"获取章节图片: {manga_id}/{chapter_id}")
        
        # 从数据库获取图片信息
        images = await db_manager.get_chapter_images(f"{manga_id}_{chapter_id}")
        
        if not images:
            logger.warning("未找到图片信息")
            return {
                'code': 404,
                'message': '未找到图片信息',
                'data': None
            }
            
        # 按照顺序排序图片
        sorted_images = sorted(images, key=lambda x: x.order)
        
        # 构建返回数据
        result = {
            'images': [image.url for image in sorted_images]
        }
        
        return {
            'code': 200,
            'message': 'success',
            'data': result
        }
            
    except Exception as e:
        logger.error(f"获取章节图片时出错: {str(e)}")
        return {
            'code': 500,
            'message': str(e),
            'data': None
        }

if __name__ == "__main__":
    # 确保数据目录存在
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 启动服务器
    import sys
    import pathlib
    
    file_path = pathlib.Path(__file__).absolute()
    sys.path.append(str(file_path.parent))
    
    uvicorn.run(
        "fastapi_server:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
        reload_dirs=[str(file_path.parent)]
    ) 