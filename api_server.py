from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import os
from datetime import datetime
import logging

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

app = Flask(__name__)
CORS(app)  # 启用CORS支持

# 数据文件路径
DATA_DIR = 'data'
LATEST_UPDATES_FILE = os.path.join(DATA_DIR, 'latest_updates.json')
LATEST_MANGA_DETAILS_FILE = os.path.join(DATA_DIR, 'latest_manga_details.json')

def log_request(endpoint):
    """记录请求信息"""
    logger.info(f"接收到请求: {endpoint}")
    logger.info(f"请求方法: {request.method}")
    logger.info(f"请求IP: {request.remote_addr}")

@app.route('/api/manga/updates', methods=['GET', 'POST'])
def get_manga_updates():
    try:
        log_request('/api/manga/updates')
        
        # 检查最新更新数据文件是否存在
        if not os.path.exists(LATEST_UPDATES_FILE):
            logger.warning(f"文件不存在: {LATEST_UPDATES_FILE}")
            return jsonify({
                'code': 404,
                'message': '更新数据未找到',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        # 读取最新更新数据
        with open(LATEST_UPDATES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info("成功读取更新数据")
            
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"获取更新数据时出错: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/details', methods=['GET', 'POST'])
def get_manga_details():
    try:
        log_request('/api/manga/details')
        
        # 检查最新漫画详情数据文件是否存在
        if not os.path.exists(LATEST_MANGA_DETAILS_FILE):
            logger.warning(f"文件不存在: {LATEST_MANGA_DETAILS_FILE}")
            return jsonify({
                'code': 404,
                'message': '漫画详情数据未找到',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        # 读取最新漫画详情数据
        with open(LATEST_MANGA_DETAILS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info("成功读取漫画详情数据")
            
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"获取漫画详情时出错: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/history/updates/<timestamp>', methods=['GET', 'POST'])
def get_history_updates(timestamp):
    try:
        log_request(f'/api/manga/history/updates/{timestamp}')
        
        history_file = os.path.join(DATA_DIR, f'updates_{timestamp}.json')
        
        if not os.path.exists(history_file):
            logger.warning(f"历史更新文件不存在: {history_file}")
            return jsonify({
                'code': 404,
                'message': f'未找到时间戳为 {timestamp} 的历史更新数据',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"成功读取历史更新数据: {timestamp}")
            
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"获取历史更新数据时出错: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/history/details/<timestamp>', methods=['GET', 'POST'])
def get_history_details(timestamp):
    try:
        log_request(f'/api/manga/history/details/{timestamp}')
        
        history_file = os.path.join(DATA_DIR, f'manga_details_{timestamp}.json')
        
        if not os.path.exists(history_file):
            logger.warning(f"历史详情文件不存在: {history_file}")
            return jsonify({
                'code': 404,
                'message': f'未找到时间戳为 {timestamp} 的历史详情数据',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"成功读取历史详情数据: {timestamp}")
            
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"获取历史详情数据时出错: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/list/updates', methods=['GET', 'POST'])
def list_updates_history():
    try:
        log_request('/api/manga/list/updates')
        
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
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': history_list,
            'timestamp': int(datetime.now().timestamp())
        })
        
    except Exception as e:
        logger.error(f"获取更新历史列表时出错: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/list/details', methods=['GET', 'POST'])
def list_details_history():
    try:
        log_request('/api/manga/list/details')
        
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
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': history_list,
            'timestamp': int(datetime.now().timestamp())
        })
        
    except Exception as e:
        logger.error(f"获取详情历史列表时出错: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/latest', methods=['GET', 'POST'])
def get_latest_data():
    try:
        log_request('/api/manga/latest')
        
        # 检查文件是否存在
        if not os.path.exists(LATEST_UPDATES_FILE):
            logger.warning(f"最新更新文件不存在: {LATEST_UPDATES_FILE}")
            return jsonify({
                'code': 404,
                'message': '更新数据未找到',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        if not os.path.exists(LATEST_MANGA_DETAILS_FILE):
            logger.warning(f"最新详情文件不存在: {LATEST_MANGA_DETAILS_FILE}")
            return jsonify({
                'code': 404,
                'message': '漫画详情数据未找到',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        # 读取数据
        with open(LATEST_UPDATES_FILE, 'r', encoding='utf-8') as f:
            updates_data = json.load(f)
            
        with open(LATEST_MANGA_DETAILS_FILE, 'r', encoding='utf-8') as f:
            details_data = json.load(f)
            
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
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"获取最新数据时出错: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

if __name__ == '__main__':
    # 确保数据目录存在
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 启动服务器
    logger.info("API服务器启动...")
    app.run(host='0.0.0.0', port=7056) 