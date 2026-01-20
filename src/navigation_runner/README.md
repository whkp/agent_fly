# Navigation Runner - PPO 强化学习导航系统

基于 PPO (Proximal Policy Optimization) 的端到端无人机导航系统，集成到 AgentFly 项目中。

## 系统概述

Navigation Runner 是 AgentFly 的核心导航模块，提供：

1. **PPO 导航策略**：端到端速度级控制，输入激光雷达数据，输出 3D 速度向量
2. **感知模块**：
   - 深度相机实时占用地图构建（map_manager）
   - 动态障碍物检测（onboard_detector）
   - 激光雷达模拟（通过地图 Raycasting，144 点）
3. **安全防护**：可选的安全防护层（Safety Shield）

## 与 AgentFly 集成

在 AgentFly 系统中，navigation_runner 负责：
- 接收 Agent 发布的导航目标（`/move_base_simple/goal`）
- 使用 PPO 策略进行避障导航
- 发布速度控制指令到仿真器（`/CERLAB/quadcopter/cmd_vel`）

## 系统架构

```
┌─────────────────────────────────────────────────┐
│           Navigation Runner 系统                │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────┐       ┌──────────────┐      │
│  │ 占用地图构建  │ ◄───► │ 激光雷达模拟  │      │
│  │ (深度相机)    │       │ (Raycasting) │      │
│  └──────────────┘       └──────────────┘      │
│         │                       │              │
│         │                       │              │
│         ▼                       ▼              │
│  ┌──────────────────────────────────────┐     │
│  │      PPO 导航策略网络                 │     │
│  │  输入: 激光雷达 + 动态障碍物 + 方向   │     │
│  │  输出: 3D 速度命令 (vx, vy, vz)      │     │
│  └──────────────────────────────────────┘     │
│         │                       │              │
│         ▼                       ▼              │
│  ┌──────────────┐       ┌──────────────┐     │
│  │ 安全防护层    │       │ 速度控制      │     │
│  │ (可选)        │       │               │     │
│  └──────────────┘       └──────────────┘     │
│                                                 │
└─────────────────────────────────────────────────┘
           │                       │
           ▼                       ▼
    uav_simulator           Gazebo/RViz
```

## 快速开始

### 方法 1: 通过 AgentFly 启动（推荐）

```bash
# 1. 清理环境变量
unset ROS_PACKAGE_PATH
unset PYTHONPATH

# 2. Source 工作空间
source ~/catkin_ws/devel/setup.bash

# 3. 激活 agent_uav 环境
conda activate agent_uav

# 4. 启动完整系统（包含 navigation_runner）
roslaunch agent flight.launch
```

navigation_runner 会通过 wrapper 脚本自动在 NavRL 环境中启动。

### 方法 2: 单独测试导航模块

```bash
# 终端 1: 启动仿真器
roslaunch uav_simulator start.launch

# 终端 2: 启动感知和地图
roslaunch navigation_runner safety_and_perception_sim.launch \
    use_px4:=false \
    use_prebuilt_map:=false \
    use_real_detector:=false \
    use_safety_shield:=false \
    rviz:=true

# 终端 3: 启动导航节点（需要 NavRL 环境）
conda activate NavRL
rosrun navigation_runner navigation_node_wrapper.sh

# 终端 4: 在 RViz 中使用 "2D Nav Goal" 设置目标点
```

## 配置说明

### 主配置文件

**scripts/cfg/train.yaml**
```yaml
device: "cuda:0"              # 计算设备 (cuda:0 或 cpu)
headless: False               # 是否无头模式

sensor:
  lidar_range: 4.0            # 激光雷达最大范围 (米)
  lidar_vfov: [-10, 20]       # 垂直视场角 (度)
  lidar_vbeams: 4             # 垂直光束数量
  lidar_hres: 10.0            # 水平角度分辨率 (度)
```

### 传感器配置

**激光雷达参数** (cfg/drone.yaml):
- `lidar_range: 4.0` - 探测范围 4 米
- `lidar_vfov: [-10, 20]` - 垂直 30° 视场
- `lidar_vbeams: 4` - 4 条垂直扫描线
- `lidar_hres: 10.0` - 水平每 10° 一个点（共 36 个水平方向）

总激光点数: 36 (水平) × 4 (垂直) = 144 个点

