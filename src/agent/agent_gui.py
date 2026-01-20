#!/usr/bin/env python3
"""
Agent UAV GUI 控制界面
功能：
1. 实时摄像头显示
2. 工具按键快捷调用
3. LLM聊天日志显示
4. 用户输入区域
"""

import sys
import os
import json
import queue
import threading
import signal
from datetime import datetime

# ROS
import rospy
from std_msgs.msg import String
from sensor_msgs.msg import Image as ROSImage

# OpenCV & NumPy
import cv2
import numpy as np
from cv_bridge import CvBridge

# PyQt5
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QSplitter, QGroupBox,
    QGridLayout, QScrollArea, QFrame, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QSpinBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QImage, QPixmap, QFont, QTextCursor

# 添加当前模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import AgentTools


class ROSSignals(QObject):
    """ROS消息信号"""
    log_received = pyqtSignal(dict)


class GoalDialog(QDialog):
    """目标点设置对话框"""
    def __init__(self, current_pos, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 设置目标点")
        self.setModal(True)
        self.setMinimumWidth(350)
        
        layout = QFormLayout(self)
        
        # 显示当前位置
        current_label = QLabel(f"当前位置: X={current_pos[0]:.2f}, Y={current_pos[1]:.2f}, Z={current_pos[2]:.2f}")
        current_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addRow(current_label)
        
        # X坐标输入
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(-100.0, 100.0)
        self.x_spin.setValue(current_pos[0])
        self.x_spin.setDecimals(2)
        self.x_spin.setSingleStep(0.5)
        self.x_spin.setSuffix(" m")
        layout.addRow("X 坐标:", self.x_spin)
        
        # Y坐标输入
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(-100.0, 100.0)
        self.y_spin.setValue(current_pos[1])
        self.y_spin.setDecimals(2)
        self.y_spin.setSingleStep(0.5)
        self.y_spin.setSuffix(" m")
        layout.addRow("Y 坐标:", self.y_spin)
        
        # Z坐标输入
        self.z_spin = QDoubleSpinBox()
        self.z_spin.setRange(0.5, 20.0)
        self.z_spin.setValue(current_pos[2])
        self.z_spin.setDecimals(2)
        self.z_spin.setSingleStep(0.5)
        self.z_spin.setSuffix(" m")
        layout.addRow("Z 坐标 (高度):", self.z_spin)
        
        # 快捷按钮
        quick_layout = QHBoxLayout()
        quick_buttons = [
            ("⬆️ +5m", lambda: self.adjust_position(5, 0, 0)),
            ("⬇️ -5m", lambda: self.adjust_position(-5, 0, 0)),
            ("⬅️ +5m", lambda: self.adjust_position(0, 5, 0)),
            ("➡️ -5m", lambda: self.adjust_position(0, -5, 0)),
        ]
        for text, callback in quick_buttons:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            quick_layout.addWidget(btn)
        
        layout.addRow("快捷调整:", quick_layout)
        
        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def adjust_position(self, dx, dy, dz):
        """调整位置"""
        self.x_spin.setValue(self.x_spin.value() + dx)
        self.y_spin.setValue(self.y_spin.value() + dy)
        self.z_spin.setValue(self.z_spin.value() + dz)
    
    def get_goal(self):
        """获取目标点"""
        return {
            'x': self.x_spin.value(),
            'y': self.y_spin.value(),
            'z': self.z_spin.value()
        }


class RotationDialog(QDialog):
    """旋转角度设置对话框"""
    def __init__(self, current_yaw, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔄 设置旋转角度")
        self.setModal(True)
        self.setMinimumWidth(350)
        
        layout = QFormLayout(self)
        
        # 显示当前角度
        current_label = QLabel(f"当前朝向: {current_yaw:.1f}°")
        current_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addRow(current_label)
        
        # 角度输入方式选择
        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(-180.0, 180.0)
        self.angle_spin.setValue(0.0)
        self.angle_spin.setDecimals(1)
        self.angle_spin.setSingleStep(15.0)
        self.angle_spin.setSuffix("°")
        self.angle_spin.setWrapping(True)
        layout.addRow("目标角度 (相对):", self.angle_spin)
        
        # 绝对角度输入
        self.absolute_spin = QDoubleSpinBox()
        self.absolute_spin.setRange(0.0, 360.0)
        self.absolute_spin.setValue(current_yaw)
        self.absolute_spin.setDecimals(1)
        self.absolute_spin.setSingleStep(15.0)
        self.absolute_spin.setSuffix("°")
        self.absolute_spin.setWrapping(True)
        layout.addRow("目标角度 (绝对):", self.absolute_spin)
        
        # 快捷按钮
        quick_layout = QGridLayout()
        quick_buttons = [
            ("↑ 北 (0°)", lambda: self.set_absolute(0), 0, 1),
            ("↗ 东北 (45°)", lambda: self.set_absolute(45), 0, 2),
            ("← 西 (270°)", lambda: self.set_absolute(270), 1, 0),
            ("🔄 左转90°", lambda: self.adjust_angle(90), 1, 1),
            ("🔃 右转90°", lambda: self.adjust_angle(-90), 1, 2),
            ("→ 东 (90°)", lambda: self.set_absolute(90), 1, 3),
            ("↙ 西南 (225°)", lambda: self.set_absolute(225), 2, 0),
            ("↓ 南 (180°)", lambda: self.set_absolute(180), 2, 1),
            ("↘ 东南 (135°)", lambda: self.set_absolute(135), 2, 2),
        ]
        for text, callback, row, col in quick_buttons:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            btn.setMinimumHeight(35)
            quick_layout.addWidget(btn, row, col)
        
        layout.addRow("快捷方向:", quick_layout)
        
        # 说明
        info_label = QLabel(
            "💡 提示：\n"
            "• 相对角度：基于当前朝向旋转\n"
            "• 绝对角度：面向指定方向（0°=北，90°=东）"
        )
        info_label.setStyleSheet("color: #888; font-size: 9pt;")
        layout.addRow(info_label)
        
        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.current_yaw = current_yaw
    
    def adjust_angle(self, delta):
        """调整相对角度"""
        self.angle_spin.setValue(self.angle_spin.value() + delta)
    
    def set_absolute(self, angle):
        """设置绝对角度"""
        self.absolute_spin.setValue(angle)
    
    def get_rotation(self):
        """获取旋转信息"""
        return {
            'relative': self.angle_spin.value(),
            'absolute': self.absolute_spin.value(),
            'use_absolute': abs(self.absolute_spin.value() - self.current_yaw) > 1.0
        }


class AgentGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🚁 Agent UAV 控制面板")
        self.setGeometry(100, 100, 1400, 900)
        
        # ROS相关
        self.command_pub = None
        self.direct_tool_pub = None  # 直接工具调用发布器
        self.emergency_stop_pub = None  # 紧急停止发布器
        self.agent_tools = None
        self.cv_bridge = CvBridge()
        self.current_image = None
        self.image_lock = threading.Lock()
        
        # 关闭标志
        self.is_closing = False
        
        # 信号
        self.signals = ROSSignals()
        self.signals.log_received.connect(self.on_log_received)
        
        # 聊天历史
        self.chat_history = []
        
        # 初始化UI
        self.init_ui()
        
        # 初始化ROS
        self.init_ros()
        
        # 定时器更新图像
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_camera_display)
        self.timer.start(33)  # 30 FPS
    
    def init_ui(self):
        """初始化UI界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.setGeometry(100, 100, 1600, 1000)  # 增大窗口尺寸
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        
        # 左侧：摄像头 + 工具按钮
        left_panel = self.create_left_panel()
        
        # 右侧：聊天日志 + 输入
        right_panel = self.create_right_panel()
        
        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        
        main_layout.addWidget(splitter)
    
    def create_left_panel(self):
        """创建左侧面板：摄像头 + 工具按钮"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # 摄像头显示区域
        camera_group = QGroupBox("📷 机载摄像头")
        camera_layout = QVBoxLayout()
        
        self.camera_label = QLabel()
        self.camera_label.setMinimumSize(960, 720)
        self.camera_label.setMaximumSize(960, 720)
        self.camera_label.setStyleSheet("background-color: black; border: 2px solid #555;")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setText("等待图像...")
        
        camera_layout.addWidget(self.camera_label)
        camera_group.setLayout(camera_layout)
        
        # 工具按钮区域
        tools_group = QGroupBox("🛠️ 快捷工具")
        tools_layout = QGridLayout()
        
        # 定义按钮
        buttons = [
            ("🛫 起飞", self.on_takeoff, 0, 0),
            ("🛬 降落", self.on_land, 0, 1),
            (" 紧急停止", self.on_emergency_stop, 0, 2, 1, 1),
            (" 获取位置", self.on_get_position, 1, 0),
            ("📊 获取状态", self.on_get_status, 1, 1),
            (" 检测前方物体", self.on_detect_objects, 1, 2),
            ("🎯 设置目标点", self.on_set_goal_dialog, 2, 0),
            ("🔄 设置旋转角度", self.on_set_rotation_dialog, 2, 1),
            ("⏹️ 终止任务", self.on_stop_task, 2, 2),
            ("⬆️ 上升1m", lambda: self.quick_move("up"), 3, 0),
            ("⬇️ 下降1m", lambda: self.quick_move("down"), 3, 1),
            ("⬅️ 左移2m", lambda: self.quick_move("left"), 4, 0),
            ("➡️ 右移2m", lambda: self.quick_move("right"), 4, 1),
            ("⬆️ 前进3m", lambda: self.quick_move("forward"), 5, 0),
            ("⬇️ 后退3m", lambda: self.quick_move("backward"), 5, 1),
        ]
        
        for button_info in buttons:
            text, callback, row, col = button_info[:4]
            rowspan = button_info[4] if len(button_info) > 4 else 1
            colspan = button_info[5] if len(button_info) > 5 else 1
            
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            btn.setMinimumHeight(40)
            
            # 紧急停止按钮使用红色
            if "紧急停止" in text:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #d32f2f;
                        color: white;
                        font-weight: bold;
                        border: 2px solid #b71c1c;
                    }
                    QPushButton:hover {
                        background-color: #f44336;
                    }
                    QPushButton:pressed {
                        background-color: #b71c1c;
                    }
                """)
            # 终止任务按钮使用橙色
            elif "终止任务" in text:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f57c00;
                        color: white;
                        font-weight: bold;
                        border: 2px solid #e65100;
                    }
                    QPushButton:hover {
                        background-color: #ff9800;
                    }
                    QPushButton:pressed {
                        background-color: #e65100;
                    }
                """)
            
            tools_layout.addWidget(btn, row, col, rowspan, colspan)
        
        tools_group.setLayout(tools_layout)
        
        layout.addWidget(camera_group)
        layout.addWidget(tools_group)
        layout.addStretch()
        
        return panel
    
    def create_right_panel(self):
        """创建右侧面板：聊天日志 + 输入"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # 聊天日志显示
        log_group = QGroupBox("💬 LLM 聊天日志")
        log_layout = QVBoxLayout()
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Monospace", 10))
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #555;
            }
        """)
        
        log_layout.addWidget(self.log_display)
        log_group.setLayout(log_layout)
        
        # 输入区域
        input_group = QGroupBox("✍️ 用户输入")
        input_layout = QVBoxLayout()
        
        # 输入框
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入指令，例如：飞到坐标(10, 5, 2) 或 向前飞5米")
        self.input_field.setMinimumHeight(40)
        self.input_field.returnPressed.connect(self.on_send_command)
        
        # 发送按钮
        send_btn = QPushButton("🚀 发送指令")
        send_btn.clicked.connect(self.on_send_command)
        send_btn.setMinimumHeight(40)
        
        # 示例指令
        examples_label = QLabel(
            "💡 示例指令：\n"
            "  • 飞到坐标(10, 5, 2)\n"
            "  • 向前飞5米\n"
            "  • 起飞到2米高度\n"
            "  • 飞往柱子\n"
            "  • 检测前方物体"
        )
        examples_label.setStyleSheet("color: #888; font-size: 9pt;")
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(send_btn)
        input_layout.addWidget(examples_label)
        input_group.setLayout(input_layout)
        
        layout.addWidget(log_group, stretch=4)
        layout.addWidget(input_group, stretch=1)
        
        return panel
    
    def init_ros(self):
        """初始化ROS节点"""
        try:
            if not rospy.core.is_initialized():
                rospy.init_node('agent_gui', anonymous=True, disable_signals=True)
            
            # 发布器
            self.command_pub = rospy.Publisher('/agent_node/user_command', String, queue_size=10)
            self.direct_tool_pub = rospy.Publisher('/agent_node/direct_tool_call', String, queue_size=10)
            self.emergency_stop_pub = rospy.Publisher('/agent_node/emergency_stop', String, queue_size=10)
            
            # 订阅器
            rospy.Subscriber('/agent_node/agent_log', String, self.ros_log_callback)
            rospy.Subscriber('/camera/color/image_raw', ROSImage, self.ros_image_callback)
            
            # 初始化工具
            self.agent_tools = AgentTools()
            
            # 启动ROS spin线程（设置为daemon线程，主线程退出时自动结束）
            self.ros_thread = threading.Thread(target=self.ros_spin_thread, daemon=True)
            self.ros_thread.start()
            
            self.append_log("SYSTEM", "✅ ROS 节点初始化成功", "#00ff00")
            
        except Exception as e:
            self.append_log("ERROR", f"❌ ROS 初始化失败: {e}", "#ff0000")
    
    def ros_spin_thread(self):
        """ROS spin线程"""
        while not rospy.is_shutdown() and not self.is_closing:
            try:
                rospy.sleep(0.1)
            except:
                break
    
    def ros_log_callback(self, msg):
        """ROS日志回调"""
        try:
            data = json.loads(msg.data)
            self.signals.log_received.emit(data)
        except Exception as e:
            print(f"解析日志失败: {e}")
    
    def ros_image_callback(self, msg):
        """ROS图像回调"""
        try:
            # 尝试使用cv_bridge
            img = self.cv_bridge.imgmsg_to_cv2(msg, "bgr8")
            with self.image_lock:
                self.current_image = img
        except Exception as e:
            # 备用方案：手动解码
            if "libgdal" in str(e) or "TIFF" in str(e):
                try:
                    if msg.encoding == "bgr8":
                        img_array = np.frombuffer(msg.data, dtype=np.uint8)
                        img = img_array.reshape((msg.height, msg.width, 3))
                        with self.image_lock:
                            self.current_image = img
                except:
                    pass
    
    def update_camera_display(self):
        """更新摄像头显示"""
        with self.image_lock:
            if self.current_image is not None:
                img = self.current_image.copy()
            else:
                return
        
        # 转换为Qt格式
        height, width, channel = img.shape
        bytes_per_line = 3 * width
        q_img = QImage(img.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
        
        # 缩放到显示区域
        pixmap = QPixmap.fromImage(q_img)
        scaled_pixmap = pixmap.scaled(
            self.camera_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.camera_label.setPixmap(scaled_pixmap)
    
    def on_log_received(self, data):
        """处理接收到的日志"""
        self.chat_history.append(data)
        
        role = data.get('role', 'unknown')
        msg_type = data.get('type', 'Unknown')
        content = data.get('content', '')
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if role == "user":
            self.append_log("USER", f"👤 {content}", "#4ec9b0")
        elif msg_type == "Thought":
            self.append_log("THOUGHT", f"🧠 {content}", "#c586c0")
        elif msg_type == "Action":
            self.append_log("ACTION", f"🔧 {content}", "#dcdcaa")
        elif msg_type == "Observation":
            self.append_log("OBSERVATION", f"👁️ {content}", "#9cdcfe")
        elif msg_type == "Final":
            self.append_log("FINAL", f"✅ {content}", "#4ec9b0")
        elif msg_type == "Warning":
            self.append_log("WARNING", f"⚠️ {content}", "#ff9800")
        elif msg_type == "DirectTool":
            self.append_log("RESULT", f"📊 {content}", "#4ec9b0")
        elif msg_type == "Error":
            self.append_log("ERROR", f"❌ {content}", "#ff0000")
        else:
            self.append_log(msg_type.upper(), content, "#d4d4d4")
    
    def append_log(self, label, text, color="#d4d4d4"):
        """添加日志到显示区域"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        html = f'<span style="color: #888;">[{timestamp}]</span> '
        html += f'<span style="color: {color}; font-weight: bold;">[{label}]</span> '
        html += f'<span style="color: {color};">{text}</span><br>'
        
        self.log_display.moveCursor(QTextCursor.End)
        self.log_display.insertHtml(html)
        self.log_display.moveCursor(QTextCursor.End)
    
    def send_command(self, command):
        """发送命令到Agent（会触发LLM思考）"""
        if self.command_pub is None:
            self.append_log("ERROR", "❌ ROS 发布器未初始化", "#ff0000")
            return
        
        try:
            self.command_pub.publish(command)
            self.append_log("SYSTEM", f"📤 命令已发送: {command}", "#00ff00")
        except Exception as e:
            self.append_log("ERROR", f"❌ 发送失败: {e}", "#ff0000")
    
    def call_tool_directly(self, tool_name, params=None):
        """直接调用工具（不触发LLM思考）"""
        if self.direct_tool_pub is None:
            self.append_log("ERROR", "❌ ROS 发布器未初始化", "#ff0000")
            return
        
        try:
            tool_call = {
                'tool': tool_name,
                'params': params or {}
            }
            self.direct_tool_pub.publish(json.dumps(tool_call))
            self.append_log("SYSTEM", f"🔧 直接调用工具: {tool_name}", "#00ff00")
        except Exception as e:
            self.append_log("ERROR", f"❌ 工具调用失败: {e}", "#ff0000")
    
    # ============== 事件处理 ==============
    
    def on_send_command(self):
        """发送用户输入的命令"""
        command = self.input_field.text().strip()
        if command:
            self.send_command(command)
            self.input_field.clear()
    
    def on_takeoff(self):
        """起飞"""
        if self.agent_tools:
            try:
                self.call_tool_directly('takeoff', {'height': 1.5})
            except Exception as e:
                self.append_log("ERROR", f"❌ 起飞失败: {e}", "#ff0000")
    
    def on_land(self):
        """降落"""
        if self.agent_tools:
            try:
                self.call_tool_directly('land', {})
            except Exception as e:
                self.append_log("ERROR", f"❌ 降落失败: {e}", "#ff0000")
    
    def on_get_position(self):
        """获取位置"""
        if self.agent_tools:
            try:
                self.call_tool_directly('get_current_position', {})
            except Exception as e:
                self.append_log("ERROR", f"❌ 获取位置失败: {e}", "#ff0000")
    
    def on_get_status(self):
        """获取状态"""
        if self.agent_tools:
            try:
                self.call_tool_directly('get_flight_status', {})
            except Exception as e:
                self.append_log("ERROR", f"❌ 获取状态失败: {e}", "#ff0000")
    
    def on_set_goal(self):
        """设置目标（使用当前位置+前方5米）- 保留用于兼容"""
        if self.agent_tools:
            try:
                status = self.agent_tools.get_status_dict()
                x = status['x'] + 5.0
                y = status['y']
                z = status['z']
                result = self.agent_tools.set_goal({'x': x, 'y': y, 'z': z})
                self.append_log("TOOL", f"🎯 导航: {result.get('result', result)}", "#4ec9b0")
            except Exception as e:
                self.append_log("ERROR", f"❌ 设置目标失败: {e}", "#ff0000")
    
    def on_set_goal_dialog(self):
        """打开目标点设置对话框"""
        if self.agent_tools:
            try:
                # 获取当前位置
                status = self.agent_tools.get_status_dict()
                current_pos = (status['x'], status['y'], status['z'])
                
                # 打开对话框
                dialog = GoalDialog(current_pos, self)
                if dialog.exec_() == QDialog.Accepted:
                    goal = dialog.get_goal()
                    self.call_tool_directly('set_goal', goal)
                    self.append_log("TOOL", 
                        f"🎯 导航至 ({goal['x']:.2f}, {goal['y']:.2f}, {goal['z']:.2f})", 
                        "#4ec9b0")
            except Exception as e:
                self.append_log("ERROR", f"❌ 设置目标失败: {e}", "#ff0000")
    
    def on_set_rotation_dialog(self):
        """打开旋转角度设置对话框"""
        if self.agent_tools:
            try:
                # 获取当前朝向
                status = self.agent_tools.get_status_dict()
                current_yaw = status.get('yaw', 0.0)
                
                # 打开对话框
                dialog = RotationDialog(current_yaw, self)
                if dialog.exec_() == QDialog.Accepted:
                    rotation = dialog.get_rotation()
                    
                    # 直接调用 rotate 工具，不触发 LLM，不检测物体
                    if rotation['use_absolute']:
                        # 计算相对角度
                        target_yaw = rotation['absolute']
                        delta_yaw = target_yaw - current_yaw
                        # 归一化到 [-180, 180]
                        while delta_yaw > 180:
                            delta_yaw -= 360
                        while delta_yaw < -180:
                            delta_yaw += 360
                        
                        self.call_tool_directly('rotate', {'angle': delta_yaw, 'detect': False})
                        self.append_log("TOOL", f"🔄 旋转至绝对角度 {target_yaw:.1f}° (相对旋转 {delta_yaw:+.1f}°)", "#4ec9b0")
                    else:
                        delta_yaw = rotation['relative']
                        self.call_tool_directly('rotate', {'angle': delta_yaw, 'detect': False})
                        self.append_log("TOOL", f"🔄 相对旋转 {delta_yaw:+.1f}°", "#4ec9b0")
                        
            except Exception as e:
                self.append_log("ERROR", f"❌ 设置旋转失败: {e}", "#ff0000")
    
    def on_detect_objects(self):
        """检测物体"""
        if self.agent_tools:
            try:
                self.call_tool_directly('get_detected_objects', {})
            except Exception as e:
                self.append_log("ERROR", f"❌ 检测失败: {e}", "#ff0000")
    
    def on_emergency_stop(self):
        """紧急停止 - 立即悬停"""
        if self.emergency_stop_pub is None:
            self.append_log("ERROR", "❌ ROS 发布器未初始化", "#ff0000")
            return
        
        try:
            self.emergency_stop_pub.publish("stop")
            self.append_log("SYSTEM", "🚨 紧急停止信号已发送！无人机将立即悬停", "#ff0000")
        except Exception as e:
            self.append_log("ERROR", f"❌ 紧急停止失败: {e}", "#ff0000")
    
    def on_stop_task(self):
        """终止任务 - 停止 LLM 思考"""
        if self.emergency_stop_pub is None:
            self.append_log("ERROR", "❌ ROS 发布器未初始化", "#ff0000")
            return
        
        try:
            self.emergency_stop_pub.publish("stop")
            self.append_log("SYSTEM", "⏹️ 任务终止信号已发送！LLM 将停止思考", "#ff9800")
        except Exception as e:
            self.append_log("ERROR", f"❌ 终止任务失败: {e}", "#ff0000")
    
    def quick_move(self, direction):
        """快速移动"""
        if self.agent_tools:
            try:
                status = self.agent_tools.get_status_dict()
                x, y, z = status['x'], status['y'], status['z']
                
                if direction == "forward":
                    x += 3.0
                elif direction == "backward":
                    x -= 3.0
                elif direction == "left":
                    y += 2.0
                elif direction == "right":
                    y -= 2.0
                elif direction == "up":
                    z += 1.0
                elif direction == "down":
                    z -= 1.0
                
                self.call_tool_directly('set_goal', {'x': x, 'y': y, 'z': z})
                self.append_log("TOOL", f"🎯 移动({direction})", "#4ec9b0")
            except Exception as e:
                self.append_log("ERROR", f"❌ 移动失败: {e}", "#ff0000")
    
    def closeEvent(self, event):
        """关闭事件"""
        print("\n🛑 正在关闭GUI...")
        
        # 设置关闭标志
        self.is_closing = True
        
        # 停止定时器
        if hasattr(self, 'timer'):
            self.timer.stop()
        
        # 关闭ROS节点
        if rospy.core.is_initialized():
            try:
                rospy.signal_shutdown("GUI closed")
            except:
                pass
        
        print("✅ GUI已关闭")
        event.accept()
    
    def shutdown(self):
        """强制关闭"""
        self.is_closing = True
        self.close()


def signal_handler(signum, frame):
    """信号处理器 - 处理Ctrl+C"""
    print("\n🛑 收到中断信号 (Ctrl+C)，正在关闭...")
    
    # 获取QApplication实例
    app = QApplication.instance()
    if app:
        # 关闭所有窗口
        for window in app.topLevelWidgets():
            if isinstance(window, AgentGUI):
                window.shutdown()
        
        # 退出应用
        app.quit()
    
    # 强制退出（如果QApplication.quit()没有生效）
    import time
    time.sleep(0.5)
    sys.exit(0)


def main():
    # 设置信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    window = AgentGUI()
    window.show()
    
    # 创建定时器来处理Python信号
    # PyQt5的事件循环会阻塞Python信号，需要定期让Python处理信号
    timer = QTimer()
    timer.start(500)  # 每500ms检查一次
    timer.timeout.connect(lambda: None)  # 空操作，只是为了让Python有机会处理信号
    
    print("✅ GUI已启动，按 Ctrl+C 可退出")
    
    try:
        exit_code = app.exec_()
    except KeyboardInterrupt:
        print("\n🛑 收到KeyboardInterrupt，正在关闭...")
        window.shutdown()
        exit_code = 0
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
