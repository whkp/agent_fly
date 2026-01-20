#!/home/namy/anaconda3/envs/agent_uav/bin/python3
"""
Vision 节点 - 仅保留 YOLO 检测功能

功能:
    - YOLO 物体检测（实时）
    - 深度估计
    - 像素坐标 → 世界坐标转换
    
注意:
    - VLM 场景描述功能已移至 agent.py（统一多模态模型）
"""

# 解决 libtiff 版本冲突问题
# 必须在导入 cv2/cv_bridge 之前加载系统 libtiff
import ctypes
try:
    ctypes.CDLL("/usr/lib/x86_64-linux-gnu/libtiff.so.5", mode=ctypes.RTLD_GLOBAL)
except OSError:
    pass

import numpy as np
import cv2
import json
import os

import rospy
from geometry_msgs.msg import PointStamped
from std_msgs.msg import String
from sensor_msgs.msg import Image, CameraInfo
from nav_msgs.msg import Odometry
from tf.transformations import euler_from_quaternion

from cv_bridge import CvBridge

# 可选导入
try:
    from ultralytics import YOLOWorld
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    rospy.logwarn("YOLOWorld未安装，YOLO检测功能将不可用")

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    rospy.logwarn("PyTorch未安装，GPU加速将不可用")

device_info = {
    "px4_uav": {
        "device": "px4_uav",
        "camera_link": "camera_link",
        "camerainfo_topic": "/camera/color/camera_info",
        "base_link": "base_link",
        "depth": "m"
    }
}