**深度相机配置** (cfg/mapping/sim/no_map.yaml):
```yaml
depth_image_topic: /camera/depth/image_raw
depth_intrinsics: [554.254691191187, 554.254691191187, 320.5, 240.5]
depth_min_value: 0.5          # 最小有效深度 (米)
depth_max_value: 5.0          # 最大有效深度 (米)
image_cols: 640
image_rows: 480
```

**地图参数**:
```yaml
map_resolution: 0.1           # 地图栅格大小 (米)
map_size: [60, 60, 5]         # 地图尺寸 (米)
local_update_range: [5, 5, 5] # 局部更新范围 (米)
raycast_max_length: 5.0       # Raycast 最大距离 (米)
```

### 障碍物检测配置

**cfg/detection/sim/fake_detector.yaml**:
```yaml
odom_topic: "/CERLAB/quadcopter/odom"
target_obstacle: ["person", "dynamic_box", "dynamic_cylinder"]
color_distance: 5.0           # 检测范围 (米)
history_size: 100             # 障碍物历史记录大小
```

## 话题接口

### 输入话题

| 话题 | 类型 | 描述 |
|------|------|------|
| `/move_base_simple/goal` | PoseStamped | 导航目标点（来自 Agent） |
| `/CERLAB/quadcopter/odom` | Odometry | 无人机里程计 |
| `/camera/depth/image_raw` | Image | 深度图像（用于建图） |

### 输出话题

| 话题 | 类型 | 描述 |
|------|------|------|
| `/CERLAB/quadcopter/cmd_vel` | TwistStamped | 速度控制指令（PPO 输出） |
| `/CERLAB/quadcopter/setpoint_pose` | PoseStamped | 位置控制指令（起飞/降落） |
| `/rl_navigation/raycast` | PointCloud2 | 激光雷达模拟点云 |
| `/rl_navigation/goal` | Marker | 当前目标点可视化 |

### 模式切换

通过 ROS 参数 `rl/use_px4` 切换控制模式：
- `use_px4:=false` - uav_simulator 模式（默认）
- `use_px4:=true` - PX4 真机模式

## 工作流程

### 1. 初始化
- 加载 PPO 模型权重：`ckpts/navrl_checkpoint.pt`
- 初始化地图服务（Raycast）
- 订阅里程计和深度图像

### 2. 自动起飞
- 启动时自动起飞到 1.5m 高度（可配置）
- 使用位置控制模式（`/CERLAB/quadcopter/setpoint_pose`）

### 3. 等待目标
- 监听 `/move_base_simple/goal` 话题
- Agent 通过 `set_goal` 工具发布目标点

### 4. PPO 导航循环
```
获取当前状态 (odom)
    ↓
激光雷达模拟 (Raycast 144 点)
    ↓
获取动态障碍物信息
    ↓
PPO 策略推理 → 输出 3D 速度 [vx, vy, vz]
    ↓
发布速度指令 (/CERLAB/quadcopter/cmd_vel)
    ↓
检查是否到达目标 (距离 < 0.5m)
```

### 5. 到达目标
- 距离小于阈值时停止
- 切换到悬停模式

## PPO 策略详情

### 输入
- **激光雷达**：144 点（36 水平 × 4 垂直）
- **动态障碍物**：位置、速度、大小
- **目标方向**：相对目标的方向向量

### 输出
- **3D 速度向量**：`[vx, vy, vz]`（机体坐标系）
- **速度范围**：[-2.0, 2.0] m/s
- **控制频率**：10-20 Hz

## 可视化

### RViz 话题

启动 RViz 后可以看到：

```yaml
可视化话题:
  - /rl_navigation/raycast                    # 激光雷达扫描点云
  - /rl_navigation/goal                       # 当前目标点（绿色圆柱）
  - /rl_navigation/cmd                        # 速度命令箭头
  - /rollout_traj                             # 预测轨迹
  - /occupancy_map/global_map                 # 全局占用地图
  - /occupancy_map/local_map                  # 局部占用地图
  - /rl_navigation/in_range_dynamic_obstacles # 检测到的动态障碍物
```

### 使用 RViz 设置目标

1. 在 RViz 中点击 "2D Nav Goal" 工具
2. 在地图上点击目标位置
3. 系统会自动接收目标并开始导航

