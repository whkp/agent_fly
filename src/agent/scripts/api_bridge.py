#!/usr/bin/env python3
"""API 桥接服务器 - 机载计算机运行，提供 REST API"""

import rospy
from std_msgs.msg import String
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import AgentTools
from config_manager import ConfigManager

app = Flask(__name__)
CORS(app)

class APIBridge:
    def __init__(self):
        rospy.init_node('api_bridge', anonymous=True)
        self.agent_tools = AgentTools()
        self.config = ConfigManager()
        self.logs = []
        self.max_logs = 100
        
        rospy.Subscriber('/agent_node/agent_log', String, self._on_agent_log)
        self.user_cmd_pub = rospy.Publisher('/agent_node/user_command', String, queue_size=10)
        
        rospy.loginfo("API 桥接启动 - 端口 5000")
    
    def _on_agent_log(self, msg):
        try:
            log = json.loads(msg.data)
            self.logs.append(log)
            if len(self.logs) > self.max_logs:
                self.logs = self.logs[-self.max_logs:]
        except Exception as e:
            rospy.logerr(f"日志处理失败: {e}")
    
    def get_status(self):
        return self.agent_tools.get_status_dict()
    
    def send_command(self, command):
        self.user_cmd_pub.publish(command)
        return {'status': 'ok', 'message': f'已发送: {command}'}
    
    def takeoff(self, height=2.0):
        return self.agent_tools.call_tool('takeoff', {'height': height})
    
    def land(self):
        return self.agent_tools.call_tool('land', {})
    
    def set_position(self, x, y, z, yaw=0.0):
        return self.agent_tools.call_tool('set_goal', {'x': x, 'y': y, 'z': z, 'yaw': yaw})
    
    def get_logs(self, limit=20):
        return self.logs[-limit:]
    
    def get_tools(self):
        """获取工具列表"""
        return self.config.get_tools()
    
    def update_tools(self, tools_data):
        """更新工具配置"""
        try:
            import os
            tools_file = os.path.join(self.config.config_dir, 'tools.json')
            with open(tools_file, 'w', encoding='utf-8') as f:
                json.dump(tools_data, f, indent=2, ensure_ascii=False)
            self.config.reload()
            return True, "工具配置已更新"
        except Exception as e:
            return False, f"更新失败: {e}"
    
    def get_monitor_stats(self):
        """获取监控统计"""
        return self.agent_tools.get_monitor_stats()
    
    def get_monitor_history(self, limit=20):
        """获取调用历史"""
        return self.agent_tools.get_monitor_history(limit)

api_bridge = None

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        return jsonify(api_bridge.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/command', methods=['POST'])
def send_command():
    try:
        data = request.get_json()
        command = data.get('command', '')
        if not command:
            return jsonify({'error': '命令不能为空'}), 400
        return jsonify(api_bridge.send_command(command))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/takeoff', methods=['POST'])
def takeoff():
    try:
        data = request.get_json() or {}
        height = data.get('height', 2.0)
        return jsonify(api_bridge.takeoff(height))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/land', methods=['POST'])
def land():
    try:
        return jsonify(api_bridge.land())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/position', methods=['POST'])
def set_position():
    try:
        data = request.get_json()
        x = data.get('x', 0.0)
        y = data.get('y', 0.0)
        z = data.get('z', 2.0)
        yaw = data.get('yaw', 0.0)
        return jsonify(api_bridge.set_position(x, y, z, yaw))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    try:
        limit = int(request.args.get('limit', 20))
        return jsonify({'logs': api_bridge.get_logs(limit)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'ros_ok': not rospy.is_shutdown(),
        'node_name': rospy.get_name()
    })

# ========== 新增：工具管理 API ==========

@app.route('/api/tools', methods=['GET'])
def get_tools():
    """获取工具列表（参考 typefly）"""
    try:
        tools = api_bridge.get_tools()
        return jsonify({'tools': tools})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tools', methods=['POST'])
def update_tools():
    """更新工具配置（参考 typefly）"""
    try:
        data = request.get_json()
        if not data or 'tools' not in data:
            return jsonify({'success': False, 'msg': '缺少 tools 字段'}), 400
        
        success, message = api_bridge.update_tools(data)
        return jsonify({'success': success, 'msg': message})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500

@app.route('/api/tools/<tool_name>', methods=['POST'])
def call_tool_direct(tool_name):
    """直接调用工具（用于测试）"""
    try:
        data = request.get_json() or {}
        result = api_bridge.agent_tools.call_tool(tool_name, data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== 新增：监控 API ==========

@app.route('/api/monitor/stats', methods=['GET'])
def get_monitor_stats():
    """获取工具调用统计"""
    try:
        stats = api_bridge.get_monitor_stats()
        return jsonify({'stats': stats})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/monitor/history', methods=['GET'])
def get_monitor_history():
    """获取工具调用历史"""
    try:
        limit = int(request.args.get('limit', 20))
        history = api_bridge.get_monitor_history(limit)
        return jsonify({'history': history})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== 新增：配置管理 API ==========

@app.route('/api/config/reload', methods=['POST'])
def reload_config():
    """重新加载配置"""
    try:
        api_bridge.config.reload()
        # 重新初始化工具
        api_bridge.agent_tools.tools = api_bridge.agent_tools._init_tools()
        return jsonify({'success': True, 'msg': '配置已重新加载'})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)}), 500

@app.route('/api/agent_status', methods=['GET'])
def agent_status():
    """检查 Agent 是否运行（参考 typefly）"""
    try:
        nodes = rospy.get_published_topics()
        running = any('/agent_node' in topic[0] for topic in nodes)
        return jsonify({"running": running})
    except:
        return jsonify({"running": False})

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    try:
        api_bridge = APIBridge()
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        rospy.loginfo("API 服务运行中 - 测试: curl http://localhost:5000/api/status")
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
    except KeyboardInterrupt:
        rospy.loginfo("关闭中...")
