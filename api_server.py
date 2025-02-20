from flask import Flask, jsonify, request, Response
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
from quart import Quart, jsonify as quart_jsonify, Response, current_app
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
cache = CacheManager(ttl=3600)  # 1小时缓存

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
            
            content = await page.content()
            
            if '<html' not in content.lower():
                logger.warning("获取的内容可能不是有效的HTML")
                return None
                
            # 解析HTML
            tree = etree.HTML(str(BeautifulSoup(content, 'html.parser')))
            
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
        config = Config()
        config.bind = [f"{API_HOST}:{API_PORT}"]
        config.use_reloader = True
        
        asyncio.run(hypercorn.asyncio.serve(app, config))
        
    except KeyboardInterrupt:
        logger.info("服务器正在关闭...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"服务器启动失败: {str(e)}")
        sys.exit(1) 