## 性能调优

### GPU 优化

如果 GPU 内存不足：
```yaml
# 在 train.yaml 中
device: "cpu"  # 使用 CPU（较慢）
```

如果有多个 GPU：
```yaml
device: "cuda:1"  # 使用第二个 GPU
```

### 激光雷达密度

提高精度但降低速度：
```yaml
# cfg/drone.yaml
sensor:
  lidar_hres: 5.0      # 从 10° 减小到 5°（点数翻倍）
  lidar_vbeams: 8      # 从 4 增加到 8
```

### 地图更新频率

减小局部更新范围以提高速度：
```yaml
# cfg/mapping/sim/no_map.yaml
local_update_range: [3, 3, 3]  # 从 [5,5,5] 减小
```

## 调试技巧

### 查看话题频率

```bash
# 检查控制命令发布频率
rostopic hz /CERLAB/quadcopter/cmd_vel

# 检查激光雷达更新频率
rostopic hz /rl_navigation/raycast

# 检查地图更新频率
rostopic hz /occupancy_map/local_map
```

### 监控策略输出

```bash
# 查看速度命令
rostopic echo /CERLAB/quadcopter/cmd_vel

# 查看当前目标
rostopic echo /move_base_simple/goal
```

### 性能监控

```bash
# GPU 使用情况
nvidia-smi -l 1

# CPU 和内存
htop

# ROS 节点性能
rosrun rqt_top rqt_top
```

## 常见问题

### Q1: ImportError: cannot import name 'PositionTarget'

**原因**：工作空间冲突，系统从错误的路径导入 mavros_msgs

**解决方法**：
```bash
# 清理环境变量
unset ROS_PACKAGE_PATH
unset PYTHONPATH

# 重新 source 工作空间
source ~/catkin_ws/devel/setup.bash
```

### Q2: 无人机不移动

**检查清单**：
```bash
# 1. 检查导航节点是否运行
rosnode list | grep navigation

# 2. 检查是否收到目标点
rostopic echo /move_base_simple/goal

# 3. 检查速度指令
rostopic echo /CERLAB/quadcopter/cmd_vel

# 4. 检查 PPO 模型
ls src/navigation_runner/ckpts/navrl_checkpoint.pt
```

### Q3: 地图为空

**检查清单**：
```bash
# 1. 检查深度图像
rostopic hz /camera/depth/image_raw

# 2. 检查地图节点
rosnode list | grep occupancy_map

# 3. 查看地图话题
rostopic echo /occupancy_map/local_map
```

### Q4: Conda 环境问题

**现象**：`conda: command not found` 或环境切换失败

**解决方法**：
```bash
# 初始化 conda
eval "$(conda shell.bash hook)"

# 或者在 ~/.bashrc 中添加
echo 'eval "$(conda shell.bash hook)"' >> ~/.bashrc
```

### Q5: GPU 内存不足

**解决方法**：
```yaml
# 修改 scripts/cfg/train.yaml
device: "cpu"  # 改为 CPU 模式
```

## 环境要求

### Conda 环境

navigation_runner 需要在 **NavRL** 环境中运行：

```bash
# 创建环境
conda create -n NavRL python=3.8
conda activate NavRL

# 安装依赖
pip install torch torchvision
pip install tensordict torchrl
pip install numpy opencv-python
```

### ROS 依赖

```bash
sudo apt install ros-noetic-octomap*
sudo apt install ros-noetic-vision-msgs
```

## 性能指标

- **导航成功率**：90%+（仿真环境）
- **平均速度**：1.5-2.0 m/s
- **避障距离**：0.5m 安全距离
- **激光雷达**：144 点，4m 范围
- **地图分辨率**：0.1m
- **控制频率**：10-20 Hz

## 相关模块

- [agent](../agent/README.md) - LLM Agent 和视觉感知
- [map_manager](../map_manager/README.md) - 3D 占据地图构建
- [onboard_detector](../onboard_detector/README.md) - 动态障碍物检测
- [uav_simulator](https://github.com/Zhefan-Xu/uav_simulator) - 轻量级仿真器

## 技术支持

如有问题，请查看：
1. [主项目 README](../../README.md)
2. [故障排除指南](../../README.md#故障排除)
3. GitHub Issues
