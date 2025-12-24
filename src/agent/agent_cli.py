#!/usr/bin/env python3
"""
Agent UAV 终端控制界面 (CLI)
使用 CERLAB autonomous_flight 导航系统
"""

import rospy
from std_msgs.msg import String
import json
import threading
import queue
import sys
import time
import os
from datetime import datetime

# 添加当前模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入工具类
from tools import AgentTools


class AgentCLI:
    def __init__(self):
        self.command_pub = None
        self.msg_queue = queue.Queue()
        self.running = True
        self.agent_tools = None
        self.chat_history = []
        
    def init_ros(self):
        """初始化ROS节点"""
        if not rospy.core.is_initialized():
            rospy.init_node('agent_cli', anonymous=True, disable_signals=True)
        
        self.command_pub = rospy.Publisher('/agent_node/user_command', String, queue_size=10)
        
        # 初始化工具类
        try:
            self.agent_tools = AgentTools()
            print("✅ 工具模块初始化成功")
        except Exception as e:
            print(f"⚠️ 工具模块初始化失败: {e}")
            self.agent_tools = None
        
        # 启动监听线程
        t = threading.Thread(target=self._ros_listener, daemon=True)
        t.start()
        
        print("✅ ROS 节点初始化完成")
        time.sleep(1)
        
    def _ros_listener(self):
        """ROS消息监听线程"""
        def cb_log(msg: String):
            try:
                data = json.loads(msg.data)
                self.msg_queue.put(data)
            except Exception as e:
                rospy.logerr(f"解析日志失败: {e}")
        
        rospy.Subscriber('/agent_node/agent_log', String, cb_log)
        rospy.spin()
    
    def display_banner(self):
        """显示欢迎界面"""
        print("\n" + "="*60)
        print("🚁 Agent UAV 控制面板 (CERLAB autonomous_flight)")
        print("="*60)
        print("\n📋 命令:")
        print("  1. 获取位置     - 获取当前位置")
        print("  2. 获取状态     - 获取飞行状态")
        print("  3. 自定义命令   - 输入自定义指令 [大模型]")
        print("  4. 显示日志     - 显示系统日志")
        print("-" * 60)
        print("  🛫 飞行控制:")
        print("  t. 起飞         - 起飞到指定高度")
        print("  l. 降落         - 降落到地面")
        print("  g. 导航         - 设置导航目标 [x, y, z]")
        print("-" * 60)
        print("  0. 退出")
        print("="*60 + "\n")
    
    def display_logs(self, n=10):
        """显示最新的日志"""
        print("\n📜 系统日志:")
        print("-" * 60)
        if not self.chat_history:
            print("  （暂无日志）")
        else:
            for msg in self.chat_history[-n:]:
                role = msg.get('role', 'unknown')
                msg_type = msg.get('type', 'Unknown')
                content = msg.get('content', '')
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                if role == "user":
                    print(f"[{timestamp}] 👤 用户: {content}")
                elif msg_type == "Answer":
                    print(f"[{timestamp}] 🤖 答案: {content}")
                elif msg_type == "Output":
                    if isinstance(content, dict):
                        action = content.get('action', '未知')
                        action_input = content.get('action_input', '')
                        print(f"[{timestamp}] 🔧 工具: {action}({action_input})")
                    else:
                        print(f"[{timestamp}] 🔧 输出: {content}")
                elif msg_type == "Observation":
                    print(f"[{timestamp}] 👁️  观察: {content}")
                else:
                    print(f"[{timestamp}] 📝 {msg_type}: {content}")
        print("-" * 60 + "\n")
    
    def send_command(self, command: str):
        """发送命令到Agent"""
        if self.command_pub is None:
            print("❌ ROS 发布器未初始化")
            return False
        
        try:
            self.command_pub.publish(command)
            print(f"📤 命令已发送: {command}")
            return True
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            return False
    
    def process_messages(self):
        """处理接收到的消息"""
        while not self.msg_queue.empty():
            try:
                msg = self.msg_queue.get_nowait()
                self.chat_history.append(msg)
            except queue.Empty:
                break
    
    def run(self):
        """主程序循环"""
        try:
            self.init_ros()
            self.display_banner()
            
            while self.running:
                self.process_messages()
                
                print("请选择 (0-4, t/l/g): ", end='', flush=True)
                
                try:
                    choice = input().strip().lower()
                except KeyboardInterrupt:
                    print("\n\n👋 退出")
                    break
                
                if choice == '0':
                    print("👋 退出")
                    break
                elif choice == '1':
                    self._get_position()
                elif choice == '2':
                    self._get_status()
                elif choice == '3':
                    cmd = input("📝 输入命令: ").strip()
                    if cmd:
                        self.send_command(cmd)
                elif choice == '4':
                    self.display_logs()
                elif choice == 't':
                    self._takeoff()
                elif choice == 'l':
                    self._land()
                elif choice == 'g':
                    self._goto()
                else:
                    print("❌ 无效选择")
                
                print()
        
        except KeyboardInterrupt:
            print("\n\n👋 退出")
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
    
    # ============== 工具调用 ==============
    
    def _check_tools(self):
        if self.agent_tools is None:
            print("❌ 工具模块未初始化")
            return False
        return True
    
    def _takeoff(self):
        if not self._check_tools():
            return
        try:
            height = input("🛫 起飞高度 (默认1.5m): ").strip()
            height = float(height) if height else 1.5
            print(f"🚀 起飞到 {height}m...")
            result = self.agent_tools.takeoff({'height': height})
            print(f"📋 {result.get('result', result)}")
        except ValueError:
            print("❌ 无效高度")
        except Exception as e:
            print(f"❌ 起飞失败: {e}")
    
    def _land(self):
        if not self._check_tools():
            return
        try:
            confirm = input("🛬 确认降落? (y/n): ").strip().lower()
            if confirm in ['', 'y', 'yes']:
                print("🛬 降落中...")
                result = self.agent_tools.land()
                print(f"📋 {result.get('result', result)}")
            else:
                print("❌ 已取消")
        except Exception as e:
            print(f"❌ 降落失败: {e}")
    
    def _goto(self):
        if not self._check_tools():
            return
        try:
            print("📍 输入目标坐标:")
            x = float(input("   X (m): ").strip() or "0")
            y = float(input("   Y (m): ").strip() or "0")
            z = float(input("   Z (m): ").strip() or "1.5")
            
            print(f"🎯 导航到 ({x}, {y}, {z})...")
            result = self.agent_tools.set_goal({'x': x, 'y': y, 'z': z})
            print(f"📋 {result.get('result', result)}")
        except ValueError:
            print("❌ 无效坐标")
        except Exception as e:
            print(f"❌ 导航失败: {e}")
    
    def _get_position(self):
        if not self._check_tools():
            return
        try:
            result = self.agent_tools.get_current_position()
            print(f"📍 {result.get('result', result)}")
        except Exception as e:
            print(f"❌ 获取位置失败: {e}")
    
    def _get_status(self):
        if not self._check_tools():
            return
        try:
            result = self.agent_tools.get_flight_status()
            print(f"📊 {result.get('result', result)}")
        except Exception as e:
            print(f"❌ 获取状态失败: {e}")


if __name__ == '__main__':
    cli = AgentCLI()
    cli.run()
