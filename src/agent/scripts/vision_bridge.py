#!/usr/bin/env python3
"""
Vision Bridge - 将 Gazebo 真值转换为视觉里程计

模拟真机 VIO 输入:
- 发布 /mavros/vision_pose/pose 和 /mavros/vision_speed/speed (给 PX4 EKF2)
- 发布 /ekf2/odom 融合里程计 (给 so3_control)
"""

import rospy
from geometry_msgs.msg import PoseStamped, Vector3Stamped
from nav_msgs.msg import Odometry
from gazebo_msgs.msg import ModelStates


class VisionBridge:
    def __init__(self):
        rospy.init_node('vision_bridge')
        
        self.model_name = rospy.get_param('~model_name', 'iris')
        
        # 发布者 - MAVROS vision 输入 (给 PX4 EKF2)
        self.vision_pose_pub = rospy.Publisher(
            '/mavros/vision_pose/pose', PoseStamped, queue_size=1)
        self.vision_speed_pub = rospy.Publisher(
            '/mavros/vision_speed/speed', Vector3Stamped, queue_size=1)
        
        # 发布者 - 融合里程计 (给 so3_control)
        self.odom_pub = rospy.Publisher('/ekf2/odom', Odometry, queue_size=1)
        
        # 订阅 Gazebo 真值
        rospy.Subscriber('/gazebo/model_states', ModelStates, 
                        self._on_model_states, queue_size=1)
        
        self._last_pub_time = rospy.Time.now()
        
        rospy.loginfo(f"VisionBridge 启动，模型: {self.model_name}")
        rospy.loginfo("发布: /mavros/vision_pose/pose, /mavros/vision_speed/speed, /ekf2/odom")
        rospy.spin()
    
    def _on_model_states(self, msg):
        now = rospy.Time.now()
        # 限制发布频率 ~100Hz
        if (now - self._last_pub_time).to_sec() < 0.01:
            return
        self._last_pub_time = now
        
        try:
            # 查找模型
            idx = -1
            for name in [self.model_name, f'{self.model_name}_0', 'iris', 'iris_0']:
                if name in msg.name:
                    idx = msg.name.index(name)
                    break
            
            if idx == -1:
                return
            
            pose = msg.pose[idx]
            twist = msg.twist[idx]
            
            # 发布 vision_pose (给 PX4 EKF2)
            ps = PoseStamped()
            ps.header.stamp = now
            ps.header.frame_id = 'world'
            ps.pose = pose
            self.vision_pose_pub.publish(ps)
            
            # 发布 vision_speed (给 PX4 EKF2)
            vs = Vector3Stamped()
            vs.header.stamp = now
            vs.header.frame_id = 'world'
            vs.vector = twist.linear
            self.vision_speed_pub.publish(vs)
            
            # 发布融合里程计 /ekf2/odom (给 so3_control)
            odom = Odometry()
            odom.header.stamp = now
            odom.header.frame_id = 'world'
            odom.child_frame_id = 'base_link'
            odom.pose.pose = pose
            odom.twist.twist = twist
            self.odom_pub.publish(odom)
            
        except Exception as e:
            rospy.logwarn_throttle(5.0, f"VisionBridge 错误: {e}")


if __name__ == '__main__':
    try:
        VisionBridge()
    except rospy.ROSInterruptException:
        pass
