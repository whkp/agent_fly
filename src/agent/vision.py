#!/home/namy/anaconda3/envs/agent_uav/bin/python3

# 解决 libtiff 版本冲突问题
# 必须在导入 cv2/cv_bridge 之前加载系统 libtiff
import ctypes
try:
    ctypes.CDLL("/usr/lib/x86_64-linux-gnu/libtiff.so.5", mode=ctypes.RTLD_GLOBAL)
except OSError:
    pass

import numpy as np
import base64
import cv2
import json
import os

import rospy
import tf
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
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    rospy.logwarn("OpenAI未安装，VLM功能将不可用")

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
        self.use_vlm = rospy.get_param('~use_vlm', True)
        
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
        
        # ROS订阅 - PX4仿真器话题
        rospy.Subscriber("/camera/color/image_raw", Image, self.horizon_image_callback)
        rospy.Subscriber("/camera/depth/image_raw", Image, self.horizon_depth_callback)
        rospy.Subscriber("/mavros/local_position/odom", Odometry, self.odom_callback)
        rospy.Subscriber("/agent_node/vision_command", String, self.command_callback)

        # ROS发布
        self.env_desc_pub = rospy.Publisher('/vision_node/env_description', String, queue_size=10)
        
        rospy.loginfo("=" * 50)
        rospy.loginfo("Vision节点配置:")
        rospy.loginfo(f"  设备类型: {self.device}")
        rospy.loginfo(f"  YOLO检测: {'启用' if self.model else '禁用'}")
        rospy.loginfo(f"  VLM描述: {'启用' if self.use_vlm else '禁用'}")
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
        """运行YOLO检测并可视化"""
        try:
            results = self.model.predict(self.horizon_image, verbose=False)
            
            for i, result in enumerate(results):
                self.result_boxes = result.boxes
                annotated_frame = result.plot()

                # 添加深度信息
                for box in self.result_boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    depth_value = self.get_depth_value(x1, y1, x2, y2)
                    cv2.putText(annotated_frame, f"{depth_value:.2f}m", 
                              (x1, y1 - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

            cv2.imshow("YOLO Detection", annotated_frame)
            cv2.waitKey(1)
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

    def command_callback(self, msg):
        """agent节点发来的命令"""
        try:
            command = msg.data.lower()
            
            if command == "get_objects":
                # 获取检测到的物体及其世界坐标
                self.get_world_coordinates()
            elif command == "describe_scene":
                # 使用VLM描述场景
                if self.use_vlm:
                    self.vlm_describe_scene()
                else:
                    rospy.logwarn("VLM未启用")
            else:
                rospy.logwarn(f"未知命令: {command}")
        except Exception as e:
            rospy.logerr(f"命令处理失败: {e}")

    def vlm_describe_scene(self):
        """使用VLM模型对图像进行描述"""
        if not OPENAI_AVAILABLE:
            rospy.logwarn("OpenAI库未安装，无法使用VLM功能")
            self.env_desc_pub.publish("错误：OpenAI库未安装")
            return
        
        if self.horizon_image is None:
            rospy.logwarn("没有可用的图像")
            self.env_desc_pub.publish("错误：没有可用的图像")
            return
        
        try:
            # 保存临时图像
            temp_path = "/tmp/vision_temp.jpg"
            cv2.imwrite(temp_path, self.horizon_image)
            
            with open(temp_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode("utf-8")
            
            # 从参数服务器或环境变量获取API配置
            api_key = rospy.get_param('~vlm_api_key', os.environ.get('OPENAI_API_KEY', ''))
            api_base = rospy.get_param('~vlm_api_base', os.environ.get('OPENAI_API_BASE', 'https://dashscope.aliyuncs.com/compatible-mode/v1'))
            model_name = rospy.get_param('~vlm_model', 'qwen-vl-plus')
            
            if not api_key:
                rospy.logwarn("未配置VLM API密钥，请设置 ~vlm_api_key 参数或 OPENAI_API_KEY 环境变量")
                self.env_desc_pub.publish("错误：未配置API密钥")
                return
            
            rospy.loginfo(f"🔍 正在使用 {model_name} 分析场景...")
            
            client = OpenAI(api_key=api_key, base_url=api_base)
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                        {"type": "text", "text": "请简洁描述当前环境中的物体、障碍物和可通行区域，字数少于100字"}
                    ]
                }],
                max_tokens=300
            )
            
            description = completion.choices[0].message.content
            self.env_desc_pub.publish(description)
            rospy.loginfo(f"📝 场景描述: {description}")
            
        except Exception as e:
            rospy.logerr(f"VLM描述失败: {e}")
            import traceback
            rospy.logerr(traceback.format_exc())
            self.env_desc_pub.publish(f"错误：{str(e)}")

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
        """将像素坐标和深度值转为世界坐标"""
        camera_link = device_info[self.device]["camera_link"]
        base_link = device_info[self.device]["base_link"]
        camera_info = rospy.wait_for_message(device_info[self.device]["camerainfo_topic"], CameraInfo, timeout=5.0)
        camera_fx = camera_info.K[0]       # 焦距 fx
        camera_fy = camera_info.K[4]       # 焦距 fy
        camera_cx = camera_info.K[2]       # 光心 cx
        camera_cy = camera_info.K[5]
        # 1. 像素坐标和深度值 -> 相机坐标
        camera_point = PointStamped()
        camera_point.header.frame_id = camera_link
        camera_point.point.y = - (u - camera_cx) * depth / camera_fx
        camera_point.point.z = - (v - camera_cy) * depth / camera_fy
        camera_point.point.x = float(depth)
        try:
            # 2. 相机坐标 -> 机器人（无人机）坐标
            listener = tf.TransformListener()
            listener.waitForTransform(base_link, camera_link, rospy.Time(0), rospy.Duration(1.0))
            camera_point_in_base_link = listener.transformPoint(base_link, camera_point)

            # 3. 机器人（无人机）坐标 -> 世界坐标
            if self.drone_position is None or self.drone_orientation is None:
                rospy.logerr("无人机位姿信息未获取到！")
                return None
            
            # 将四元数转为欧拉角（yaw, pitch, roll）
            qx, qy, qz, qw = self.drone_orientation.x, self.drone_orientation.y, self.drone_orientation.z, self.drone_orientation.w
            roll, pitch, yaw = euler_from_quaternion([qx, qy, qz, qw])

            # 无人机在地图坐标系中的位置
            drone_position_map = [self.drone_position.x, self.drone_position.y, self.drone_position.z]

            # 旋转矩阵（从 base_link 转换到 map）
            rotation_matrix = self._get_rotation_matrix(yaw)

            # 将相机点从 base_link 转换到 map 坐标系
            camera_coords_in_base_link = [camera_point_in_base_link.point.x, camera_point_in_base_link.point.y, camera_point_in_base_link.point.z]
            camera_coords_in_map = self._apply_rotation_and_translation(camera_coords_in_base_link, rotation_matrix, drone_position_map)

            return tuple(round(x, 3) for x in camera_coords_in_map)

        except (tf.Exception) as e:
            rospy.logerr(f"Transform failed: {e}")
            return None
    
    def _get_rotation_matrix(self, yaw):
        """根据yaw角计算旋转矩阵"""
        rotation_matrix = [
            [np.cos(yaw), -np.sin(yaw), 0],
            [np.sin(yaw), np.cos(yaw), 0],
            [0, 0, 1]
        ]
        return rotation_matrix

    def _apply_rotation_and_translation(self, camera_coords, rotation_matrix, translation_vector):
        """应用旋转和位移将相机坐标系转换到地图坐标系"""
        rotated_coords = np.dot(rotation_matrix, camera_coords)
        transformed_coords = rotated_coords + np.array(translation_vector)
        return transformed_coords
    

if __name__ == '__main__':
    try:
        node = VisionNode()
        rospy.spin()   # 保持节点运行
    except rospy.ROSInterruptException:
        pass