class VisionNode:
    def __init__(self):
        self.device = "px4_uav"
        rospy.init_node('vision_node', anonymous=True)
        rospy.loginfo(f"✅ Vision节点启动，设备类型: {self.device}")

        # 参数配置
        use_yolo = rospy.get_param('~use_yolo', True)  # 默认启用YOLO
        model_path = rospy.get_param('~yolo_model_path', 
                                     os.path.join(os.path.dirname(__file__), 'pth/yolov8l-worldv2.pt'))
        
        # 检测类别配置
        self.detection_classes = rospy.get_param('~detection_classes', [
            "person", "vase", "bus", "bookshelf", "desk", "chair",
            "car", "ladder", "lamp", "door", "tv", "dining table", "bottle"
        ])
        
        # 初始化YOLO模型
        self.model = None
        self.result_boxes = []
        
        if use_yolo:
            if not YOLO_AVAILABLE:
                rospy.logwarn("⚠️ YOLOWorld未安装，YOLO检测功能将不可用")
            elif not os.path.exists(model_path):
                rospy.logwarn(f"⚠️ YOLO模型文件不存在: {model_path}")
            else:
                try:
                    # 确定设备
                    if TORCH_AVAILABLE and torch.cuda.is_available():
                        device = 'cuda:0'
                        rospy.loginfo("🚀 使用GPU加速")
                    else:
                        device = 'cpu'
                        rospy.loginfo("💻 使用CPU运行")
                    
                    # 加载模型
                    rospy.loginfo(f"📦 正在加载YOLO模型: {model_path}")
                    self.model = YOLOWorld(model_path).to(device)
                    
                    # 设置检测类别
                    self.model.set_classes(self.detection_classes)
                    
                    rospy.loginfo(f"✅ YOLO模型加载成功 (设备: {device})")
                    rospy.loginfo(f"🎯 检测类别: {', '.join(self.detection_classes[:5])}... (共{len(self.detection_classes)}类)")
                    
                except Exception as e:
                    rospy.logerr(f"❌ YOLO模型加载失败: {e}")
                    import traceback
                    rospy.logerr(traceback.format_exc())
        else:
            rospy.loginfo("ℹ️ YOLO检测已禁用")
        
        # 状态变量
        self.horizon_image = None
        self.horizon_depth = None
        self.drone_position = None
        self.drone_orientation = None
        
        # 参数配置 - 里程计话题
        self.odom_topic = rospy.get_param('~odom_topic', '/CERLAB/quadcopter/odom')
        
        # ROS订阅
        rospy.Subscriber("/camera/color/image_raw", Image, self.horizon_image_callback)
        rospy.Subscriber("/camera/depth/image_raw", Image, self.horizon_depth_callback)
        rospy.Subscriber(self.odom_topic, Odometry, self.odom_callback)
        rospy.Subscriber("/agent_node/vision_command", String, self.command_callback)

        # ROS发布
        self.env_desc_pub = rospy.Publisher('/vision_node/env_description', String, queue_size=10)
        
        rospy.loginfo("=" * 50)
        rospy.loginfo("Vision节点配置:")
        rospy.loginfo(f"  设备类型: {self.device}")
        rospy.loginfo(f"  里程计话题: {self.odom_topic}")
        rospy.loginfo(f"  YOLO检测: {'启用' if self.model else '禁用'}")
        rospy.loginfo(f"  VLM描述: 已移至agent.py（统一多模态模型）")
        rospy.loginfo("=" * 50)



    def horizon_image_callback(self, msg):
        """水平视角RGB图像"""
        try:
            self.horizon_image = CvBridge().imgmsg_to_cv2(msg, "bgr8")
            
            # 如果启用了YOLO检测
            if self.model is not None:
                self._run_yolo_detection()
        except Exception as e:
            rospy.logwarn_throttle(5.0, f"RGB图像处理失败: {e}")
    
    def _run_yolo_detection(self):
        """运行YOLO检测（不显示可视化窗口）"""
        try:
            results = self.model.predict(self.horizon_image, verbose=False)
            
            for i, result in enumerate(results):
                self.result_boxes = result.boxes
                # 注释掉可视化部分，避免弹出检测框
                # annotated_frame = result.plot()
                # 
                # # 添加深度信息
                # for box in self.result_boxes:
                #     x1, y1, x2, y2 = map(int, box.xyxy[0])
                #     depth_value = self.get_depth_value(x1, y1, x2, y2)
                #     cv2.putText(annotated_frame, f"{depth_value:.2f}m", 
                #               (x1, y1 - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                # 
                # cv2.imshow("YOLO Detection", annotated_frame)
                # cv2.waitKey(1)
        except Exception as e:
            rospy.logwarn_throttle(5.0, f"YOLO检测失败: {e}")



    def horizon_depth_callback(self, msg):
        """水平视角深度图像"""
        try:
            self.horizon_depth = CvBridge().imgmsg_to_cv2(msg, "passthrough")
        except Exception as e:
            rospy.logwarn_throttle(5.0, f"深度图像处理失败: {e}")

    def odom_callback(self, msg):
        """接收无人机位姿"""
        self.drone_position = msg.pose.pose.position
        self.drone_orientation = msg.pose.pose.orientation
        
        # 首次接收到位姿信息时打印日志
        if not hasattr(self, '_odom_received'):
            self._odom_received = True
            rospy.loginfo(f"✅ 已接收到里程计数据: 位置({msg.pose.pose.position.x:.2f}, {msg.pose.pose.position.y:.2f}, {msg.pose.pose.position.z:.2f})")

    def command_callback(self, msg):
        """agent节点发来的命令"""
        try:
            command = msg.data
            
            # 检查是否是 JSON 格式命令
            if command.startswith('{'):
                try:
                    cmd_data = json.loads(command)
                    cmd_type = cmd_data.get('type')
                    
                    if cmd_type == 'scene_description':
                        # VLM 场景描述请求，由 agent.py 处理，这里忽略
                        rospy.logdebug(f"收到 VLM 请求，由 agent.py 处理")
                        return
                    else:
                        rospy.logwarn(f"未知命令类型: {cmd_type}")
                        return
                except json.JSONDecodeError:
                    pass  # 不是 JSON，继续按普通命令处理
            
            # 普通命令处理
            command_lower = command.lower()
            if command_lower == "get_objects":
                # 获取检测到的物体及其世界坐标
                self.get_world_coordinates()
            else:
                rospy.logwarn(f"未知命令: {command}")
        except Exception as e:
            rospy.logerr(f"命令处理失败: {e}")

    def get_world_coordinates(self):
        """将检测到的目标转换为世界坐标并发布"""
        if not self.result_boxes or self.model is None:
            payload = {"status": "no_objects_detected", "message": "未检测到物体"}
            msg = String()
            msg.data = json.dumps(payload, ensure_ascii=False)
            self.env_desc_pub.publish(msg)
            return
        
        results = []
        
        try:
            for box in self.result_boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                depth_value = self.get_depth_value(x1, y1, x2, y2)
                
                # 跳过无效深度
                if np.isnan(depth_value) or depth_value <= 0:
                    continue
                
                # 转换为世界坐标
                center_u = (x1 + x2) // 2
                center_v = (y1 + y2) // 2
                coordinates = self.get_coordinates(center_u, center_v, depth_value)
                
                if coordinates:
                    obj_name = self.model.names[int(box.cls)]
                    confidence = float(box.conf)
                    
                    results.append({
                        "name": obj_name,
                        "confidence": round(confidence, 3),
                        "world_coordinates": {
                            "x": round(coordinates[0], 2),
                            "y": round(coordinates[1], 2),
                            "z": round(coordinates[2], 2)
                        },
                        "depth": round(float(depth_value), 2)
                    })
            
            # 构建消息
            if not results:
                payload = {"status": "no_valid_objects", "message": "检测到物体但无有效深度"}
            else:
                payload = {"status": "ok", "count": len(results), "objects": results}
            
            msg = String()
            msg.data = json.dumps(payload, ensure_ascii=False)
            self.env_desc_pub.publish(msg)
            
            rospy.loginfo(f"📡 发布环境信息: 检测到 {len(results)} 个物体")
            
        except Exception as e:
            rospy.logerr(f"世界坐标转换失败: {e}")

    def get_depth_value(self, x1, y1, x2, y2):
        """获取检测框中心像素的深度值"""
        if self.horizon_depth is None:
            return float('nan')
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        depth_value = self.horizon_depth[center_y, center_x]
        depth_value = depth_value / 1000.0 if device_info[self.device]["depth"] == "mm" else depth_value

        # --- 中心值有效（0 < depth < 100m） ---
        if not np.isnan(depth_value) and 0 < depth_value < 100.0:
            return depth_value
        
        # --- 否则在框区域内取最小有效值 ---
        roi = self.horizon_depth[y1:y2, x1:x2]
        roi_valid = roi[(roi > 0) & (roi < 100.0) & (~np.isnan(roi))]

        if roi_valid.size > 0:
            min_depth = np.min(roi_valid)
            return min_depth / 1000.0 if device_info[self.device]["depth"] == "mm" else min_depth

        # --- 整个区域都无效 ---
        return float('nan')
    
    def get_coordinates(self, u, v, depth):
        """将像素坐标和深度值转为世界坐标（直接计算，绕过TF）"""
        try:
            # 获取相机内参
            camera_info = rospy.wait_for_message(
                device_info[self.device]["camerainfo_topic"], 
                CameraInfo, 
                timeout=5.0
            )
            camera_fx = camera_info.K[0]  # 焦距 fx
            camera_fy = camera_info.K[4]  # 焦距 fy
            camera_cx = camera_info.K[2]  # 光心 cx
            camera_cy = camera_info.K[5]  # 光心 cy
            
            # 检查无人机位姿是否可用
            if self.drone_position is None or self.drone_orientation is None:
                rospy.logerr(f"无人机位姿信息未获取到！当前订阅话题: {self.odom_topic}")
                rospy.logerr(f"请检查: 1) 话题是否存在 (rostopic list | grep odom)")
                rospy.logerr(f"        2) 话题是否有数据 (rostopic echo {self.odom_topic} -n 1)")
                return None
            
            # 1. 像素坐标 → 相机坐标系
            # 相机坐标系：X-前方（深度）, Y-左方, Z-上方
            camera_x = depth
            camera_y = -(u - camera_cx) * depth / camera_fx
            camera_z = -(v - camera_cy) * depth / camera_fy
            
            rospy.logdebug(f"相机坐标: x={camera_x:.2f}, y={camera_y:.2f}, z={camera_z:.2f}")
            
            # 2. 相机坐标 → base_link 坐标
            # 假设相机安装在无人机中心，朝向与无人机一致（无俯仰角）
            # base_link 坐标系：X-前方, Y-左方, Z-上方
            base_x = camera_x
            base_y = camera_y
            base_z = camera_z
            
            # 3. base_link 坐标 → 世界坐标（map）
            # 获取无人机的 yaw 角（偏航角）
            qx = self.drone_orientation.x
            qy = self.drone_orientation.y
            qz = self.drone_orientation.z
            qw = self.drone_orientation.w
            roll, pitch, yaw = euler_from_quaternion([qx, qy, qz, qw])
            
            # 应用旋转（只考虑 yaw，假设无人机水平飞行）
            cos_yaw = np.cos(yaw)
            sin_yaw = np.sin(yaw)
            
            # 旋转矩阵应用
            rotated_x = base_x * cos_yaw - base_y * sin_yaw
            rotated_y = base_x * sin_yaw + base_y * cos_yaw
            rotated_z = base_z
            
            # 加上无人机的世界坐标
            world_x = rotated_x + self.drone_position.x
            world_y = rotated_y + self.drone_position.y
            world_z = rotated_z + self.drone_position.z
            
            rospy.logdebug(f"世界坐标: x={world_x:.2f}, y={world_y:.2f}, z={world_z:.2f}")
            
            return (world_x, world_y, world_z)
            
        except Exception as e:
            rospy.logerr(f"坐标转换失败: {e}")
            import traceback
            rospy.logerr(traceback.format_exc())
            return None


if __name__ == '__main__':
    try:
        node = VisionNode()
        rospy.spin()   # 保持节点运行
    except rospy.ROSInterruptException:
        pass