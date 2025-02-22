import os
import sys
import signal
import time
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def read_pid():
    """读取PID文件"""
    try:
        if os.path.exists('api_server.pid'):
            with open('api_server.pid', 'r') as f:
                return int(f.read().strip())
    except Exception as e:
        logger.error(f"读取PID文件失败: {e}")
    return None

def is_running(pid):
    """检查进程是否运行中"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def start_server():
    """启动服务器"""
    if os.path.exists('api_server.pid'):
        pid = read_pid()
        if pid and is_running(pid):
            logger.info(f"服务器已经在运行中 (PID: {pid})")
            return
        
    logger.info("启动服务器...")
    os.system('python api_server.py &')
    time.sleep(2)  # 等待服务器启动
    
    pid = read_pid()
    if pid and is_running(pid):
        logger.info(f"服务器启动成功 (PID: {pid})")
    else:
        logger.error("服务器启动失败")

def stop_server():
    """停止服务器"""
    pid = read_pid()
    if not pid:
        logger.info("没有找到运行中的服务器")
        return
        
    if not is_running(pid):
        logger.info("服务器已经停止")
        if os.path.exists('api_server.pid'):
            os.remove('api_server.pid')
        return
        
    try:
        # 发送SIGTERM信号
        os.kill(pid, signal.SIGTERM)
        
        # 等待进程结束
        for _ in range(5):  # 最多等待5秒
            if not is_running(pid):
                logger.info("服务器已停止")
                if os.path.exists('api_server.pid'):
                    os.remove('api_server.pid')
                return
            time.sleep(1)
            
        # 如果进程还在运行，强制结束
        if is_running(pid):
            os.kill(pid, signal.SIGKILL)
            logger.info("服务器已强制停止")
            if os.path.exists('api_server.pid'):
                os.remove('api_server.pid')
            
    except Exception as e:
        logger.error(f"停止服务器时出错: {e}")

def restart_server():
    """重启服务器"""
    stop_server()
    time.sleep(2)  # 等待端口释放
    start_server()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python server_control.py [start|stop|restart]")
        sys.exit(1)
        
    command = sys.argv[1].lower()
    
    if command == 'start':
        start_server()
    elif command == 'stop':
        stop_server()
    elif command == 'restart':
        restart_server()
    else:
        print("无效的命令。请使用 start, stop 或 restart")
        sys.exit(1) 