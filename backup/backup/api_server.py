from flask import Flask, jsonify, Response
from flask_cors import CORS
import json
import os
from datetime import datetime
import logging
import time
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright
import random
import re
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
import html
import asyncio
from lxml import html as lxml_html
from quart import Quart, jsonify as quart_jsonify, Response, current_app, request, make_response
from quart_cors import cors
import aiofiles
from lxml import etree
import hypercorn.asyncio
from hypercorn.config import Config
import socket
import sys
import ssl
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.ssl_ import create_urllib3_context
from threading import Lock
import urllib.parse
from cachetools import TTLCache
from typing import List, Dict, Any, Optional

from config.settings import (
    DATA_DIR, LATEST_UPDATES_FILE, LATEST_MANGA_DETAILS_FILE,
    API_HOST, API_PORT, LOG_CONFIG, PROXY_CONFIG
)
from utils.browser_manager import BrowserManager
from utils.response_formatter import ResponseFormatter
from utils.cache_manager import CacheManager
from utils.error_handler import handle_exceptions, NotFoundError, BadRequestError, ServerError
from extractors.manga_extractor import MangaExtractor
from extractors.chapter_extractor import ChapterExtractor
from models.manga import MangaInfo, ChapterInfo, HomePageData, ApiResponse

# 设置日志
logging.basicConfig(
    level=getattr(logging, LOG_CONFIG['level']),
    format=LOG_CONFIG['format'],
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_CONFIG['filename'], encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

app = Quart(__name__)
app = cors(app)  # 启用CORS支持

# 初始化工具类
browser_manager = BrowserManager()
response = ResponseFormatter()
cache = TTLCache(maxsize=100, ttl=1800)  # 30分钟缓存

async def log_request(endpoint, method, ip):
    """记录请求信息"""
    logger.info(f"接收到请求: {endpoint}")
    logger.info(f"请求方法: {method}")
    logger.info(f"请求IP: {ip}")

@app.route('/api/manga/updates', methods=['GET', 'POST'])
@handle_exceptions
async def get_manga_updates():
    logger.info("接收到请求: /api/manga/updates")
    
    # 尝试从缓存获取
    cached_data = cache.get('manga_updates')
    if cached_data:
        return response.success(cached_data)
    
    if not os.path.exists(LATEST_UPDATES_FILE):
        raise NotFoundError('更新数据未找到')
        
    async with aiofiles.open(LATEST_UPDATES_FILE, 'r', encoding='utf-8') as f:
        content = await f.read()
        data = json.loads(content)
        logger.info("成功读取更新数据")
        
        # 缓存数据
        cache.set('manga_updates', data)
        return response.success(data)

@app.route('/api/manga/details', methods=['GET', 'POST'])
@handle_exceptions
async def get_manga_details():
    logger.info("接收到请求: /api/manga/details")
    
    # 尝试从缓存获取
    cached_data = cache.get('manga_details')
    if cached_data:
        return response.success(cached_data)
    
    if not os.path.exists(LATEST_MANGA_DETAILS_FILE):
        raise NotFoundError('漫画详情数据未找到')
        
    async with aiofiles.open(LATEST_MANGA_DETAILS_FILE, 'r', encoding='utf-8') as f:
        content = await f.read()
        data = json.loads(content)
        logger.info("成功读取漫画详情数据")
        
        # 缓存数据
        cache.set('manga_details', data)
        return response.success(data)

@app.route('/api/manga/history/updates/<timestamp>', methods=['GET', 'POST'])
async def get_history_updates(timestamp):
    try:
        logger.info(f"接收到请求: /api/manga/history/updates/{timestamp}")
        
        history_file = os.path.join(DATA_DIR, f'updates_{timestamp}.json')
        
        if not os.path.exists(history_file):
            logger.warning(f"历史更新文件不存在: {history_file}")
            return quart_jsonify({
                'code': 404,
                'message': f'未找到时间戳为 {timestamp} 的历史更新数据',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        async with aiofiles.open(history_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            logger.info(f"成功读取历史更新数据: {timestamp}")
            
        return quart_jsonify(data)
        
    except Exception as e:
        logger.error(f"获取历史更新数据时出错: {str(e)}", exc_info=True)
        return quart_jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/history/details/<timestamp>', methods=['GET', 'POST'])
async def get_history_details(timestamp):
    try:
        logger.info(f"接收到请求: /api/manga/history/details/{timestamp}")
        
        history_file = os.path.join(DATA_DIR, f'manga_details_{timestamp}.json')
        
        if not os.path.exists(history_file):
            logger.warning(f"历史详情文件不存在: {history_file}")
            return quart_jsonify({
                'code': 404,
                'message': f'未找到时间戳为 {timestamp} 的历史详情数据',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        async with aiofiles.open(history_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            logger.info(f"成功读取历史详情数据: {timestamp}")
            
        return quart_jsonify(data)
        
    except Exception as e:
        logger.error(f"获取历史详情数据时出错: {str(e)}", exc_info=True)
        return quart_jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/list/updates', methods=['GET', 'POST'])
async def list_updates_history():
    try:
        logger.info(f"接收到请求: /api/manga/list/updates")
        
        # 获取所有更新历史数据文件
        history_files = [f for f in os.listdir(DATA_DIR) if f.startswith('updates_') and f.endswith('.json')]
        history_files.sort(reverse=True)  # 按时间戳降序排序
        
        history_list = []
        for filename in history_files:
            timestamp = filename.replace('updates_', '').replace('.json', '')
            history_list.append({
                'timestamp': timestamp,
                'filename': filename
            })
            
        logger.info(f"找到 {len(history_list)} 个历史更新文件")
        return quart_jsonify({
            'code': 200,
            'message': 'success',
            'data': history_list,
            'timestamp': int(datetime.now().timestamp())
        })
        
    except Exception as e:
        logger.error(f"获取更新历史列表时出错: {str(e)}", exc_info=True)
        return quart_jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/list/details', methods=['GET', 'POST'])
async def list_details_history():
    try:
        logger.info(f"接收到请求: /api/manga/list/details")
        
        # 获取所有漫画详情历史数据文件
        history_files = [f for f in os.listdir(DATA_DIR) if f.startswith('manga_details_') and f.endswith('.json')]
        history_files.sort(reverse=True)  # 按时间戳降序排序
        
        history_list = []
        for filename in history_files:
            timestamp = filename.replace('manga_details_', '').replace('.json', '')
            history_list.append({
                'timestamp': timestamp,
                'filename': filename
            })
            
        logger.info(f"找到 {len(history_list)} 个历史详情文件")
        return quart_jsonify({
            'code': 200,
            'message': 'success',
            'data': history_list,
            'timestamp': int(datetime.now().timestamp())
        })
        
    except Exception as e:
        logger.error(f"获取详情历史列表时出错: {str(e)}", exc_info=True)
        return quart_jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/latest', methods=['GET', 'POST'])
async def get_latest_data():
    try:
        logger.info(f"接收到请求: /api/manga/latest")
        
        # 检查文件是否存在
        if not os.path.exists(LATEST_UPDATES_FILE):
            logger.warning(f"最新更新文件不存在: {LATEST_UPDATES_FILE}")
            return quart_jsonify({
                'code': 404,
                'message': '更新数据未找到',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        if not os.path.exists(LATEST_MANGA_DETAILS_FILE):
            logger.warning(f"最新详情文件不存在: {LATEST_MANGA_DETAILS_FILE}")
            return quart_jsonify({
                'code': 404,
                'message': '漫画详情数据未找到',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        # 读取数据
        async with aiofiles.open(LATEST_UPDATES_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            updates_data = json.loads(content)
            
        async with aiofiles.open(LATEST_MANGA_DETAILS_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            details_data = json.loads(content)
            
        # 合并数据
        response_data = {
            'code': 200,
            'message': 'success',
            'data': {
                'updates': updates_data.get('data', {}),
                'details': details_data.get('data', {})
            },
            'timestamp': int(datetime.now().timestamp())
        }
        
        logger.info("成功读取并合并最新数据")
        return quart_jsonify(response_data)
        
    except Exception as e:
        logger.error(f"获取最新数据时出错: {str(e)}", exc_info=True)
        return quart_jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/home', methods=['GET', 'POST'])
@handle_exceptions
async def get_home_page():
    # 尝试从缓存获取
    cached_data = cache.get('home_page')
    if cached_data:
        return response.success(cached_data)
    
    # 首先尝试使用 cloudscraper
    links = await get_page_content_with_cloudscraper()
    
    # 如果 cloudscraper 失败，尝试使用 playwright
    if not links:
        links = await get_page_content_with_playwright()
        
    if not links:
        raise ServerError('无法获取首页数据')
        
    # 缓存数据
    cache.set('home_page', links)
    return response.success(links)

@app.route('/api/manga/chapter/<path:manga_path>', methods=['GET', 'POST'])
@handle_exceptions
async def get_chapter_info(manga_path):
    # 验证路径
    path_parts = manga_path.split('/')
    if len(path_parts) != 2:
        raise BadRequestError('无效的章节路径')
        
    manga_id = path_parts[0]
    chapter_id = path_parts[1]
    logger.info(f"获取章节信息: manga_id={manga_id}, chapter_id={chapter_id}")
    
    # 尝试从缓存获取
    cache_key = f'chapter_{manga_path}'
    cached_data = cache.get(cache_key)
    if cached_data:
        return response.success(cached_data)
    
    # 获取页面
    page = await browser_manager.get_page()
    
    try:
        # 访问章节页面
        chapter_url = f'https://g-mh.org/manga/{manga_path}'
        await page.goto(chapter_url, wait_until='networkidle', timeout=60000)
        
        # 提取数据
        chapter_data = await ChapterExtractor.extract_chapter_data(page)
        
        # 缓存数据
        cache.set(cache_key, chapter_data)
        return response.success(chapter_data)
        
    finally:
        await browser_manager.close()

async def get_page_content_with_cloudscraper():
    try:
        # SSL验证选项
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'mobile': False
            }
        )
        
        logger.info("使用 cloudscraper 访问网站...")
        # 使用 asyncio 运行同步代码
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: scraper.get('https://g-mh.org/'))
        
        if response.status_code == 200:
            logger.info("成功获取响应!")
            if '<html' not in response.text.lower():
                logger.warning("响应内容可能不是有效的HTML")
                return None
                
            # 解析HTML
            tree = etree.HTML(str(BeautifulSoup(response.content, 'html.parser')))
            
            # 提取数据
            home_data = HomePageData(
                updates=[MangaInfo(**info) for info in MangaExtractor.extract_updates(tree)],
                popular_manga=[MangaInfo(**info) for info in MangaExtractor.extract_popular_manga(tree)],
                new_manga=[MangaInfo(**info) for info in MangaExtractor.extract_new_manga(tree)],
                hot_updates=[MangaInfo(**info) for info in MangaExtractor.extract_hot_updates(tree)]
            )
            
            return home_data
        else:
            logger.warning(f"请求失败，状态码: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Cloudscraper 错误: {str(e)}")
        return None

async def get_page_content_with_playwright():
    try:
        page = await browser_manager.get_page()
        
        try:
            logger.info("使用 Playwright 访问网站...")
            response = await page.goto('https://g-mh.org/', timeout=30000)
            
            if response:
                logger.info(f"Playwright 响应状态码: {response.status}")
            
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(3000)
            
            # 获取页面内容
            content = await page.content()
            
            if not content:
                logger.error("无法获取页面内容")
                return quart_jsonify({
                    "code": 500,
                    "message": "无法获取页面内容",
                    "data": None,
                    "timestamp": int(time.time())
                }), 500
            
            # 输出页面内容以进行调试
            logger.info("页面内容:")
            logger.info(content)
            
            # 解析HTML
            tree = etree.HTML(content)
            
            # 提取数据
            home_data = HomePageData(
                updates=[MangaInfo(**info) for info in MangaExtractor.extract_updates(tree)],
                popular_manga=[MangaInfo(**info) for info in MangaExtractor.extract_popular_manga(tree)],
                new_manga=[MangaInfo(**info) for info in MangaExtractor.extract_new_manga(tree)],
                hot_updates=[MangaInfo(**info) for info in MangaExtractor.extract_hot_updates(tree)]
            )
            
            return home_data
                    
        finally:
            await browser_manager.close()
                    
    except Exception as e:
        logger.error(f"Playwright 错误: {str(e)}")
        return None

@app.route('/api/manga/proxy/<path:image_path>', methods=['GET'])
async def proxy_image(image_path):
    try:
        app.logger.info(f"Received proxy request for path: {image_path}")
        
        # 构建章节页面URL
        chapter_url = f"https://g-mh.org/manga/{image_path}"
        app.logger.info(f"Fetching chapter page: {chapter_url}")
        
        # 获取页面
        page = await browser_manager.get_page()
        
        try:
            # 访问章节页面
            await page.goto(chapter_url, wait_until='networkidle', timeout=60000)
            
            # 等待页面加载完成
            await page.wait_for_load_state('networkidle')
            
            # 获取页面内容
            content = await page.content()
            
            # 解析HTML内容
            soup = BeautifulSoup(content, 'html.parser')
            
            # 提取所有图片URL（使用集合去重）
            image_urls = []
            seen_urls = set()
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if ('g-mh.online/hp/' in src or 'baozimh.org' in src) and not ('cover' in src):
                    if src not in seen_urls:
                        image_urls.append(src)
                        seen_urls.add(src)
            
            # 提取上一章和下一章链接
            prev_chapter = None
            next_chapter = None
            for link in soup.find_all('a'):
                text = link.get_text()
                href = link.get('href', '')
                if '上一' in text and href:
                    # 从完整URL中提取相对路径
                    prev_chapter = href.replace('https://g-mh.org/manga/', '')
                elif '下一' in text and href:
                    # 从完整URL中提取相对路径
                    next_chapter = href.replace('https://g-mh.org/manga/', '')
            
            # 返回章节数据
            return {
                'code': 200,
                'message': 'success',
                'data': {
                    'images': image_urls,
                    'prev_chapter': prev_chapter,
                    'next_chapter': next_chapter
                }
            }
        finally:
            await browser_manager.close()
            
    except Exception as e:
        app.logger.error(f"Error proxying chapter: {str(e)}")
        return {"error": "Failed to fetch chapter"}, 500

class CloudflareSession:
    _instance = None
    _session = None
    _last_verify_time = 0
    _verify_interval = 300  # 5分钟验证一次
    _lock = Lock()
    _max_retries = 3
    _retry_delay = 1  # 重试延迟（秒）
    
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
                    'mobile': False
                },
                delay=10,  # 添加延迟
                interpreter='nodejs'  # 使用nodejs解释器
            )
            
            # 设置请求头
            self._session.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"macOS"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1'
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
                    response = self._session.get('https://g-mh.org/', timeout=30)
                    if response.status_code == 200:
                        self._last_verify_time = current_time
                        logger.info("Cloudflare会话验证成功")
                        return
                    else:
                        logger.warning(f"Cloudflare会话验证失败，状态码: {response.status_code}")
                        if attempt < self._max_retries - 1:
                            time.sleep(self._retry_delay)
                            self._create_session()
                        else:
                            raise Exception(f"会话验证失败，已重试 {self._max_retries} 次")
                except Exception as e:
                    logger.error(f"Cloudflare会话验证出错 (尝试 {attempt + 1}/{self._max_retries}): {str(e)}")
                    if attempt < self._max_retries - 1:
                        time.sleep(self._retry_delay)
                        self._create_session()
                    else:
                        raise
                
    def get_session(self):
        self._verify_session()
        return self._session

    def get(self, url, **kwargs):
        """发送GET请求"""
        for attempt in range(self._max_retries):
            try:
                self._verify_session()
                response = self._session.get(url, timeout=30, **kwargs)
                if response.status_code == 403:
                    logger.warning("收到403响应，重新创建会话")
                    self._create_session()
                    if attempt < self._max_retries - 1:
                        time.sleep(self._retry_delay)
                        continue
                return response
            except Exception as e:
                logger.error(f"请求失败 (尝试 {attempt + 1}/{self._max_retries}): {str(e)}")
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay)
                    self._create_session()
                else:
                    raise

cloudflare_session = CloudflareSession.get_instance()

@app.route('/api/manga/search/<path:keyword>', methods=['GET', 'POST'])
async def search_manga(keyword):
    try:
        logger.info(f"接收到搜索请求: {keyword}")
        
        # 参数验证
        if not keyword or len(keyword.strip()) == 0:
            raise BadRequestError("搜索关键词不能为空")
            
        # 缓存键
        cache_key = f"search_{keyword}"
        
        # 尝试从缓存获取
        cached_data = cache.get(cache_key)
        if cached_data:
            return quart_jsonify(cached_data)

        # 获取浏览器页面
        browser_page = await browser_manager.get_page()
        search_results = []
        current_url = None

        try:
            # 构建搜索URL
            search_url = f"https://g-mh.org/s/{quote(keyword)}"
            logger.info(f"访问搜索URL: {search_url}")

            # 访问搜索页面
            response = await browser_page.goto(search_url, wait_until='networkidle', timeout=30000)
            logger.info(f"页面响应状态: {response.status}")
            
            # 等待页面加载
            await browser_page.wait_for_timeout(5000)  # 等待5秒确保页面加载完成
            
            # 获取当前URL
            current_url = browser_page.url
            logger.info(f"当前页面URL: {current_url}")

            # 获取页面标题
            title = await browser_page.title()
            logger.info(f"页面标题: {title}")

            # 获取页面内容
            content = await browser_page.content()
            logger.info(f"页面内容: {content}")

            # 等待页面元素出现
            try:
                await browser_page.wait_for_selector('.comics-card', timeout=5000)
                logger.info("找到漫画元素")
            except Exception as e:
                logger.warning(f"等待漫画元素超时: {str(e)}")
                # 尝试其他选择器
                try:
                    await browser_page.wait_for_selector('.book-list', timeout=5000)
                    logger.info("找到漫画列表元素")
                except Exception as e:
                    logger.warning(f"等待漫画列表元素超时: {str(e)}")

            # 提取漫画信息
            items = await browser_page.query_selector_all('.book-list .book-item')
            logger.info(f"找到 {len(items)} 个漫画")

            for item in items:
                try:
                    manga_info = {}
                    
                    # 提取标题和链接
                    title_elem = await item.query_selector('.book-title')
                    if title_elem:
                        manga_info['title'] = (await title_elem.text_content()).strip()
                        link_elem = await title_elem.query_selector('a')
                        if link_elem:
                            manga_info['link'] = await link_elem.get_attribute('href')
                            if manga_info['link'] and not manga_info['link'].startswith('http'):
                                manga_info['link'] = urljoin(current_url, manga_info['link'])

                    # 提取封面图片
                    img_elem = await item.query_selector('.book-cover img')
                    if img_elem:
                        for attr in ['src', 'data-src', 'data-original']:
                            cover = await img_elem.get_attribute(attr)
                            if cover:
                                if not cover.startswith('http'):
                                    cover = urljoin(current_url, cover)
                                manga_info['cover'] = cover
                                break

                    # 提取最新章节
                    latest_chapter = await item.query_selector('.book-info a')
                    if latest_chapter:
                        manga_info['latest_chapter'] = (await latest_chapter.text_content()).strip()
                        manga_info['latest_chapter_link'] = await latest_chapter.get_attribute('href')
                        if manga_info['latest_chapter_link'] and not manga_info['latest_chapter_link'].startswith('http'):
                            manga_info['latest_chapter_link'] = urljoin(current_url, manga_info['latest_chapter_link'])

                    # 只添加有效的结果
                    if manga_info.get('title') and manga_info.get('link'):
                        search_results.append(manga_info)
                        logger.info(f"找到漫画: {manga_info}")

                except Exception as e:
                    logger.error(f"处理漫画元素时出错: {str(e)}")
                    continue

            # 准备返回结果
            result = {
                "code": 200,
                "message": "success" if search_results else "未找到搜索结果",
                "data": {
                    "list": search_results,
                    "meta": {
                        "keyword": keyword,
                        "source_url": current_url,
                        "timestamp": int(time.time())
                    }
                }
            }

            # 只缓存有结果的搜索
            if search_results:
                cache.set(cache_key, result, ttl=1800)  # 30分钟缓存

            return quart_jsonify(result)

        finally:
            await browser_manager.close()

    except BadRequestError as e:
        error_result = {
            "code": 400,
            "message": str(e),
            "data": None,
            "meta": {
                "keyword": keyword if 'keyword' in locals() else None,
                "timestamp": int(time.time())
            }
        }
        return quart_jsonify(error_result), 400

    except Exception as e:
        logger.error(f"搜索漫画时出错: {str(e)}")
        error_result = {
            "code": 500,
            "message": "服务器内部错误",
            "data": None,
            "meta": {
                "error": str(e),
                "keyword": keyword if 'keyword' in locals() else None,
                "timestamp": int(time.time())
            }
        }
        return quart_jsonify(error_result), 500

@app.route('/api/search', methods=['GET', 'POST'])
async def search():
    try:
        # 从查询参数中获取值
        keyword = request.args.get('keyword')
        page = request.args.get('page', 1, type=int)
        size = request.args.get('size', 10, type=int)
        
        if not keyword:
            response = await make_response(quart_jsonify({
                "code": 400,
                "message": "关键词不能为空",
                "data": []
            }))
            response.status_code = 400
            return response
            
        logger.info(f"收到搜索请求: keyword={keyword}, page={page}, size={size}")
        
        # 对关键词进行URL编码
        encoded_keyword = urllib.parse.quote(keyword)
        logger.info(f"编码后的关键词: {encoded_keyword}")
        
        results = await search_manga(encoded_keyword, page, size)
        logger.info(f"搜索完成，返回结果数量: {len(results)}")
        
        response = await make_response(quart_jsonify({
            "code": 200,
            "message": "success" if results else "未找到匹配的结果",
            "data": results,
            "meta": {
                "keyword": keyword,
                "page": page,
                "size": size,
                "total": len(results)
            }
        }))
        response.headers['Content-Type'] = 'application/json'
        return response
        
    except Exception as e:
        logger.error(f"搜索失败: {str(e)}", exc_info=True)
        response = await make_response(quart_jsonify({
            "code": 500,
            "message": f"搜索失败: {str(e)}",
            "data": []
        }))
        response.status_code = 500
        return response

async def search_manga(keyword: str, page: int = 1, size: int = 10) -> List[dict]:
    try:
        logger.info(f"开始搜索漫画: keyword={keyword}, page={page}, size={size}")
        async with browser_manager as manager:
            browser_page = await manager.get_page()
            logger.info("成功创建浏览器页面")

            # 构建搜索URL
            search_url = f"https://g-mh.org/search?keyword={keyword}&page={page}"
            logger.info(f"访问搜索页面: {search_url}")
            
            # 访问页面
            await browser_page.goto(search_url, wait_until='networkidle', timeout=60000)
            logger.info("页面加载完成")
            
            # 等待页面加载
            await browser_page.wait_for_timeout(5000)
            
            # 获取页面标题和内容用于调试
            title = await browser_page.title()
            logger.info(f"页面标题: {title}")
            
            content = await browser_page.content()
            logger.info(f"页面内容长度: {len(content)}")
            
            # 等待漫画列表元素出现
            logger.info("等待漫画列表元素出现")
            try:
                await browser_page.wait_for_selector('.book-list', timeout=10000)
                logger.info("找到漫画列表容器")
                
                await browser_page.wait_for_selector('.book-list .book-item', timeout=10000)
                logger.info("找到漫画列表项")
            except Exception as e:
                logger.warning(f"等待选择器超时: {str(e)}")
                return []

            # 获取所有漫画项
            manga_items = await browser_page.query_selector_all('.book-list .book-item')
            logger.info(f"找到 {len(manga_items)} 个漫画项")

            results = []
            for item in manga_items[:size]:
                try:
                    # 提取标题
                    title_element = await item.query_selector('.book-title')
                    title = await title_element.text_content() if title_element else "未知标题"
                    logger.info(f"提取到标题: {title}")
                    
                    # 提取链接
                    link_element = await item.query_selector('a')
                    link = await link_element.get_attribute('href') if link_element else None
                    if link:
                        link = f"https://g-mh.org{link}" if not link.startswith('http') else link
                    logger.info(f"提取到链接: {link}")
                    
                    # 提取封面图
                    img_element = await item.query_selector('.book-cover img')
                    cover = None
                    if img_element:
                        for attr in ['src', 'data-src', 'data-original']:
                            cover = await img_element.get_attribute(attr)
                            if cover:
                                if not cover.startswith('http'):
                                    cover = f"https://g-mh.org{cover}"
                                break
                    logger.info(f"提取到封面: {cover}")
                    
                    # 提取最新章节
                    latest_chapter_element = await item.query_selector('.book-info a')
                    latest_chapter = await latest_chapter_element.text_content() if latest_chapter_element else "暂无章节"
                    logger.info(f"提取到最新章节: {latest_chapter}")
                    
                    manga = {
                        "title": title.strip(),
                        "link": link,
                        "cover": cover,
                        "latest_chapter": latest_chapter.strip()
                    }
                    results.append(manga)
                    logger.info(f"成功提取漫画信息: {manga['title']}")
                except Exception as e:
                    logger.error(f"提取漫画信息时出错: {str(e)}")
                    continue

            logger.info(f"搜索完成，返回 {len(results)} 个结果")
            return results
            
    except Exception as e:
        logger.error(f"搜索过程中出错: {str(e)}", exc_info=True)
        return []

if __name__ == '__main__':
    try:
        # 检查端口是否被占用
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', API_PORT))
        sock.close()
        
        if result == 0:
            logger.error(f"端口 {API_PORT} 已被占用")
            sys.exit(1)
            
        # 确保数据目录存在
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # 启动服务器
        logger.info("API服务器启动...")
        app.run(
            host=API_HOST,
            port=API_PORT,
            debug=True,
            use_reloader=True
        )
        
    except KeyboardInterrupt:
        logger.info("服务器正在关闭...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"服务器启动失败: {str(e)}")
        sys.exit(1) 