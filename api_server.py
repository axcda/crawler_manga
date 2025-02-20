from flask import Flask, jsonify, request
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

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('api_server.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

app = Quart(__name__)
app = cors(app)  # 启用CORS支持

# 数据文件路径
DATA_DIR = 'data'
LATEST_UPDATES_FILE = os.path.join(DATA_DIR, 'latest_updates.json')
LATEST_MANGA_DETAILS_FILE = os.path.join(DATA_DIR, 'latest_manga_details.json')

async def log_request(endpoint, method, ip):
    """记录请求信息"""
    logger.info(f"接收到请求: {endpoint}")
    logger.info(f"请求方法: {method}")
    logger.info(f"请求IP: {ip}")

@app.route('/api/manga/updates', methods=['GET', 'POST'])
async def get_manga_updates():
    try:
        logger.info(f"接收到请求: /api/manga/updates")
        
        # 检查最新更新数据文件是否存在
        if not os.path.exists(LATEST_UPDATES_FILE):
            logger.warning(f"文件不存在: {LATEST_UPDATES_FILE}")
            return quart_jsonify({
                'code': 404,
                'message': '更新数据未找到',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        # 读取最新更新数据
        async with aiofiles.open(LATEST_UPDATES_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            logger.info("成功读取更新数据")
            
        return quart_jsonify(data)
        
    except Exception as e:
        logger.error(f"获取更新数据时出错: {str(e)}", exc_info=True)
        return quart_jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/details', methods=['GET', 'POST'])
async def get_manga_details():
    try:
        logger.info(f"接收到请求: /api/manga/details")
        
        # 检查最新漫画详情数据文件是否存在
        if not os.path.exists(LATEST_MANGA_DETAILS_FILE):
            logger.warning(f"文件不存在: {LATEST_MANGA_DETAILS_FILE}")
            return quart_jsonify({
                'code': 404,
                'message': '漫画详情数据未找到',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        # 读取最新漫画详情数据
        async with aiofiles.open(LATEST_MANGA_DETAILS_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            logger.info("成功读取漫画详情数据")
            
        return quart_jsonify(data)
        
    except Exception as e:
        logger.error(f"获取漫画详情时出错: {str(e)}", exc_info=True)
        return quart_jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

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
async def get_home_page():
    try:
        # 首先尝试使用 cloudscraper
        links = await get_page_content_with_cloudscraper()
        
        # 如果 cloudscraper 失败，尝试使用 playwright
        if not links:
            links = await get_page_content_with_playwright()
            
        if not links:
            logger.error("无法获取首页数据")
            return quart_jsonify({
                'code': 500,
                'message': '无法获取首页数据',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 500
            
        return quart_jsonify({
            'code': 200,
            'message': 'success',
            'data': links,
            'timestamp': int(datetime.now().timestamp())
        })
        
    except Exception as e:
        logger.error(f"获取首页数据时出错: {str(e)}", exc_info=True)
        return quart_jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

async def extract_chapter_data(page):
    """提取章节页面的数据"""
    try:
        # 等待页面加载完成
        logging.info('等待页面加载完成...')
        await page.wait_for_load_state('networkidle', timeout=60000)
        logging.info('页面加载完成')

        # 等待Cloudflare验证完成
        logging.info('等待Cloudflare验证...')
        try:
            await page.wait_for_selector('#challenge-running', state='hidden', timeout=60000)
            await page.wait_for_selector('#challenge-form', state='hidden', timeout=60000)
            logging.info('Cloudflare验证完成')
        except Exception as e:
            logging.warning(f'等待Cloudflare验证时出错: {str(e)}')

        # 提取页面标题
        logging.info('提取页面标题...')
        page_title = await page.title()
        manga_title = page_title.split('-')[0].strip()
        chapter_title = page_title.split('-')[1].strip()
        logging.info(f'提取到标题: {manga_title} - {chapter_title}')

        # 提取所有图片元素
        logging.info('开始提取图片...')
        image_elements = await page.query_selector_all('img')
        logging.info(f'找到 {len(image_elements)} 个图片元素')
        chapter_images = set()  # 使用集合来去重
        
        for img in image_elements:
            src = await img.get_attribute('src') or ''
            alt = await img.get_attribute('alt') or ''
            class_name = await img.get_attribute('class') or ''
            logging.info(f'检查图片: src={src}, alt={alt}, class={class_name}')
            
            # 检查图片是否为章节内容图片
            if ('g-mh.online/hp/' in src or 'baozimh.org' in src) and not ('cover' in src):
                logging.info(f'找到章节图片: src={src}, alt={alt}, class={class_name}')
                chapter_images.add(src)
        
        if not chapter_images:
            logging.warning('未找到任何章节图片')
            # 获取页面内容以便调试
            content = await page.content()
            logging.debug(f'页面内容: {content[:2000]}...')
        else:
            logging.info(f'找到 {len(chapter_images)} 张章节图片')
        
        # 按照图片序号排序
        def get_image_number(url):
            # 从URL中提取序号,例如从 "1_19c0ba3b1c57951b510811041bb10cd9.webp" 中提取 1
            try:
                filename = url.split('/')[-1]
                number = filename.split('_')[0]
                return int(number)
            except:
                return 0
        
        sorted_images = sorted(list(chapter_images), key=get_image_number)
        logging.info(f'图片排序完成,共 {len(sorted_images)} 张')
        
        # 提取上一章和下一章的链接
        logging.info('提取导航链接...')
        prev_chapter = None
        next_chapter = None
        try:
            # 查找所有链接
            links = await page.query_selector_all('a')
            for link in links:
                text = await link.inner_text()
                href = await link.get_attribute('href')
                if text and href:
                    if '上一' in text:
                        prev_chapter = href
                        logging.info(f'找到上一章链接: {href}')
                    elif '下一' in text:
                        next_chapter = href
                        logging.info(f'找到下一章链接: {href}')
        except Exception as e:
            logger.warning(f"提取导航链接时出错: {str(e)}")
        
        # 提取结果
        result = {
            'manga_title': manga_title,
            'chapter_title': chapter_title,
            'image_urls': sorted_images,
            'prev_chapter': prev_chapter,
            'next_chapter': next_chapter
        }
        
        logger.info(f"提取结果: {json.dumps(result, ensure_ascii=False)}")
        return result
        
    except Exception as e:
        logger.error(f"提取章节数据时出错: {str(e)}")
        # 获取当前页面内容以便调试
        page_content = await page.content()
        logger.debug(f"页面内容: {page_content[:2000]}...")
        raise

@app.route('/api/manga/proxy/<path:manga_path>', methods=['GET', 'POST'])
async def proxy_manga(manga_path):
    try:
        target_url = f'https://g-mh.org/manga/{manga_path}'
        logger.info(f"代理请求: {target_url}")
        
        # 判断页面类型
        path_parts = manga_path.split('/')
        is_chapter_page = len(path_parts) == 2 and '-' in path_parts[1] and any(part.isdigit() for part in path_parts[1].split('-'))
        logger.info(f"路径分析: {path_parts}")
        logger.info(f"页面类型判断: {'章节页面' if is_chapter_page else '其他页面'}")
        
        # 启动浏览器
        logger.info("启动浏览器...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            )
            
            # 创建上下文
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                bypass_csp=True
            )
            
            # 设置额外的头部
            page = await context.new_page()
            await page.set_extra_http_headers({
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'identity',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            })
            
            # 添加 JavaScript 来模拟真实浏览器
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """)
            
            # 导航到目标URL
            logger.info(f"导航到目标URL: {target_url}")
            response = await page.goto(target_url, timeout=60000, wait_until='domcontentloaded')
            
            # 等待页面加载完成
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(random.uniform(2000, 3000))
            
            if is_chapter_page:
                # 如果是章节页面，提取数据并返回JSON
                logger.info("开始提取章节数据...")
                try:
                    # 获取并记录页面内容
                    content = await page.content()
                    logger.info(f"页面内容: {content[:2000]}...")
                    
                    chapter_data = await extract_chapter_data(page)
                    await browser.close()
                    return quart_jsonify(chapter_data)
                except Exception as e:
                    logger.error(f"提取章节数据时出错: {str(e)}")
                    content = await page.content()
                    logger.debug(f"页面内容: {content[:2000]}...")
                    await browser.close()
                    return quart_jsonify({'error': str(e)}), 500
            else:
                # 如果是其他页面，返回HTML内容
                content = await page.content()
                await browser.close()
                return content

    except Exception as e:
        logger.error(f"代理请求出错: {str(e)}")
        return quart_jsonify({'error': str(e)}), 500

@app.route('/api/manga/chapter/<path:manga_path>', methods=['GET', 'POST'])
async def get_chapter_info(manga_path):
    try:
        # 从URL中提取章节ID
        path_parts = manga_path.split('/')
        if len(path_parts) != 2:
            return quart_jsonify({
                'code': 400,
                'message': '无效的章节路径',
                'data': None
            }), 400
            
        manga_id = path_parts[0]
        chapter_id = path_parts[1]
        
        logger.info(f"获取章节信息: manga_id={manga_id}, chapter_id={chapter_id}")
        
        # 启动浏览器
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            )
            
            # 创建上下文
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                bypass_csp=True
            )
            
            # 创建新页面
            page = await context.new_page()
            
            # 设置额外的头部
            await page.set_extra_http_headers({
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'identity',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            })
            
            # 添加 JavaScript 来模拟真实浏览器
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """)
            
            # 访问章节页面
            chapter_url = f'https://g-mh.org/manga/{manga_path}'
            logger.info(f"访问章节页面: {chapter_url}")
            
            response = await page.goto(chapter_url, wait_until='networkidle', timeout=60000)
            
            # 等待页面加载完成
            await page.wait_for_load_state('networkidle', timeout=60000)
            await page.wait_for_timeout(random.uniform(2000, 3000))
            
            # 提取章节数据
            chapter_data = await extract_chapter_data(page)
            
            # 关闭浏览器
            await browser.close()
            
            return quart_jsonify({
                'code': 200,
                'message': 'success',
                'data': chapter_data
            })
            
    except Exception as e:
        logger.error(f"获取章节信息时出错: {str(e)}")
        return quart_jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500

async def get_page_content_with_cloudscraper():
    try:
        # 创建 cloudscraper 会话
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'mobile': False
            },
            delay=10
        )
        scraper.proxies = {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890'
        }
        scraper.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

        logger.info("使用 cloudscraper 访问网站...")
        # 使用 asyncio 运行同步代码
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: scraper.get('https://g-mh.org/'))
        
        if response.status_code == 200:
            logger.info("成功获取响应!")
            if '<html' not in response.text.lower():
                logger.warning("响应内容可能不是有效的HTML")
                return None
            return extract_links(response.content)
        else:
            logger.warning(f"请求失败，状态码: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Cloudscraper 错误: {str(e)}", exc_info=True)
        return None

async def get_page_content_with_playwright():
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={
                    "server": "http://127.0.0.1:7890"
                }
            )
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN'
            )
            page = await context.new_page()
            
            await page.set_extra_http_headers({
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'identity'
            })
            
            logger.info("使用 Playwright 访问网站...")
            response = await page.goto('https://g-mh.org/', timeout=30000)
            
            if response:
                logger.info(f"Playwright 响应状态码: {response.status}")
            
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(random.uniform(3000, 5000))
            
            content = await page.content()
            
            if '<html' not in content.lower():
                logger.warning("获取的内容可能不是有效的HTML")
                return None
                
            try:
                await page.wait_for_selector('div.slicarda', timeout=5000)
                logger.info("找到更新卡片元素")
            except Exception as e:
                logger.warning(f"未找到更新卡片元素: {str(e)}")
            
            return extract_links(content)
                    
    except Exception as e:
        logger.error(f"Playwright 错误: {str(e)}", exc_info=True)
        return None
    finally:
        if 'browser' in locals():
            await browser.close()

def extract_links(html_content, base_url='https://g-mh.org/'):
    try:
        # 使用lxml的etree而不是html模块
        tree = etree.HTML(str(BeautifulSoup(html_content, 'html.parser')))
        
        links = {
            'updates': [],  # 更新信息
            'popular_manga': [],  # 人气排行
            'new_manga': [],  # 最新上架
            'hot_updates': []  # 热门更新
        }
        
        # 查找所有漫画卡片
        manga_cards = tree.xpath('//a[@class="slicarda"]')
        logger.info(f"找到漫画卡片数量: {len(manga_cards)}")
        
        # 查找热门更新
        hot_updates_section = tree.xpath('/html/body/main/div/div[6]/div[1]/div[2]/div')
        logger.info(f"找到热门更新数量: {len(hot_updates_section)}")
        
        # 处理热门更新
        for index, item in enumerate(hot_updates_section, 1):
            try:
                link_element = item.xpath('.//a')[0] if item.xpath('.//a') else None
                if not link_element:
                    continue
                    
                title_element = item.xpath('.//h3/text()')
                title = title_element[0].strip() if title_element else "未知标题"
                
                img_element = None
                img_url = ''
                
                img_xpath = f'/html/body/main/div/div[6]/div[1]/div[2]/div[{index}]/a/div/div/img'
                img_elements = tree.xpath(img_xpath)
                if img_elements:
                    img_element = img_elements[0]
                    img_url = img_element.get('src', '')
                
                if not img_url:
                    img_elements = item.xpath('.//img')
                    if img_elements:
                        img_element = img_elements[0]
                        img_url = img_element.get('src', '')
                
                if not img_url and link_element is not None:
                    img_elements = link_element.xpath('.//img')
                    if img_elements:
                        img_element = img_elements[0]
                        img_url = img_element.get('src', '')
                
                img_url = process_image_url(img_url) if img_url else ''
                link = urljoin(base_url, link_element.get('href', ''))
                
                manga_info = {
                    'title': title,
                    'link': link,
                    'image_url': img_url
                }
                
                links['hot_updates'].append(manga_info)
                
            except Exception as e:
                logger.warning(f"处理热门更新项时出错: {str(e)}")
                continue
        
        # 处理更新卡片
        for card in manga_cards:
            try:
                title = card.xpath('.//h3[@class="slicardtitle"]/text()')[0].strip()
                link = urljoin(base_url, card.get('href', ''))
                time_text = card.xpath('.//p[@class="slicardtagp"]/text()')[0].strip()
                chapter_text = card.xpath('.//p[@class="slicardtitlep"]/text()')[0].strip()
                img = card.xpath('.//img[@class="slicardimg"]')[0]
                img_url = process_image_url(img.get('src', ''))
                
                manga_info = {
                    'title': title,
                    'link': link,
                    'time': time_text,
                    'chapter': chapter_text,
                    'image_url': img_url
                }
                
                if '小时前' in time_text or '分钟前' in time_text:
                    links['updates'].append(manga_info)
                
            except Exception as e:
                logger.warning(f"处理漫画卡片时出错: {str(e)}")
                continue
        
        # 处理排行榜
        rank_section = tree.xpath('/html/body/main/div/div[6]/div[2]/div[2]/div')
        if rank_section:
            for index, item in enumerate(rank_section, 1):
                try:
                    link_element = item.xpath('.//a')[0] if item.xpath('.//a') else None
                    if not link_element:
                        continue
                        
                    title_element = item.xpath('.//a/div/h3/text()')
                    title = title_element[0].strip() if title_element else "未知标题"
                    
                    img_url = ''
                    img_xpath = f'/html/body/main/div/div[6]/div[2]/div[2]/div[{index}]/a/div/div/img'
                    img_elements = tree.xpath(img_xpath)
                    if img_elements:
                        img_url = img_elements[0].get('src', '')
                    
                    if not img_url:
                        img_elements = item.xpath('.//img')
                        if img_elements:
                            img_url = img_elements[0].get('src', '')
                    
                    img_url = process_image_url(img_url) if img_url else ''
                    link = urljoin(base_url, link_element.get('href', ''))
                    
                    manga_info = {
                        'title': title,
                        'link': link,
                        'image_url': img_url
                    }
                    
                    links['popular_manga'].append(manga_info)
                    
                except Exception as e:
                    logger.warning(f"处理排行榜项时出错: {str(e)}")
                    continue
        
        # 处理最新上架
        new_section = tree.xpath('/html/body/main/div/div[6]/div[3]/div[2]/div')
        if new_section:
            for index, item in enumerate(new_section, 1):
                try:
                    title_xpath = f'/html/body/main/div/div[6]/div[3]/div[2]/div[{index}]/a/div/h3'
                    title_element = tree.xpath(title_xpath)
                    title = title_element[0].text.strip() if title_element else None
                    
                    if not title:
                        continue
                    
                    link_xpath = f'/html/body/main/div/div[6]/div[3]/div[2]/div[{index}]/a'
                    link_element = tree.xpath(link_xpath)
                    if not link_element:
                        continue
                    link = urljoin(base_url, link_element[0].get('href', ''))
                    
                    img_xpath = f'/html/body/main/div/div[6]/div[3]/div[2]/div[{index}]/a/div/div/img'
                    img_element = tree.xpath(img_xpath)
                    img_url = ''
                    if img_element:
                        img_url = img_element[0].get('src', '')
                    
                    img_url = process_image_url(img_url) if img_url else ''
                    
                    manga_info = {
                        'title': title,
                        'link': link,
                        'image_url': img_url
                    }
                    
                    links['new_manga'].append(manga_info)
                    
                except Exception as e:
                    logger.warning(f"处理最新上架项时出错: {str(e)}")
                    continue
        
        logger.info(f"找到 {len(links['updates'])} 个更新信息")
        logger.info(f"找到 {len(links['popular_manga'])} 个排行榜信息")
        logger.info(f"找到 {len(links['new_manga'])} 个最新上架信息")
        logger.info(f"找到 {len(links['hot_updates'])} 个热门更新信息")
        
        return links
    except Exception as e:
        logger.error(f"提取链接时出错: {str(e)}", exc_info=True)
        return None

def process_image_url(img_url):
    try:
        if 'pro-api.mgsearcher.com/_next/image' in img_url:
            return img_url
            
        if 'cncover.godamanga.online' in img_url:
            encoded_url = quote(img_url, safe='')
            return f'https://pro-api.mgsearcher.com/_next/image?url={encoded_url}&w=250&q=60'
            
        return img_url
    except Exception as e:
        logger.warning(f"处理图片URL时出错: {str(e)}")
        return img_url

if __name__ == '__main__':
    # 确保数据目录存在
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 启动服务器
    logger.info("API服务器启动...")
    config = hypercorn.Config()
    config.bind = ["0.0.0.0:7056"]
    config.use_reloader = True  # 启用热重载
    asyncio.run(hypercorn.asyncio.serve(app, config)) 