import logging
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import time

logging.basicConfig(level=logging.INFO)

def analyze_page():
    with sync_playwright() as p:
        # 启动浏览器，不使用代理
        browser = p.chromium.launch(
            headless=True
        )
        
        # 创建上下文
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        )
        
        try:
            # 创建新页面
            page = context.new_page()
            
            # 访问漫画页面
            url = 'https://g-mh.org/manga/bianchengtongrenwenlidefanpai'
            print(f'访问页面: {url}')
            
            # 等待页面加载
            response = page.goto(url, timeout=60000)  # 增加超时时间到60秒
            if response:
                print(f'页面状态码: {response.status}')
            
            # 等待章节列表容器出现
            print('等待章节列表加载...')
            page.wait_for_selector('.chapterlists', state='visible', timeout=30000)
            
            # 等待动态内容加载完成
            page.wait_for_load_state('networkidle')
            time.sleep(2)  # 额外等待以确保内容加载完成
            
            # 获取页面内容
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            print('\n页面标题:', soup.title.text if soup.title else 'No title')
            
            # 查找章节列表
            print('\n查找章节列表:')
            chapter_list = soup.find('div', class_='chapterlists')
            if chapter_list:
                print('找到章节列表容器')
                
                # 查找所有章节链接
                chapter_links = chapter_list.find_all('a')
                print(f'找到 {len(chapter_links)} 个章节')
                
                # 显示前几个章节的信息
                for i, link in enumerate(chapter_links[:5]):
                    print(f'\n章节 {i+1}:')
                    print(f'标题: {link.text.strip()}')
                    print(f'链接: {link.get("href", "无链接")}')
                    
                if len(chapter_links) > 5:
                    print(f'\n... 还有 {len(chapter_links)-5} 个章节')
            else:
                print('未找到章节列表容器')
                
                # 输出页面结构以供调试
                print('\n页面结构:')
                for div in soup.find_all('div', class_=True):
                    print(f'发现div, 类名: {div.get("class")}')
            
        except Exception as e:
            print(f'发生错误: {str(e)}')
            
            # 如果发生错误，尝试获取当前页面内容
            try:
                if 'page' in locals():
                    content = page.content()
                    soup = BeautifulSoup(content, 'html.parser')
                    print('\n当前页面内容片段:')
                    print(soup.prettify()[:500])
            except:
                pass
                
        finally:
            browser.close()

if __name__ == '__main__':
    analyze_page() 