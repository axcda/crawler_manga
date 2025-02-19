import cloudscraper
import time
import random
import logging
from playwright.sync_api import sync_playwright
import json
import chardet
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, unquote, quote
import os
from datetime import datetime
import schedule
from lxml import html
import concurrent.futures
from queue import Queue
from threading import Lock

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('crawler.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 代理设置
PROXY_CONFIG = {
    'http': 'http://127.0.0.1:7890',  # 本地HTTP代理
    'https': 'http://127.0.0.1:7890'  # 本地HTTPS代理
}

# 添加线程安全的日志队列和锁
log_queue = Queue()
log_lock = Lock()

def thread_safe_log(level, message):
    with log_lock:
        if level == 'info':
            logger.info(message)
        elif level == 'warning':
            logger.warning(message)
        elif level == 'error':
            logger.error(message)

# 创建存储目录
def ensure_directories():
    os.makedirs('data', exist_ok=True)
    os.makedirs('logs', exist_ok=True)

def save_api_result(links):
    if not links:
        return False
        
    try:
        # 生成时间戳文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 创建更新信息的数据结构
        updates_data = {
            'code': 200,
            'message': 'success',
            'data': {
                'updates': links.get('updates', []),
                'hot_updates': links.get('hot_updates', [])
            },
            'timestamp': int(time.time())
        }
        
        # 创建漫画详情的数据结构
        manga_details = {
            'code': 200,
            'message': 'success',
            'data': {
                'popular_manga': links.get('popular_manga', []),
                'new_manga': links.get('new_manga', [])
            },
            'timestamp': int(time.time())
        }
        
        # 保存最新的更新信息
        with open('data/latest_updates.json', 'w', encoding='utf-8') as f:
            json.dump(updates_data, f, ensure_ascii=False, indent=2)
            
        # 保存最新的漫画详情
        with open('data/latest_manga_details.json', 'w', encoding='utf-8') as f:
            json.dump(manga_details, f, ensure_ascii=False, indent=2)
            
        # 保存历史更新信息记录
        with open(f'data/updates_{timestamp}.json', 'w', encoding='utf-8') as f:
            json.dump(updates_data, f, ensure_ascii=False, indent=2)
            
        # 保存历史漫画详情记录
        with open(f'data/manga_details_{timestamp}.json', 'w', encoding='utf-8') as f:
            json.dump(manga_details, f, ensure_ascii=False, indent=2)
            
        thread_safe_log('info', f"API结果已分别保存到更新信息和漫画详情文件")
        return True
    except Exception as e:
        thread_safe_log('error', f"保存API结果时出错: {str(e)}", exc_info=True)
        return False

def fetch_manga_detail(url, playwright=None, browser_context=None):
    """
    获取漫画详情，包括标题、作者、标签和章节列表
    
    Args:
        url: 漫画详情页URL
        playwright: 可选的playwright实例，如果提供则使用现有实例
        browser_context: 可选的浏览器上下文，如果提供则使用现有上下文
    """
    try:
        should_close_browser = False
        if not playwright or not browser_context:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
            browser_context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            )
            should_close_browser = True
        
        page = browser_context.new_page()
        detail_info = {}
        
        try:
            # 访问页面
            thread_safe_log('info', f"访问漫画详情页面: {url}")
            response = page.goto(url, timeout=60000)
            
            if response and response.status == 200:
                # 等待章节列表加载
                page.wait_for_selector('.chapterlists', state='visible', timeout=30000)
                page.wait_for_load_state('networkidle')
                time.sleep(2)  # 额外等待以确保内容加载完成
                
                # 获取页面内容
                content = page.content()
                tree = html.fromstring(content)
                
                # 使用精确的XPath提取标题
                title_element = tree.xpath('/html/body/main/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/h1')
                if title_element:
                    detail_info['title'] = title_element[0].text.strip()
                    thread_safe_log('info', f"找到标题: {detail_info['title']}")
                else:
                    detail_info['title'] = "未知标题"
                    thread_safe_log('warning', "无法获取标题")
                
                # 使用精确的XPath提取简介
                desc_element = tree.xpath('/html/body/main/div[2]/div[2]/div[2]/div[1]/div[1]/p')
                if desc_element:
                    detail_info['description'] = desc_element[0].text.strip()
                    thread_safe_log('info', f"找到简介: {detail_info['description'][:50]}...")
                else:
                    detail_info['description'] = "暂无简介"
                
                # 提取作者信息
                author_element = tree.xpath('//div[contains(@class, "author")]')
                if author_element:
                    author_text = author_element[0].text_content().strip()
                    author_link = author_element[0].xpath('.//a/@href')
                    if author_text:
                        detail_info['author'] = author_text
                        thread_safe_log('info', f"找到作者: {author_text}")
                    if author_link:
                        detail_info['author_link'] = urljoin(url, author_link[0])
                        thread_safe_log('info', f"找到作者链接: {detail_info['author_link']}")
                
                # 提取标签
                tags_element = tree.xpath('//div[contains(@class, "tags")]//a')
                if tags_element:
                    tags = []
                    tag_links = {}
                    for tag in tags_element:
                        tag_text = tag.text_content().strip()
                        tag_href = tag.get('href')
                        if tag_text:
                            tags.append(tag_text)
                            if tag_href:
                                tag_links[tag_text] = urljoin(url, tag_href)
                    detail_info['tags'] = tags
                    detail_info['tag_links'] = tag_links
                    thread_safe_log('info', f"找到标签: {tags}")
                
                # 提取章节列表
                chapters = []
                chapter_list = tree.xpath('//div[contains(@class, "chapterlists")]//a')
                if chapter_list:
                    thread_safe_log('info', f"找到 {len(chapter_list)} 个章节")
                    
                    # 使用线程池处理章节信息
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_chapter = {
                            executor.submit(process_chapter, chapter, url): chapter 
                            for chapter in chapter_list
                        }
                        
                        for future in concurrent.futures.as_completed(future_to_chapter):
                            try:
                                chapter_info = future.result()
                                if chapter_info:
                                    chapters.append(chapter_info)
                            except Exception as e:
                                thread_safe_log('error', f"处理章节信息时出错: {str(e)}")
                
                detail_info['chapters'] = chapters
                
                # 提取查看所有章节链接
                view_more = tree.xpath('//a[contains(text(), "查看所有章节")]/@href')
                if view_more:
                    detail_info['all_chapters_link'] = urljoin(url, view_more[0])
                    thread_safe_log('info', f"找到查看所有章节链接: {detail_info['all_chapters_link']}")
                
                thread_safe_log('info', f"成功获取漫画详情: {detail_info['title']}, 章节数: {len(chapters)}")
                
            else:
                thread_safe_log('error', f"访问页面失败: {response.status if response else 'No response'}")
                
        except Exception as e:
            thread_safe_log('error', f"处理页面时出错: {str(e)}")
        finally:
            page.close()
            
        return detail_info
            
    except Exception as e:
        thread_safe_log('error', f"访问漫画详情页面时出错: {url}, 错误: {str(e)}")
        return None
    finally:
        if should_close_browser:
            browser_context.close()
            playwright.stop()

