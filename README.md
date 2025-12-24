# UAV Agent

基于 LLM 的智能无人机控制 Agent，使用 CERLAB autonomous_flight 导航系统。

## 系统架构

```
用户指令 → Agent (LLM) → tools.py → navigation_node → tracking_controller → uav_simulator
```

- **Agent**: 基于 LangChain 的 LLM Agent，解析用户自然语言指令
- **tools.py**: 工具接口，提供起飞、降落、导航等功能
- **navigation_node**: CERLAB 导航节点，负责轨迹规划和避障
- **tracking_controller**: 轨迹跟踪控制器
- **uav_simulator**: CERLAB Non-PX4 仿真器

## 依赖

- Ubuntu 20.04
- ROS Noetic
- Gazebo 11
- CERLAB-UAV-Autonomy (autonomous_flight, tracking_controller, uav_simulator, map_manager)
- Python 依赖: `conda env create -f agent/cfg/environment.yaml`

### 安装
```bash
# step1: install dependencies
sudo apt install ros-${ROS_DISTRO}-octomap* && sudo apt install ros-${ROS_DISTRO}-mavros* && sudo apt install ros-${ROS_DISTRO}-vision-msgs
# step2: clone repo
mkdir -p ~/Documents/agent_ws
cd ~/Documents/agent_ws
git clone --recursive https://github.com/whkp/agent_fly.git
# optional: switch to simulation branch for autonomous_flight
# the default branch is for real flight and PX4 simulation
cd path/to/autonomous_flight
git checkout simulation

# step3: build workspace
cd ~/Documents/agent_ws
catkin_make

```

## 使用方法

### 1. 启动仿真环境

```bash
source devel/setup.bash
source ~/Documents/agent_ws/src/CERLAB-UAV-Autonomy/uav_simulator/gazeboSetup.bash
roslaunch uav_simulator start.launch
```

### 2. 启动导航系统 + Agent 后台

```bash
source devel/setup.bash
roslaunch agent flight.launch
```

### 3. 启动终端控制界面（新终端）

```bash
source devel/setup.bash
rosrun agent agent_cli.py
```

### 4. 输入指令

在 Agent 终端输入自然语言指令，例如：
- "起飞到2米高度"
- "飞到坐标 (5, 3, 2)"
- "向前飞5米"
- "降落"

## 可用工具

navigation_node 启动时会自动执行起飞，tools.py 主要负责状态监控和目标点发布

| 工具名 | 描述 | 参数 |
|--------|------|------|
| takeoff | 起飞到指定高度 | `{'height': float}` |
| land | 降落 | 无 |
| set_goal | 设置导航目标点 | `{'x': float, 'y': float, 'z': float}` |
| get_current_position | 获取当前位置 | 无 |
| get_flight_status | 获取飞行状态 | 无 |

## 配置文件

| 文件 | 描述 |
|------|------|
| `agent/cfg/mapping.yaml` | 占据地图参数 |
| `agent/cfg/planner.yaml` | 路径规划参数 |
| `agent/cfg/tools.json` | Agent 工具定义 |
| `agent/cfg/flight.rviz` | RViz 可视化配置 |
| `agent/cfg/environment.yaml` | Conda 环境配置 |

## Launch 参数

```xml
<arg name="odom_topic" default="/CERLAB/quadcopter/odom"/>  <!-- 里程计话题 -->
<arg name="takeoff_height" default="1.5"/>                   <!-- 起飞高度 -->
<arg name="desired_velocity" default="2.0"/>                 <!-- 期望速度 m/s -->
<arg name="desired_acceleration" default="3.0"/>             <!-- 期望加速度 m/s² -->
<arg name="rviz" default="true"/>                            <!-- 是否启动 RViz -->
```

## 话题

### 仿真器话题 (Non-PX4)

| 话题 | 类型 | 描述 |
|------|------|------|
| `/CERLAB/quadcopter/odom` | Odometry | 无人机里程计 |
| `/CERLAB/quadcopter/pose` | PoseStamped | 无人机位姿 |
| `/CERLAB/quadcopter/cmd_acc` | AccelStamped | 加速度控制指令 |
| `/CERLAB/quadcopter/setpoint_pose` | PoseStamped | 位置控制指令 |
| `/camera/depth/image_raw` | Image | 深度图像 |
| `/camera/color/image_raw` | Image | 彩色图像 |

### 导航话题

| 话题 | 类型 | 描述 |
|------|------|------|
| `/move_base_simple/goal` | PoseStamped | 导航目标点 |
| `/bspline_traj/trajectory` | Path | B样条轨迹 |
| `/occupancy_map/voxel_map` | PointCloud2 | 占据栅格地图 |
| `/tracking_controller/trajectory_history` | Path | 历史轨迹 |

### Agent 话题

| 话题 | 类型 | 描述 |
|------|------|------|
| `/agent/status` | String | Agent 飞行状态 |
| `/agent_node/user_command` | String | 用户命令输入 |
| `/agent_node/agent_log` | String | Agent 日志输出 |

## 注意事项

1. **Gazebo 插件**: 启动仿真前必须 source `gazeboSetup.bash`
2. **自动起飞**: `navigation_node` 启动时会自动起飞
3. **坐标系**: 使用 `map` 作为全局坐标系
4. **路径长度**: 默认最大规划路径 20m，超过需分段导航

