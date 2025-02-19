from flask import Flask, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)  # 启用CORS支持

# 数据文件路径
DATA_DIR = 'data'
LATEST_UPDATES_FILE = os.path.join(DATA_DIR, 'latest_updates.json')
LATEST_MANGA_DETAILS_FILE = os.path.join(DATA_DIR, 'latest_manga_details.json')

@app.route('/api/manga/updates', methods=['GET', 'POST'])
def get_manga_updates():
    try:
        # 检查最新更新数据文件是否存在
        if not os.path.exists(LATEST_UPDATES_FILE):
            return jsonify({
                'code': 404,
                'message': 'Updates data not found',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        # 读取最新更新数据
        with open(LATEST_UPDATES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return jsonify(data)
        
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Error: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/details', methods=['GET', 'POST'])
def get_manga_details():
    try:
        # 检查最新漫画详情数据文件是否存在
        if not os.path.exists(LATEST_MANGA_DETAILS_FILE):
            return jsonify({
                'code': 404,
                'message': 'Manga details not found',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        # 读取最新漫画详情数据
        with open(LATEST_MANGA_DETAILS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return jsonify(data)
        
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Error: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/history/updates/<timestamp>', methods=['GET', 'POST'])
def get_history_updates(timestamp):
    try:
        history_file = os.path.join(DATA_DIR, f'updates_{timestamp}.json')
        
        if not os.path.exists(history_file):
            return jsonify({
                'code': 404,
                'message': f'History updates not found for timestamp: {timestamp}',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return jsonify(data)
        
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Error: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/history/details/<timestamp>', methods=['GET', 'POST'])
def get_history_details(timestamp):
    try:
        history_file = os.path.join(DATA_DIR, f'manga_details_{timestamp}.json')
        
        if not os.path.exists(history_file):
            return jsonify({
                'code': 404,
                'message': f'History details not found for timestamp: {timestamp}',
                'data': None,
                'timestamp': int(datetime.now().timestamp())
            }), 404
            
        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return jsonify(data)
        
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Error: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/list/updates', methods=['GET', 'POST'])
def list_updates_history():
    try:
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
            
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': history_list,
            'timestamp': int(datetime.now().timestamp())
        })
        
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Error: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

@app.route('/api/manga/list/details', methods=['GET', 'POST'])
def list_details_history():
    try:
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
            
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': history_list,
            'timestamp': int(datetime.now().timestamp())
        })
        
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Error: {str(e)}',
            'data': None,
            'timestamp': int(datetime.now().timestamp())
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7056) 