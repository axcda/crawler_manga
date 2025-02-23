import os
from datetime import datetime

# 基础配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LATEST_UPDATES_FILE = os.path.join(DATA_DIR, 'latest_updates.json')
LATEST_MANGA_DETAILS_FILE = os.path.join(DATA_DIR, 'latest_manga_details.json')

# API配置
API_HOST = "0.0.0.0"
API_PORT = 7056
BASE_URL = 'https://g-mh.org/'

# 浏览器配置
BROWSER_CONFIG = {
    'headless': True,
    'args': [
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
}

# 浏览器上下文配置
BROWSER_CONTEXT_CONFIG = {
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
}

# 默认请求头
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
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

# 日志配置
LOG_CONFIG = {
    'level': 'DEBUG',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'filename': 'logs/app.log'
}

# 代理配置
PROXY_CONFIG = {
    'enabled': False,
    'http': None,
    'https': None
}

# MongoDB配置
MONGO_HOST = "localhost"
MONGO_PORT = 27017
MONGO_DB = "manga_db"
MONGO_COLLECTION_MANGA = "manga"
MONGO_COLLECTION_CHAPTERS = "chapters"
MONGO_COLLECTION_IMAGES = "images"
MONGO_URI = f"mongodb://{MONGO_HOST}:{MONGO_PORT}" 