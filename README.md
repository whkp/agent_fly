# UAV Agent

基于多模态大语言模型的智能无人机控制系统，集成视觉感知、强化学习导航和自然语言交互。

**最新版本**：v2.5 (2025-01-20)
- ✅ 完成混合部署方案实施（LLM在无人机，YOLO在地面站）
- ✅ 创建真机部署launch文件
- ✅ 完整部署指南文档

详见 [CHANGELOG.md](CHANGELOG.md)

---

## 快速开始

### 仿真模式（开发/测试）

#### 1. 环境准备
```bash
# 清理环境变量（如果有多个ROS工作空间）
cd ~/agent_ws
unset ROS_PACKAGE_PATH
unset PYTHONPATH
unset CMAKE_PREFIX_PATH
source devel/setup.bash

# 激活Agent环境
conda activate agent_uav

# 设置API Key
export DASHSCOPE_API_KEY="your-api-key"
```

#### 2. 启动系统
```bash
# 终端1: 启动仿真环境
source src/uav_simulator/gazeboSetup.bash
roslaunch uav_simulator start.launch

# 终端2: 启动Agent系统（导航 + Agent + 视觉）
conda activate agent_uav
roslaunch agent flight.launch

# 终端3: 启动GUI控制界面
conda activate agent_uav
rosrun agent agent_gui.py
```

#### 3. 输入指令
在GUI界面输入自然语言指令：
- "起飞到2米高度"
- "飞到坐标 (5, 3, 2)"
- "找到桌子并飞到它前面"
- "原地旋转搜索人"
- "降落"

---

### 真机部署

#### 方案A: 全部在无人机（边缘计算）

**适用场景**: 无网络环境，需要完全自主

**硬件需求**: 
- GPU: 12GB显存（LLM 8GB + YOLO 2GB + 导航 2GB）
- 内存: 16GB
- 推荐: Jetson AGX Orin 32GB 或 NUC + RTX 3060

**启动方式**:
```bash
# 无人机上启动全部
roslaunch agent flight.launch \
  use_real_drone:=true \
  real_drone_takeoff_script:=/path/to/takeoff.sh \
  real_drone_land_script:=/path/to/land.sh \
  odom_topic:=/mavros/local_position/odom
```

---

#### 方案B: 混合部署（推荐）⭐

**适用场景**: 有稳定WiFi/4G/5G网络，无人机算力有限

**架构**:
```
地面站                          无人机
├── vision.py (YOLO)           ├── agent.py (LLM API)
│   └── 2GB显存                │   └── 200MB内存, 5% CPU
└── 图像处理                   ├── navigation_node (RL导航)
                               │   └── 2GB显存
                               └── 传感器
```

**硬件需求**:
- 地面站: 2GB显存（YOLO）
- 无人机: 2GB显存（导航）+ 200MB内存（LLM API）


**网络配置**:
```bash
# 地面站
export ROS_MASTER_URI=http://192.168.1.100:11311  # 无人机IP
export ROS_IP=192.168.1.200                       # 地面站IP

# 无人机
export ROS_MASTER_URI=http://localhost:11311
export ROS_IP=192.168.1.100
```

**启动步骤**:

1. **地面站 - 启动YOLO检测**
```bash
# 配置网络
export ROS_MASTER_URI=http://192.168.1.100:11311
export ROS_IP=192.168.1.200

# 启动YOLO
roslaunch agent vision_station.launch
```

2. **无人机 - 启动Agent和导航**
```bash
# 配置网络
export ROS_MASTER_URI=http://localhost:11311
export ROS_IP=192.168.1.100

# 启动Agent和导航
roslaunch agent drone_with_llm.launch \
  real_drone_takeoff_script:=/path/to/takeoff.sh \
  real_drone_land_script:=/path/to/land.sh \
  odom_topic:=/mavros/local_position/odom \
  pose_topic:=/mavros/setpoint_position/local
```

