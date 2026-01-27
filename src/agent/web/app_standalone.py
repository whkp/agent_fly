#!/usr/bin/env python3
"""Web 控制台 - 独立版本（无需 ROS，适合 Windows 地面站）"""

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import requests
import json
import threading
import time
import argparse
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'agent-uav-secret'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 配置文件路径
QUESTIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cfg/questions.json")

class RemoteBridge:
    def __init__(self, agent_host='192.168.1.100', agent_port=5000):
        self.agent_url = f"http://{agent_host}:{agent_port}/api"
        self.connected = False
        self.connected_clients = 0
        self.chat_history = []
        
        self._test_connection()
        self.polling_thread = threading.Thread(target=self._poll_status, daemon=True)
        self.polling_thread.start()
        
        print(f"远程桥接初始化 - 连接: {self.agent_url}")
    
    def _test_connection(self):
        try:
            response = requests.get(f"{self.agent_url}/status", timeout=2)
            self.connected = (response.status_code == 200)
            print("✓ 连接成功" if self.connected else "✗ 连接失败")
        except:
            self.connected = False
            print("✗ 无法连接到机载")
    
    def _poll_status(self):
        while True:
            try:
                if self.connected_clients > 0:
                    status = self.get_status()
                    if status and 'error' not in status:
                        socketio.emit('status_update', status, namespace='/')
                time.sleep(0.5)
            except:
                time.sleep(1)
    
    def get_status(self):
        try:
            response = requests.get(f"{self.agent_url}/status", timeout=2)
            if response.status_code == 200:
                self.connected = True
                return response.json()
            self.connected = False
            return {'error': 'Connection failed'}
        except Exception as e:
            self.connected = False
            return {'error': str(e)}
    
    def send_command(self, command):
        try:
            response = requests.post(f"{self.agent_url}/command", json={'command': command}, timeout=5)
            if response.status_code == 200:
                self.chat_history.append({'role': 'user', 'type': 'Question', 'content': command})
                return response.json()
            return {'error': f'HTTP {response.status_code}'}
        except Exception as e:
            return {'error': str(e)}
    
    def get_logs(self, limit=20):
        try:
            response = requests.get(f"{self.agent_url}/logs", params={'limit': limit}, timeout=2)
            return response.json().get('logs', []) if response.status_code == 200 else []
        except:
            return []

remote_bridge = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    try:
        return jsonify(remote_bridge.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/connection')
def get_connection():
    return jsonify({'connected': remote_bridge.connected})

@app.route('/api/questions', methods=['GET'])
def get_questions():
    """获取预设问题列表"""
    if not os.path.exists(QUESTIONS_FILE):
        with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({"questions": []}, f, indent=2, ensure_ascii=False)
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)
    return jsonify(questions)

@socketio.on('connect')
def handle_connect():
    remote_bridge.connected_clients += 1
    emit('status_update', remote_bridge.get_status())
    emit('connection_status', {'connected': remote_bridge.connected})
    for log in remote_bridge.get_logs(50):
        emit('agent_log', log)

@socketio.on('disconnect')
def handle_disconnect():
    remote_bridge.connected_clients -= 1

@socketio.on('send_command')
def handle_command(data):
    try:
        command = data.get('command', '')
        result = remote_bridge.send_command(command)
        emit('command_result', result)
        socketio.emit('agent_log', {'role': 'user', 'type': 'Question', 'content': command}, namespace='/')
    except Exception as e:
        emit('command_result', {'error': str(e)})

@socketio.on('request_status')
def handle_status_request():
    try:
        emit('status_update', remote_bridge.get_status())
    except Exception as e:
        emit('status_update', {'error': str(e)})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Agent Web Console (Standalone)')
    parser.add_argument('--host', default='192.168.1.100', help='机载 IP')
    parser.add_argument('--port', type=int, default=5000, help='机载端口')
    parser.add_argument('--web-port', type=int, default=8080, help='Web 端口')
    args = parser.parse_args()
    
    try:
        remote_bridge = RemoteBridge(args.host, args.port)
        print(f"Web 控制台启动 - 访问: http://localhost:{args.web_port}")
        socketio.run(app, host='0.0.0.0', port=args.web_port, debug=False)
    except KeyboardInterrupt:
        print("\n关闭中...")
