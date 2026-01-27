#!/usr/bin/env python3
"""Web 控制台 - ROS 版本（单机部署）"""

import rospy
from std_msgs.msg import String
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import json
import threading
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import AgentTools

app = Flask(__name__)
app.config['SECRET_KEY'] = 'agent-uav-secret'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 配置文件路径
QUESTIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cfg/questions.json")

class WebBridge:
    def __init__(self):
        rospy.init_node('web_console', anonymous=True)
        self.agent_tools = AgentTools()
        self.chat_history = []
        self.connected_clients = 0
        
        rospy.Subscriber('/agent_node/agent_log', String, self._on_agent_log)
        self.user_cmd_pub = rospy.Publisher('/agent_node/user_command', String, queue_size=10)
        
        rospy.loginfo("Web 控制台启动 - http://localhost:8080")
    
    def _on_agent_log(self, msg):
        try:
            log = json.loads(msg.data)
            self.chat_history.append(log)
            if len(self.chat_history) > 100:
                self.chat_history = self.chat_history[-100:]
            socketio.emit('agent_log', log, namespace='/')
        except Exception as e:
            rospy.logerr(f"日志处理失败: {e}")
    
    def get_status(self):
        return self.agent_tools.get_status_dict()
    
    def send_command(self, command):
        self.user_cmd_pub.publish(command)
        return {'status': 'ok', 'message': f'已发送: {command}'}
    
    def get_tools(self):
        return [{'name': t['name'], 'description': t['description']} for t in self.agent_tools.tools]
    
    def get_chat_history(self):
        return self.chat_history

web_bridge = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    try:
        return jsonify(web_bridge.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tools')
def get_tools():
    try:
        return jsonify({'tools': web_bridge.get_tools()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/questions', methods=['GET'])
def get_questions():
    """获取预设问题列表"""
    if not os.path.exists(QUESTIONS_FILE):
        with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({"questions": []}, f, indent=2, ensure_ascii=False)
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)
    return jsonify(questions)

@app.route('/api/agent_status', methods=['GET'])
def agent_status():
    """检查 Agent 是否运行"""
    try:
        nodes = rospy.get_published_topics()
        running = any('/agent_node' in topic[0] for topic in nodes)
        return jsonify({"running": running})
    except:
        return jsonify({"running": False})

@socketio.on('connect')
def handle_connect():
    web_bridge.connected_clients += 1
    emit('status_update', web_bridge.get_status())
    emit('chat_history', {'history': web_bridge.get_chat_history()})

@socketio.on('disconnect')
def handle_disconnect():
    web_bridge.connected_clients -= 1

@socketio.on('send_command')
def handle_command(data):
    try:
        command = data.get('command', '')
        result = web_bridge.send_command(command)
        emit('command_result', result)
    except Exception as e:
        emit('command_result', {'error': str(e)})

@socketio.on('request_status')
def handle_status_request():
    try:
        emit('status_update', web_bridge.get_status())
    except Exception as e:
        emit('status_update', {'error': str(e)})

def status_broadcast_thread():
    rate = rospy.Rate(2)
    while not rospy.is_shutdown():
        try:
            if web_bridge.connected_clients > 0:
                socketio.emit('status_update', web_bridge.get_status(), namespace='/')
        except:
            pass
        rate.sleep()

if __name__ == '__main__':
    try:
        web_bridge = WebBridge()
        broadcast_thread = threading.Thread(target=status_broadcast_thread, daemon=True)
        broadcast_thread.start()
        socketio.run(app, host='0.0.0.0', port=8080, debug=False)
    except rospy.ROSInterruptException:
        pass
    except KeyboardInterrupt:
        rospy.loginfo("关闭中...")