3. **GUI - 任意终端启动**
```bash
# 配置网络（同地面站或无人机）
export ROS_MASTER_URI=http://192.168.1.100:11311
export ROS_IP=YOUR_IP

# 启动GUI
rosrun agent agent_gui.py
```

**验证系统**:
```bash
# 检查节点
rosnode list
# 应该看到: /agent_node, /vision_node, /navigation_node

# 测试延迟
rostopic hz /camera/color/image_raw
rostopic hz /vision_node/env_description
# 预期: 2-5 Hz (200-500ms延迟)
```

---

## 部署方案对比

| 方案 | 无人机显存 | 无人机内存 | 地面站显存 | 硬件成本 | 适用场景 |
|------|-----------|-----------|-----------|---------|---------|
| 仿真模式 | 4GB | 2GB | - | 开发机 | 开发/测试 |
| 方案A（边缘计算） | 12GB | 16GB | - | ¥6000-8000 | 无网络环境 |
| 方案B（混合部署）⭐ | 2GB | 200MB | 2GB | ¥2000 | 有网络环境 |

**推荐**: 
- 开发阶段 → 仿真模式
- 真机部署（有网络）→ 方案B（混合部署）
- 真机部署（无网络）→ 方案A（边缘计算）

---

## 详细文档

- **完整部署指南**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - 包含详细配置、故障排查、性能优化
- **项目架构**: [项目介绍.md](项目介绍.md) - 系统架构、技术细节、性能指标
- **更新日志**: [CHANGELOG.md](CHANGELOG.md) - 版本历史和功能更新

---

## 可用工具

Agent提供8个核心工具：

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `takeoff` | 起飞到指定高度 | `{'height': 1.5}` |
| `land` | 降落到地面 | 无 |
| `set_goal` | 设置导航目标点 | `{'x': 5, 'y': 3, 'z': 1.5}` |
| `rotate` | 原地旋转搜索 | `{'angle': 60}` |
| `get_detected_objects` | 获取检测到的物体 | 无 |
| `describe_scene` | VLM场景描述 | `{'query': '...'}` |
| `get_current_position` | 获取当前位置 | 无 |
| `get_flight_status` | 获取飞行状态 | 无 |

---

## 故障排除

### 1. Agent无响应
```bash
# 检查API Key
echo $DASHSCOPE_API_KEY

# 查看日志
rostopic echo /agent_node/agent_log
```

### 2. 地面站连不上无人机（混合部署）
```bash
# 检查网络
ping 192.168.1.100

# 检查环境变量
echo $ROS_MASTER_URI
echo $ROS_IP

# 检查防火墙
sudo ufw allow 11311/tcp
```

### 3. YOLO检测慢（混合部署）
```bash
# 检查网络带宽
iperf3 -c 192.168.1.100
# 建议: >10 Mbps

# 降低图像质量（修改vision_station.launch）
<param name="image_compression_quality" value="60"/>
```

### 4. 无人机不移动
```bash
# 检查导航节点
rosnode list | grep navigation

# 检查速度命令
rostopic echo /CERLAB/quadcopter/cmd_vel
```

更多故障排查请参考 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---

## 安装

```bash
# 1. 安装系统依赖
sudo apt install ros-${ROS_DISTRO}-octomap* 
sudo apt install ros-${ROS_DISTRO}-mavros* 
sudo apt install ros-${ROS_DISTRO}-vision-msgs

# 2. 克隆仓库
mkdir -p ~/agent_ws/src
cd ~/agent_ws/src
git clone <repository-url>

# 3. 编译工作空间
cd ~/agent_ws
catkin_make

# 4. 配置Python环境
conda env create -f src/agent/cfg/environment.yaml
conda activate agent_uav
```

---

## 项目结构

