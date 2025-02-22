import requests
import json
from datetime import datetime
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:7056"

def test_home_page():
    """测试首页接口"""
    url = f"{BASE_URL}/api/manga/home"
    try:
        logger.info("测试首页接口...")
        response = requests.get(url)
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info("首页数据获取成功")
            return True
        else:
            logger.error(f"请求失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"测试出错: {str(e)}")
        return False

def test_search():
    """测试搜索接口"""
    keyword = "海贼"
    url = f"{BASE_URL}/api/manga/search/{keyword}"
    try:
        logger.info(f"测试搜索接口，关键词: {keyword}...")
        response = requests.get(url)
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info("搜索数据获取成功")
            return True
        else:
            logger.error(f"请求失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"测试出错: {str(e)}")
        return False

def test_manga_info():
    """测试漫画详情接口"""
    manga_path = "zongyoulaoshiyaoqingjiazhang-19262"
    url = f"{BASE_URL}/api/manga/chapter/{manga_path}"
    try:
        logger.info(f"测试漫画详情接口，漫画ID: {manga_path}...")
        response = requests.get(url)
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info("漫画详情数据获取成功")
            return True
        else:
            logger.error(f"请求失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"测试出错: {str(e)}")
        return False

def test_chapter_content():
    """测试章节内容接口"""
    chapter_path = "zongyoulaoshiyaoqingjiazhang-19262/29403-7911216-85"
    url = f"{BASE_URL}/api/manga/content/{chapter_path}"
    try:
        logger.info(f"测试章节内容接口，章节路径: {chapter_path}...")
        response = requests.get(url)
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info("章节内容数据获取成功")
            return True
        else:
            logger.error(f"请求失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"测试出错: {str(e)}")
        return False

def test_server_stats():
    """测试服务器状态接口"""
    url = f"{BASE_URL}/api/stats"
    try:
        logger.info("测试服务器状态接口...")
        response = requests.get(url)
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info("服务器状态数据获取成功")
            return True
        else:
            logger.error(f"请求失败: {response.text}")
            return False
    except Exception as e:
        logger.error(f"测试出错: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("开始API接口测试...")
    
    test_results = {
        "首页接口": test_home_page(),
        "搜索接口": test_search(),
        "漫画详情接口": test_manga_info(),
        "章节内容接口": test_chapter_content(),
        # "服务器状态接口": test_server_stats()
    }
    
    logger.info("\n测试结果汇总:")
    for api_name, result in test_results.items():
        status = "通过" if result else "失败"
        logger.info(f"{api_name}: {status}")
    
    # 计算成功率
    success_count = sum(1 for result in test_results.values() if result)
    total_count = len(test_results)
    success_rate = (success_count / total_count) * 100
    
    logger.info(f"\n测试完成！成功率: {success_rate:.2f}%") 