def process_chapter(chapter_element, base_url):
    """
    处理单个章节信息
    
    Args:
        chapter_element: 章节元素
        base_url: 基础URL
    """
    try:
        chapter_info = {
            'title': chapter_element.text_content().strip(),
            'link': urljoin(base_url, chapter_element.get('href', ''))
        }
        
        # 尝试提取更新时间
        time_element = chapter_element.xpath('.//span[contains(@class, "time")] | .//span[contains(@class, "date")]')
        if time_element:
            chapter_info['time'] = time_element[0].text_content().strip()
            
        thread_safe_log('info', f"处理章节: {chapter_info['title']}")
        return chapter_info
    except Exception as e:
        thread_safe_log('warning', f"处理章节元素时出错: {str(e)}")
        return None

def process_manga_detail(manga_info, scraper):
    try:
        detail = fetch_manga_detail(manga_info['link'], scraper)
        if detail:
            manga_info['detail'] = detail
            thread_safe_log('info', f"成功获取漫画详情: {manga_info['title']}")
        return manga_info
    except Exception as e:
        thread_safe_log('warning', f"获取漫画详情时出错: {str(e)}")
        return manga_info

def process_manga_list_with_threads(manga_list, max_workers=3):
    """
    使用多线程处理漫画列表
    
    Args:
        manga_list: 要处理的漫画列表
        max_workers: 最大线程数，默认为3
    """
    try:
        # 如果列表为空，直接返回
        if not manga_list:
            return []
            
        # 创建一个共享的 cloudscraper 会话
        thread_safe_log('info', "创建共享的 cloudscraper 会话...")
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'mobile': False
            },
            delay=10
        )
        scraper.proxies = PROXY_CONFIG
        
        # 分批处理漫画列表
        batch_size = 5  # 每批处理的数量
        results = []
        
        for i in range(0, len(manga_list), batch_size):
            try:
                batch = manga_list[i:i + batch_size]
                thread_safe_log('info', f"处理第 {i//batch_size + 1} 批漫画，共 {len(batch)} 个")
                
                # 创建线程池
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # 设置超时时间为60秒
                    timeout = 60
                    
                    # 提交所有任务到线程池
                    future_to_manga = {
                        executor.submit(process_manga_detail, manga, scraper): manga 
                        for manga in batch
                    }
                    
                    # 使用超时控制获取结果
                    try:
                        for future in concurrent.futures.as_completed(future_to_manga, timeout=timeout):
                            try:
                                manga_info = future.result(timeout=timeout)
                                if manga_info:
                                    results.append(manga_info)
                            except concurrent.futures.TimeoutError:
                                thread_safe_log('warning', f"处理漫画信息超时")
                                continue
                            except Exception as e:
                                thread_safe_log('error', f"处理漫画信息时出错: {str(e)}")
                                continue
                    except concurrent.futures.TimeoutError:
                        thread_safe_log('warning', f"批次处理超时，继续处理下一批")
                        # 取消所有未完成的任务
                        for future in future_to_manga:
                            future.cancel()
                        continue
                    
                # 批次间添加随机延迟
                if i + batch_size < len(manga_list):
                    delay = random.uniform(3, 8)
                    thread_safe_log('info', f"等待 {delay:.2f} 秒后处理下一批...")
                    time.sleep(delay)
                    
            except KeyboardInterrupt:
                thread_safe_log('warning', "检测到手动中断，正在优雅退出...")
                return results
            except Exception as e:
                thread_safe_log('error', f"处理批次时出错: {str(e)}")
                continue
                
        return results
    except KeyboardInterrupt:
        thread_safe_log('warning', "检测到手动中断，正在优雅退出...")
        return results
    except Exception as e:
        thread_safe_log('error', f"多线程处理时出错: {str(e)}")
        return manga_list