```
src/
├── agent/                      # LLM Agent模块
│   ├── agent.py               # 多模态Agent主程序
│   ├── agent_gui.py           # GUI控制界面
│   ├── tools.py               # 8个工具接口
│   ├── vision.py              # YOLO检测节点
│   └── launch/
│       ├── flight.launch      # 统一启动（仿真/真机自动选择）
│       ├── vision_station.launch    # 地面站YOLO
│       └── drone_with_llm.launch    # 无人机Agent+导航
│
├── navigation_runner/          # PPO导航模块
├── map_manager/                # 地图构建模块
├── onboard_detector/           # 障碍物检测模块
└── uav_simulator/              # 仿真环境
```

---

## 许可证

MIT License

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户交互层                                      │
│  ┌─────────────┐                                                            │
│  │ agent_gui.py│  ←── 用户自然语言指令 (GUI界面)                             │
│  └──────┬──────┘                                                            │
│         │ ROS Topic: /agent_node/user_command                               │
│         ▼                                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                           智能决策层                                         │
│  ┌─────────────────────────────────────────────────────────────┐            │
│  │  agent.py - 多模态LLM Agent (Qwen3-VL-Flash)                │            │
│  │  • 自然语言理解与任务规划                                    │            │
│  │  • 视觉场景理解（直接看到画面）                              │            │
│  │  • ReAct推理循环 (Thought → Action → Observation)          │            │
│  │  • 安全管理层（高度/距离/速度限制）                          │            │
│  └─────────────────────────────────────────────────────────────┘            │
│         │                                                                   │
├─────────┼───────────────────────────────────────────────────────────────────┤
│         │                        工具执行层                                  │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐            │
│  │  tools.py - 8个核心工具                                      │            │
│  │  • takeoff/land: 起飞降落控制                                │            │
│  │  • set_goal: 导航目标设置 → /move_base_simple/goal          │            │
│  │  • rotate: 原地旋转搜索                                      │            │
│  │  • get_detected_objects: YOLO物体检测                        │            │
│  │  • describe_scene: VLM场景描述                               │            │
│  │  • get_current_position/get_flight_status: 状态查询          │            │
│  └─────────────────────────────────────────────────────────────┘            │
│         │                           │                                       │
│         │ /CERLAB/quadcopter/       │ /move_base_simple/goal                │
│         │ setpoint_pose             │                                       │
├─────────┼───────────────────────────┼───────────────────────────────────────┤
│         │      视觉感知层            │        导航规划层                      │
│         │                           │                                       │
│  ┌──────▼──────┐            ┌───────▼────────┐                             │
│  │ vision.py   │            │ navigation_node│                             │
│  │ • YOLOWorld │            │ (PPO强化学习)  │                             │
│  │ • 深度融合  │            │ • 激光雷达模拟 │                             │
│  │ • 坐标转换  │            │ • 速度控制     │                             │
│  └─────────────┘            │ • 动态避障     │                             │
│         │                   └────────┬───────┘                             │
│         │                            │ /CERLAB/quadcopter/cmd_vel           │
├─────────┼────────────────────────────┼─────────────────────────────────────┤
│         │      地图构建层            │                                       │
│         │                            │                                       │
│  ┌──────▼────────────────────────────▼───────┐                             │
│  │  map_manager (occupancy_map_node)         │                             │
│  │  • 3D占据栅格地图 (Octomap)                │                             │
│  │  • 深度相机实时建图                        │                             │
│  │  • Raycast激光雷达模拟                     │                             │
│  └────────────────────────────────────────────┘                             │
│         │                            │                                       │
├─────────┼────────────────────────────┼─────────────────────────────────────┤
│         │                    仿真器层│                                       │
│         ▼                            ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                    uav_simulator (轻量级仿真器)                  │        │
│  │  • /CERLAB/quadcopter/odom         (里程计输出)                  │        │
│  │  • /CERLAB/quadcopter/cmd_vel      (速度控制输入)                │        │
│  │  • /CERLAB/quadcopter/setpoint_pose (位置控制输入)              │        │
│  │  • /camera/depth/image_raw         (深度图像 640×480)           │        │
│  │  • /camera/color/image_raw         (彩色图像 640×480)           │        │
│  └─────────────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Python 依赖

