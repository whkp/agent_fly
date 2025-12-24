# UAV Agent

基于 LLM 的智能无人机控制 Agent，使用 CERLAB autonomous_flight 导航系统。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户交互层                                      │
│  ┌─────────────┐                                                            │
│  │ agent_cli.py│  ←── 用户自然语言指令 (终端界面)                            │
│  └──────┬──────┘                                                            │
│         │ ROS Topic                                                         │
│         ▼                                                                   │
│  ┌─────────────┐                                                            │
│  │  agent.py   │  ←── LLM Agent (解析指令、调用工具)                         │
│  └──────┬──────┘                                                            │
│         │                                                                   │
├─────────┼───────────────────────────────────────────────────────────────────┤
│         │                        工具层                                      │
│         ▼                                                                   │
│  ┌─────────────┐     /move_base_simple/goal                                 │
│  │  tools.py   │ ─────────────────────────────┐                             │
│  └──────┬──────┘                              │                             │
│         │ /CERLAB/quadcopter/setpoint_pose    │                             │
│         │ (直接位置控制)                       │                             │
├─────────┼─────────────────────────────────────┼─────────────────────────────┤
│         │                    导航规划层        │                             │
│         │                              ┌──────▼──────┐                      │
│         │                              │navigation   │                      │
│         │                              │   _node     │ ←── 轨迹规划 + 避障   │
│         │                              └──────┬──────┘                      │
│         │                                     │ 轨迹                        │
│         │                              ┌──────▼──────┐                      │
│         │                              │ tracking    │                      │
│         │                              │ _controller │ ←── 轨迹跟踪控制      │
│         │                              └──────┬──────┘                      │
│         │                                     │ /CERLAB/quadcopter/cmd_acc  │
├─────────┼─────────────────────────────────────┼─────────────────────────────┤
│         │                    仿真器层          │                             │
│         ▼                                     ▼                             │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                    uav_simulator (Non-PX4)                      │        │
│  │  • /CERLAB/quadcopter/odom         (里程计输出)                  │        │
│  │  • /CERLAB/quadcopter/cmd_acc      (加速度控制输入)              │        │
│  │  • /CERLAB/quadcopter/setpoint_pose (位置控制输入)              │        │
│  │  • /camera/depth/image_raw         (深度图像)                   │        │
│  │  • /camera/color/image_raw         (彩色图像)                   │        │
│  └─────────────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 依赖

### 系统依赖
- Ubuntu 20.04
- ROS Noetic
- Gazebo 11
- NVIDIA GPU (可选，用于 YOLO 检测加速)

### ROS 包依赖
- CERLAB-UAV-Autonomy
  - `autonomous_flight` - 导航节点
  - `tracking_controller` - 轨迹跟踪控制器
  - `uav_simulator` - 仿真环境
  - `map_manager` - 地图管理

### Python 依赖

使用 conda 环境：
```bash
conda env create -f cfg/environment.yaml
conda activate agent_uav
```

或手动安装核心依赖：
```bash
pip install langchain langchain-openai openai torch ultralytics
```

## 快速开始

### 环境准备

```bash
# 1. Source Gazebo 插件路径
source ~/Documents/agent_ws/src/CERLAB-UAV-Autonomy/uav_simulator/gazeboSetup.bash

# 2. Source ROS 工作空间
source ~/Documents/agent_ws/devel/setup.bash

# 3. 设置 OpenAI API Key
export OPENAI_API_KEY="your-api-key"
```

### 启动系统

```bash
# 终端1: 启动仿真环境
roslaunch uav_simulator start.launch

# 终端2: 启动导航系统 + Agent
roslaunch agent flight.launch

# 终端3: 启动CLI控制界面
rosrun agent agent_cli.py
```

## CLI 使用

```
======================================================================
🚁 Agent UAV 控制面板 (CERLAB autonomous_flight)
======================================================================

📋 命令:
  1. 获取位置     - 获取当前位置
  2. 获取状态     - 获取飞行状态
  3. 自定义命令   - 输入自定义指令 [大模型]
  4. 显示日志     - 显示系统日志
----------------------------------------------------------------------
  🛫 飞行控制:
  t. 起飞         - 起飞到指定高度
  l. 降落         - 降落到地面
  g. 导航         - 设置导航目标 [x, y, z]
----------------------------------------------------------------------
  0. 退出
======================================================================
```

## 可用工具

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `takeoff` | 起飞到指定高度 | `{'height': 1.5}` |
| `land` | 降落 | 无 |
| `set_goal` | 设置导航目标点 (自动避障) | `{'x': 5, 'y': 3, 'z': 1.5}` |
| `get_current_position` | 获取当前位置 | 无 |
| `get_flight_status` | 获取飞行状态 | 无 |

## Launch 参数

### flight.launch

| 参数 | 默认值 | 描述 |
|------|--------|------|
| `odom_topic` | `/CERLAB/quadcopter/odom` | 里程计话题 |
| `takeoff_height` | `1.5` | 起飞高度 (m) |
| `desired_velocity` | `2.0` | 期望速度 (m/s) |
| `desired_acceleration` | `3.0` | 期望加速度 (m/s²) |
| `rviz` | `true` | 是否启动 RViz |

## 配置文件

| 文件 | 描述 |
|------|------|
| `cfg/mapping.yaml` | 占据地图参数 |
| `cfg/planner.yaml` | 路径规划参数 |
| `cfg/tools.json` | Agent 工具定义 |
| `cfg/flight.rviz` | RViz 可视化配置 |
| `cfg/environment.yaml` | Conda 环境配置 |

## 文件结构

```
agent/
├── agent.py              # LLM Agent 主程序
├── agent_cli.py          # CLI 控制界面
├── tools.py              # 工具接口
├── vision.py             # 视觉模块 (YOLO)
├── cfg/
│   ├── mapping.yaml      # 地图参数
│   ├── planner.yaml      # 规划参数
│   ├── tools.json        # 工具定义
│   ├── flight.rviz       # RViz 配置
│   └── environment.yaml  # Conda 环境
├── launch/
│   ├── flight.launch     # 完整导航启动
│   └── takeoff.launch    # 起飞悬停启动
└── scripts/
    ├── run_flight.sh     # 启动脚本
    └── start_cli.sh      # CLI 启动脚本
```

## 注意事项

1. **Gazebo 插件**: 启动前必须 source `gazeboSetup.bash`，否则无人机不会发布里程计数据

2. **自动起飞**: `navigation_node` 启动时会自动起飞到设定高度

3. **路径长度限制**: 默认最大规划路径长度为 20m，超过需分段导航

4. **坐标系**: 使用 `map` 作为全局坐标系

## 故障排除

### 无里程计数据
```bash
# 检查是否 source 了 gazeboSetup.bash
echo $GAZEBO_PLUGIN_PATH
# 应包含 uav_simulator/plugins 路径

# 检查话题
rostopic hz /CERLAB/quadcopter/odom
```

### A* 路径规划失败
- 检查 RViz 中的 `/occupancy_map/voxel_map` 是否有虚假障碍物
- 尝试设置更近的目标点
- 检查 `cfg/planner.yaml` 中的 `max_path_length` 参数

### Agent 无响应
```bash
# 检查 API Key
echo $OPENAI_API_KEY

# 查看 agent 日志
rosrun agent agent.py
```