def extract_links(html_content, base_url='https://g-mh.org/'):
    try:
        # 创建lxml树
        tree = html.fromstring(str(BeautifulSoup(html_content, 'html.parser')))
        
        # 创建一个字典来存储不同类型的链接
        links = {
            'updates': [],  # 更新信息
            'popular_manga': [],  # 人气排行
            'new_manga': [],  # 最新上架
            'hot_updates': []  # 热门更新
        }
        
        # 查找所有漫画卡片
        manga_cards = tree.xpath('//a[@class="slicarda"]')
        thread_safe_log('info', f"找到漫画卡片数量: {len(manga_cards)}")
        
        for card in manga_cards:
            try:
                # 提取基本信息
                title = card.xpath('.//h3[@class="slicardtitle"]/text()')[0].strip()
                link = urljoin(base_url, card.get('href', ''))
                
                # 提取时间信息
                time_text = card.xpath('.//p[@class="slicardtagp"]/text()')[0].strip()
                
                # 提取章节信息
                chapter_text = card.xpath('.//p[@class="slicardtitlep"]/text()')[0].strip()
                
                # 提取图片信息
                img = card.xpath('.//img[@class="slicardimg"]')[0]
                img_url = img.get('src', '')
                
                manga_info = {
                    'title': title,
                    'link': link,
                    'time': time_text,
                    'chapter': chapter_text,
                    'image_url': img_url
                }
                
                thread_safe_log('info', f"处理漫画: {title} - {time_text} - {chapter_text}")
                
                # 根据时间判断是否为最新更新
                if '小时前' in time_text or '分钟前' in time_text:
                    links['updates'].append(manga_info)
                    thread_safe_log('info', f"添加到更新列表: {title}")
                
                # 添加到热门更新
                if len(links['hot_updates']) < 10:
                    links['hot_updates'].append(manga_info)
                    thread_safe_log('info', f"添加到热门更新: {title}")
                
            except Exception as e:
                thread_safe_log('warning', f"处理漫画卡片时出错: {str(e)}")
                continue
        
        # 查找排行榜漫画
        rank_section = tree.xpath('//div[contains(@class, "rank-list")]//a')
        if rank_section:
            for item in rank_section[:10]:  # 只取前10个
                try:
                    title = item.xpath('.//text()')[0].strip()
                    link = urljoin(base_url, item.get('href', ''))
                    links['popular_manga'].append({
                        'title': title,
                        'link': link
                    })
                    thread_safe_log('info', f"添加到排行榜: {title}")
                except Exception as e:
                    thread_safe_log('warning', f"处理排行榜项时出错: {str(e)}")
                    continue
        
        # 查找最新上架
        new_section = tree.xpath('//div[contains(@class, "new-manga")]//a')
        if new_section:
            for item in new_section[:10]:  # 只取前10个
                try:
                    title = item.xpath('.//text()')[0].strip()
                    link = urljoin(base_url, item.get('href', ''))
                    links['new_manga'].append({
                        'title': title,
                        'link': link
                    })
                    thread_safe_log('info', f"添加到最新上架: {title}")
                except Exception as e:
                    thread_safe_log('warning', f"处理最新上架项时出错: {str(e)}")
                    continue
        
        # 使用线程池处理更新信息
        thread_safe_log('info', "开始多线程处理更新信息...")
        links['updates'] = process_manga_list_with_threads(links['updates'])
        
        # 使用线程池处理人气排行
        thread_safe_log('info', "开始多线程处理人气排行...")
        links['popular_manga'] = process_manga_list_with_threads(links['popular_manga'])
        
        # 使用线程池处理最新上架
        thread_safe_log('info', "开始多线程处理最新上架...")
        links['new_manga'] = process_manga_list_with_threads(links['new_manga'])
        
        # 使用线程池处理热门更新
        thread_safe_log('info', "开始多线程处理热门更新...")
        links['hot_updates'] = process_manga_list_with_threads(links['hot_updates'])
        
        # 保存链接到JSON文件
        with open('extracted_links.json', 'w', encoding='utf-8') as f:
            json.dump(links, f, ensure_ascii=False, indent=2)
        thread_safe_log('info', "链接已保存到 extracted_links.json")
        
        # 打印统计信息
        thread_safe_log('info', f"找到 {len(links['updates'])} 个更新信息")
        thread_safe_log('info', f"找到 {len(links['popular_manga'])} 个排行榜信息")
        thread_safe_log('info', f"找到 {len(links['new_manga'])} 个最新上架信息")
        thread_safe_log('info', f"找到 {len(links['hot_updates'])} 个热门更新信息")
        
        return links
    except Exception as e:
        thread_safe_log('error', f"提取链接时出错: {str(e)}", exc_info=True)
        return None