**Agent 环境** (agent_uav)：
```bash
conda env create -f src/agent/cfg/environment.yaml
conda activate agent_uav
```

核心依赖：
- `langchain` - LLM 框架
- `langchain-openai` - OpenAI API 集成
- `ultralytics` - YOLOWorld 检测
- `opencv-python` - 图像处理
- `torch` - 深度学习框架

**导航环境** (NavRL)：
```bash
# 需要单独配置 PPO 导航环境
conda env create -f src/navigation_runner/cfg/environment.yaml
conda activate NavRL
```

## 安装

```bash
# step1: 安装系统依赖
sudo apt install ros-${ROS_DISTRO}-octomap* 
sudo apt install ros-${ROS_DISTRO}-mavros* 
sudo apt install ros-${ROS_DISTRO}-vision-msgs

# step2: 克隆仓库
mkdir -p ~/catkin_ws/src
cd ~/catkin_ws/src
git clone https://github.com/your-repo/agent_fly.git

# step3: 克隆仿真器（如果需要）
git clone https://github.com/Zhefan-Xu/uav_simulator.git

# step4: 编译工作空间
cd ~/catkin_ws
catkin_make

# step5: 配置 Python 环境
conda env create -f src/agent/cfg/environment.yaml
conda activate agent_uav

# step6: 配置导航环境（可选）
conda create -n NavRL python=3.8
conda activate NavRL
pip install torch torchvision
```

## 快速开始

### 环境准备

**重要：如果系统中有多个 ROS 工作空间（如 my_ws），必须先清理环境变量！**

```bash
# 方法1: 使用清理脚本（推荐）
cd ~/catkin_ws
source scripts/clean_env.sh
source devel/setup.bash

# 方法2: 手动清理
unset ROS_PACKAGE_PATH
unset PYTHONPATH
unset CMAKE_PREFIX_PATH
source devel/setup.bash

# 激活 Agent 环境
conda activate agent_uav

# 设置 API Key（必需）
export OPENAI_API_KEY="your-api-key"

# 设置 API Base（可选，默认使用阿里云通义千问）
export OPENAI_API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"

# 验证环境（确保没有 my_ws）
echo "检查 ROS_PACKAGE_PATH:"
echo $ROS_PACKAGE_PATH | tr ':' '\n' | grep -v agent_ws | head -3
echo ""
echo "检查 PYTHONPATH:"
echo $PYTHONPATH | tr ':' '\n' | grep -v agent_ws | head -3
```

**检查清单**：
- ✅ ROS_PACKAGE_PATH 中不包含 `my_ws`
- ✅ PYTHONPATH 中不包含 `my_ws`
- ✅ conda 环境为 `agent_uav`
- ✅ OPENAI_API_KEY 已设置

**常见错误**：
- `ImportError: cannot import name 'PositionTarget'` → 说明环境未清理干净，重新执行清理步骤

### 启动系统

```bash
# 终端1: 启动仿真环境
source src/uav_simulator/gazeboSetup.bash
roslaunch uav_simulator start.launch

# 终端2: 启动完整系统（导航 + Agent + 视觉）
# 注意：需要在 agent_uav 环境中运行
conda activate agent_uav
roslaunch agent flight.launch

# 终端3: 启动 GUI 控制界面
conda activate agent_uav
rosrun agent agent_gui.py
```

**注意**：
- `navigation_node` 使用 NavRL 环境（通过 wrapper 脚本自动切换）
- `agent_node` 和 `vision_node` 需要在 agent_uav 环境中运行
- 如果遇到 `ImportError: cannot import name 'PositionTarget'`，说明有工作空间冲突，请参考"环境准备"部分清理环境变量

### 输入指令

在 GUI 界面输入自然语言指令，例如：
- "起飞到2米高度"
- "飞到坐标 (5, 3, 2)"
- "向前飞5米"
- "描述前方环境"
- "找到桌子并飞到它前面"
- "原地旋转搜索人"
- "降落"

## 可用工具

Agent 提供 8 个核心工具，通过 tools.py 封装：

| 工具名 | 描述 | 参数 | 特点 |
|--------|------|------|------|
| `takeoff` | 起飞到指定高度并悬停 | `{'height': 1.5}` | 自动稳定，默认1.5m |
| `land` | 降落到地面 | 无 | 安全降落，自动跟踪当前xy位置 |
| `set_goal` | 设置导航目标点 | `{'x': 5, 'y': 3, 'z': 1.5}` | 触发PPO导航，自动避障 |
| `rotate` | 原地旋转搜索 | `{'angle': 60}` | 默认60°步长，旋转后自动检测 |
| `get_detected_objects` | 获取检测到的物体 | 无 | YOLO检测+世界坐标 |
| `describe_scene` | VLM场景描述 | `{'query': '...'}` | 可选工具，Agent已能直接看画面 |
| `get_current_position` | 获取当前位置 | 无 | 返回 x, y, z, yaw |
| `get_flight_status` | 获取飞行状态 | 无 | IDLE/TAKEOFF/HOVER/NAVIGATE/LAND |

### 工具调用示例

**物体导航**：
```
用户: "飞到桌子前面"
Agent思考: 需要先检测桌子位置
Action: get_detected_objects()
Observation: 检测到 desk 在 (4.0, 2.0, 1.5)，距离 4.47m
Agent思考: 计算安全接近点（物体前1.8m）
Action: set_goal({'x': 2.4, 'y': 1.2, 'z': 1.5})
Final: 导航已委托，目标: (2.4, 1.2, 1.5)
```

**旋转搜索**：
```
用户: "找到人"
Agent思考: 先检测当前视野
Action: get_detected_objects()
Observation: 未检测到 person
Agent思考: 需要旋转搜索（相机FOV~60°）
Action: rotate({'angle': 60})
Observation: 旋转完成，检测到 person 在 (3.0, -2.0, 1.5)
Action: set_goal({'x': 1.5, 'y': -1.2, 'z': 1.5})
Final: 导航已委托
```

## 配置文件

### Agent 配置

| 文件 | 描述 |
|------|------|
| `src/agent/cfg/tools.json` | 工具定义（8个工具的描述和参数） |
| `src/agent/cfg/environment.yaml` | Conda 环境配置 |

### 导航配置

| 文件 | 描述 |
|------|------|
| `src/navigation_runner/cfg/drone.yaml` | 激光雷达参数（范围4m，144点） |
| `src/navigation_runner/scripts/cfg/train.yaml` | PPO 训练配置 |
| `src/navigation_runner/ckpts/navrl_checkpoint.pt` | PPO 模型权重 |

### 地图配置

| 文件 | 描述 |
|------|------|
| `src/navigation_runner/cfg/mapping/sim/no_map.yaml` | 实时建图配置（分辨率0.1m） |
| `src/navigation_runner/cfg/mapping/sim/prebuilt_map.yaml` | 预构建地图配置 |

### 检测配置

| 文件 | 描述 |
|------|------|
| `src/navigation_runner/cfg/detection/sim/fake_detector.yaml` | 仿真障碍物检测 |
| `src/navigation_runner/cfg/detection/sim/real_detector.yaml` | 真实YOLO检测 |

### 可视化配置

| 文件 | 描述 |
|------|------|
| `src/navigation_runner/rviz/navigation.rviz` | RViz 可视化配置 |

## Launch 参数

### flight.launch