class CloudflareSession:
    _instance = None
    _session = None
    _last_verify_time = 0
    _verify_interval = 300  # 5分钟验证一次
    _lock = Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        if CloudflareSession._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            CloudflareSession._instance = self

    def _create_session(self):
        thread_safe_log('info', "创建新的 Cloudflare 会话...")
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'mobile': False
            },
            delay=10
        )
        scraper.proxies = PROXY_CONFIG
        scraper.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        return scraper

    def _verify_session(self):
        current_time = time.time()
        if self._session is None or (current_time - self._last_verify_time) > self._verify_interval:
            with self._lock:
                if self._session is None or (current_time - self._last_verify_time) > self._verify_interval:
                    try:
                        if self._session is None:
                            self._session = self._create_session()
                        
                        # 验证会话
                        response = self._session.get('https://g-mh.org/')
                        if response.status_code != 200 or '<html' not in response.text.lower():
                            thread_safe_log('warning', "会话验证失败，创建新会话")
                            self._session = self._create_session()
                            response = self._session.get('https://g-mh.org/')
                            if response.status_code != 200:
                                raise Exception(f"无法创建有效会话，状态码: {response.status_code}")
                        
                        self._last_verify_time = current_time
                        thread_safe_log('info', "会话验证成功")
                        
                    except Exception as e:
                        thread_safe_log('error', f"会话验证出错: {str(e)}")
                        self._session = None
                        raise

    def get_session(self):
        try:
            self._verify_session()
            return self._session
        except Exception as e:
            thread_safe_log('error', f"获取会话失败: {str(e)}")
            return None

def get_page_content_with_cloudscraper():
    try:
        # 获取共享会话
        session = CloudflareSession.get_instance().get_session()
        if session is None:
            thread_safe_log('warning', "无法获取有效会话，尝试使用 Playwright...")
            return None

        thread_safe_log('info', "使用共享会话访问网站...")
        response = session.get('https://g-mh.org/')
        
        if response.status_code == 200:
            thread_safe_log('info', "成功获取响应!")
            # 打印响应内容的前1000个字符用于调试
            thread_safe_log('info', f"响应内容预览: {response.text[:1000]}")
            # 检查响应内容是否包含预期的HTML结构
            if '<html' not in response.text.lower():
                thread_safe_log('warning', "响应内容可能不是有效的HTML")
                return None
            # 直接提取链接
            return extract_links(response.content)
        else:
            thread_safe_log('warning', f"请求失败，状态码: {response.status_code}")
            thread_safe_log('warning', "尝试使用 Playwright...")
            return None
            
    except Exception as e:
        thread_safe_log('error', f"Cloudscraper 错误: {str(e)}", exc_info=True)
        return None

def get_page_content_with_playwright():
    try:
        with sync_playwright() as p:
            # 启动浏览器（无头模式）并配置代理
            browser = p.chromium.launch(
                headless=True,
                proxy={
                    "server": "http://127.0.0.1:7890"
                }
            )
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN'
            )
            page = context.new_page()
            
            # 设置额外的头部
            page.set_extra_http_headers({
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'identity'  # 禁用压缩
            })
            
            thread_safe_log('info', "使用 Playwright 通过代理访问网站...")
            response = page.goto('https://g-mh.org/', timeout=30000)
            
            if response:
                thread_safe_log('info', f"Playwright 响应状态码: {response.status}")
            
            # 等待加载完成
            page.wait_for_load_state('networkidle')
            time.sleep(random.uniform(3, 5))
            
            # 获取页面内容并检查
            content = page.content()
            thread_safe_log('info', f"Playwright 获取的页面内容预览: {content[:1000]}")
            
            # 检查是否包含预期的HTML结构
            if '<html' not in content.lower():
                thread_safe_log('warning', "Playwright 获取的内容可能不是有效的HTML")
                return None
                
            # 尝试等待特定元素出现
            try:
                page.wait_for_selector('div.slicarda', timeout=5000)
                thread_safe_log('info', "找到更新卡片元素")
            except Exception as e:
                thread_safe_log('warning', f"未找到更新卡片元素: {str(e)}")
            
            return extract_links(content)
                    
    except Exception as e:
        thread_safe_log('error', f"Playwright 错误: {str(e)}", exc_info=True)
        return None
    finally:
        if 'browser' in locals():
            browser.close()

def fetch_data():
    try:
        thread_safe_log('info', "开始获取数据...")
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 首先尝试使用 cloudscraper
        links = get_page_content_with_cloudscraper()
        
        # 如果 cloudscraper 失败，尝试使用 playwright
        if not links:
            links = get_page_content_with_playwright()
        
        if links:
            save_api_result(links)
            thread_safe_log('info', f"数据获取成功 - {current_time}")
        else:
            thread_safe_log('error', f"数据获取失败 - {current_time}")
            
    except Exception as e:
        thread_safe_log('error', f"执行任务时出错: {str(e)}", exc_info=True)

def main():
    # 确保目录存在
    ensure_directories()
    
    # 立即执行一次
    fetch_data()
    
    # 设置定时任务，每30分钟执行一次
    schedule.every(30).minutes.do(fetch_data)
    
    thread_safe_log('info', "定时任务已启动，每30分钟执行一次...")
    
    # 运行定时任务
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            thread_safe_log('info', "程序已停止")
            break
        except Exception as e:
            thread_safe_log('error', f"运行时出错: {str(e)}", exc_info=True)
            time.sleep(60)  # 发生错误时等待1分钟后继续

if __name__ == "__main__":
    main()