| 参数 | 默认值 | 描述 |
|------|--------|------|
| `use_px4` | `false` | 是否使用PX4模式（true=真机，false=仿真） |
| `use_prebuilt_map` | `false` | 是否使用预构建地图 |
| `use_real_detector` | `false` | 是否使用真实YOLO检测器 |
| `use_safety_shield` | `true` | 是否启用安全防护层 |
| `takeoff_height` | `1.5` | 起飞高度 (m) |
| `rviz` | `true` | 是否启动 RViz |
| `pcd_file` | `""` | PCD地图文件路径（可选） |

### 模式切换

**仿真模式** (默认):
```bash
roslaunch agent flight.launch use_px4:=false
```

**PX4真机模式**:
```bash
roslaunch agent flight.launch use_px4:=true
```

**使用预构建地图**:
```bash
roslaunch agent flight.launch use_prebuilt_map:=true pcd_file:=/path/to/map.pcd
```

## 核心话题

### 控制与状态

| 话题 | 类型 | 描述 |
|------|------|------|
| `/agent_node/user_command` | String | 用户命令输入 |
| `/agent_node/agent_log` | String | Agent 日志输出 |
| `/move_base_simple/goal` | PoseStamped | 导航目标点 |
| `/CERLAB/quadcopter/odom` | Odometry | 无人机里程计 |
| `/CERLAB/quadcopter/cmd_vel` | TwistStamped | 速度控制（PPO输出） |
| `/CERLAB/quadcopter/setpoint_pose` | PoseStamped | 位置控制 |

### 感知

| 话题 | 类型 | 描述 |
|------|------|------|
| `/camera/depth/image_raw` | Image | 深度图像 (640×480) |
| `/camera/color/image_raw` | Image | 彩色图像 (640×480) |
| `/vision_node/env_description` | String | 物体检测结果（JSON） |

### 可视化

| 话题 | 类型 | 描述 |
|------|------|------|
| `/occupancy_map/local_map` | PointCloud2 | 局部占据地图 |
| `/rl_navigation/raycast` | PointCloud2 | 激光雷达模拟 |
| `/rl_navigation/goal` | Marker | 当前目标点 |


## 注意事项

1. **环境切换**: Agent 使用 `agent_uav` 环境，导航使用 `NavRL` 环境（通过 wrapper 脚本自动切换）

2. **自动起飞**: `navigation_node` 启动时会自动起飞到 1.5m 高度

3. **单次移动限制**: 安全层限制单次移动距离 ≤20m，超过需分段导航

4. **视觉模式**: Agent 自动判断是否需要视觉输入，纯文本任务不启用图像（节省成本）

5. **物体导航**: 目标点必须设置在物体前方 1.5-2.0m，避免被判定为障碍物

## 故障排除

### 1. Agent 无响应
```bash
# 检查 API Key
echo $OPENAI_API_KEY

# 检查 API 配额
# 如果提示 "AllocationQuota" 错误，说明配额用完

# 查看日志
rostopic echo /agent_node/agent_log
```

### 2. 无人机不移动
```bash
# 检查导航节点是否运行
rosnode list | grep navigation

# 检查速度命令
rostopic echo /CERLAB/quadcopter/cmd_vel

# 检查是否已设置目标
rostopic echo /move_base_simple/goal
```

### 3. YOLO 检测无结果
```bash
# 检查 vision 节点
rosnode list | grep vision

# 检查图像话题
rostopic hz /camera/color/image_raw

# 查看检测结果
rostopic echo /vision_node/env_description
```

### 4. 地图为空
```bash
# 检查深度图像
rostopic hz /camera/depth/image_raw

# 检查地图节点
rosnode list | grep occupancy_map

# 查看地图话题
rostopic echo /occupancy_map/local_map
```

### 5. GPU 内存不足
```yaml
# 修改 navigation_runner/scripts/cfg/train.yaml
device: "cpu"  # 改为 CPU 模式
```
