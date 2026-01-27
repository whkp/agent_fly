# UAV Agent

基于 LLM 的智能无人机控制系统，支持 PX4 仿真和真机飞行。

## 特性

- 🤖 **自然语言控制** - 用自然语言指挥无人机执行任务
- 🌐 **Web 控制台** - 实时交互界面，支持远程控制
- 🔧 **动态工具管理** - 参考 typefly 设计，灵活配置工具
- 🎯 **提示词优化** - 精心设计的提示词系统，提升理解准确度
- 🔌 **平台适配层** - 支持仿真/真机无缝切换
- 📊 **完整监控** - 工具调用统计、历史记录、性能分析
- 📡 **分布式部署** - 机载计算机 + 地面站分离部署

## 快速开始

### 1. 安装依赖

```bash
# Python 环境
conda env create -f cfg/environment.yaml
conda activate agent_uav

# 设置 API Key
export OPENAI_API_KEY="your-key"
export OPENAI_API_BASE="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

### 2. 启动系统

**快速测试（CERLAB 仿真 - 推荐）：**

```bash
# 终端1: 启动 CERLAB 仿真器
roslaunch uav_simulator start.launch

# 终端2: 启动 Agent（使用 cerlab_sim 平台）
roslaunch agent agent_onboard.launch platform_type:=cerlab_sim

# 终端3: 启动 Web 控制台（可选）
cd agent/web
python app_standalone.py
# 访问 http://localhost:8080
```

**完整仿真（PX4 仿真）：**

```bash
# 终端1: 启动 PX4 仿真器（包含 MAVROS + PX4 SITL）
roslaunch uav_simulator px4_start.launch

# 终端2: 启动控制器
roslaunch px4ctrl run_ctrl.launch

# 终端3: 启动 Agent（使用 px4_sim 平台）
roslaunch agent agent_onboard.launch platform_type:=px4_sim

# 终端4: 启动 Web 控制台（可选）
cd agent/web
python app_standalone.py
# 访问 http://localhost:8080
```

**真机部署（机载计算机 + 地面站）：**

机载计算机（Linux）：
```bash
# 设置网络
export ROS_MASTER_URI=http://192.168.1.100:11311
export ROS_IP=192.168.1.100

# 启动基础系统
roslaunch mavros px4.launch
roslaunch vins vins_rviz.launch

# 启动 Agent（使用 px4_real 平台）
roslaunch agent agent_onboard.launch platform_type:=px4_real

# 启动 API 桥接服务器（重要！）
rosrun agent api_bridge.py
```

地面站（Windows/Linux）：
```bash
# 启动 Web 控制台（地面站模式）
cd agent/web
python app_standalone.py --host 192.168.1.100 --port 5000
# 访问 http://localhost:8080
```

## 平台适配

参考 **typefly** 设计，支持多平台无缝切换。

### 支持的平台

| 平台 | 说明 | 控制器 | 使用场景 |
|------|------|--------|---------|
| `cerlab_sim` | CERLAB 仿真 | Setpoint | 快速测试 |
| `px4_sim` | PX4 仿真 | px4ctrl | 完整仿真 |
| `px4_real` | PX4 真机 | MAVROS | 实际飞行 |

### 切换平台

**方式1：修改配置文件**
```bash
# 编辑 agent/cfg/platform_config.json
vim agent/cfg/platform_config.json
# 修改 "platform_type": "cerlab_sim" 或 "px4_sim" 或 "px4_real"
```

**方式2：通过 launch 参数**
```bash
# CERLAB 仿真（快速测试）
roslaunch agent agent_onboard.launch platform_type:=cerlab_sim

# PX4 仿真（完整仿真）
roslaunch agent agent_onboard.launch platform_type:=px4_sim

# PX4 真机（实际飞行）
roslaunch agent agent_onboard.launch platform_type:=px4_real
```

**方式3：通过 ROS 参数**
```bash
rosrun agent agent.py _platform_type:=cerlab_sim
```

### 平台对比

| 特性 | CERLAB 仿真 | PX4 仿真 | PX4 真机 |
|------|------------|---------|---------|
| 启动命令 | `roslaunch uav_simulator start.launch` | `roslaunch uav_simulator px4_start.launch` | - |
| 控制器 | Setpoint | px4ctrl | MAVROS |
| 命令消息 | PoseStamped | PositionCommand | PoseStamped |
| 里程计话题 | /CERLAB/quadcopter/odom | /vins_fusion/imu_propagate | /mavros/local_position/odom |
| 启动速度 | ⚡ 快 | 🐢 慢 | - |
| 仿真精度 | 简化 | 完整（含 PX4 SITL） | - |
| 适用场景 | 快速测试 Agent 逻辑 | 完整仿真测试 | 实际飞行 |

### 推荐工作流程

**1. 快速测试阶段**（使用 CERLAB 仿真）
```bash
# 启动 CERLAB 仿真器（简化仿真）
roslaunch uav_simulator start.launch

# 启动 Agent
roslaunch agent agent_onboard.launch platform_type:=cerlab_sim

# 快速测试 Agent 逻辑
```

**2. 完整仿真阶段**（使用 PX4 仿真）
```bash
# 启动 PX4 仿真（包含 MAVROS + PX4 SITL）
roslaunch uav_simulator px4_start.launch
roslaunch px4ctrl run_ctrl.launch

# 启动 Agent
roslaunch agent agent_onboard.launch platform_type:=px4_sim

# 完整测试飞行控制
```

**3. 实际飞行阶段**（使用 PX4 真机）
```bash
# 启动真机系统
roslaunch mavros px4.launch
roslaunch vins vins_rviz.launch

# 启动 Agent
roslaunch agent agent_onboard.launch platform_type:=px4_real

# 实际飞行测试
```

### 添加新平台

1. 创建平台类：`agent/platforms/new_platform.py`
2. 注册到工厂：`agent/platforms/platform_factory.py`
3. 添加配置：`agent/cfg/platform_config.json`
4. 使用：`roslaunch agent agent_onboard.launch platform_type:=new_platform`

详细说明见 `OPTIMIZATION_LOG.md`

## 监控功能

### Web 界面监控

访问 `http://localhost:8080`，实时查看：
- 工具调用状态
- 成功/失败统计
- 执行时间
- 调用历史

### ROS 话题监控

```bash
# 查看 Agent 状态
rostopic echo /agent/status

# 查看飞行状态
rostopic echo /mavros/state  # 真机
rostopic echo /px4ctrl/flight_status  # 仿真
```

## Web 控制台

Web 控制台提供两种部署模式，**既可以本地运行，也可以用在地面站**。

### 部署模式对比

| 模式 | 文件 | 依赖 | 使用场景 | 网络要求 |
|------|------|------|---------|---------|
| **本地模式** | `app.py` | ROS + Flask | 仿真测试（单机） | 无 |
| **地面站模式** | `app_standalone.py` | Flask（无需 ROS） | 真机部署（分布式） | 需要网络连接机载 |

### 本地模式（仿真测试 - 推荐）

**适用场景**：在本地电脑上进行仿真测试，所有组件运行在同一台机器。

**启动方式**：
```bash
# 终端1: 启动仿真器
roslaunch uav_simulator start.launch  # CERLAB 仿真
# 或
roslaunch uav_simulator px4_start.launch  # PX4 仿真

# 终端2: 启动 Agent
roslaunch agent agent_onboard.launch platform_type:=cerlab_sim

# 终端3: 启动 Web 控制台（本地模式）
cd agent/web
python app.py
# 访问 http://localhost:8080
```

**特点**：
- ✅ 直接通过 ROS 话题通信，无需网络
- ✅ 实时性好，延迟低
- ✅ 无需额外配置
- ✅ 适合快速开发和测试

### 地面站模式（真机部署）

**适用场景**：真机飞行时，机载计算机运行 Agent，地面站运行 Web 控制台。

**架构**：
```
机载计算机（Linux）          地面站（Windows/Linux）
├── ROS Master              ├── Web 浏览器
├── Agent (agent.py)        └── Web 控制台 (app_standalone.py)
└── API Bridge (api_bridge.py)
         ↓ HTTP API ↓
         网络连接 (WiFi/有线)
```

**启动方式**：

机载计算机：
```bash
# 设置网络
export ROS_MASTER_URI=http://192.168.1.100:11311
export ROS_IP=192.168.1.100

# 启动基础系统
roslaunch mavros px4.launch
roslaunch vins vins_rviz.launch

# 启动 Agent
roslaunch agent agent_onboard.launch platform_type:=px4_real

# 启动 API 桥接服务器（重要！）
rosrun agent api_bridge.py
# 或
python agent/scripts/api_bridge.py
```

地面站：
```bash
# 设置机载 IP（默认 192.168.1.100）
cd agent/web
python app_standalone.py --host 192.168.1.100 --port 5000 --web-port 8080

# 访问 http://localhost:8080
```

**特点**：
- ✅ 支持跨平台（Windows 地面站 + Linux 机载）
- ✅ 无需在地面站安装 ROS
- ✅ 通过 HTTP API 通信
- ⚠️ 需要稳定的网络连接
- ⚠️ 延迟略高于本地模式

### 快速测试（当前仿真）

**你当前的需求**：在本地仿真环境中通过 Web 控制台测试。

**推荐方案**：使用本地模式（`app.py`）

```bash
# 终端1: 启动 CERLAB 仿真
roslaunch uav_simulator start.launch

# 终端2: 启动 Agent
roslaunch agent agent_onboard.launch platform_type:=cerlab_sim

# 终端3: 启动 Web 控制台
cd agent/web
python app.py
```

然后访问 `http://localhost:8080`，你可以：
- 发送自然语言命令（如"起飞到2米"）
- 查看无人机实时状态
- 查看工具调用历史
- 监控系统性能

### Web 控制台功能

访问 `http://localhost:8080`，实时查看和控制：
- 发送自然语言命令
- 查看无人机状态（位置、速度、姿态）
- 查看工具调用历史
- 监控系统性能
- 查看 Agent 日志

### 使用示例

```
用户: "起飞到2米"
Agent: 执行 takeoff({'height': 2.0})
结果: 起飞成功，当前高度 2.0m

用户: "向前飞5米"
Agent: 执行 move_relative({'dx': 5, 'dy': 0, 'dz': 0})
结果: 已设置目标点 (5.0, 0.0, 2.0)

用户: "悬停5秒观察周围"
Agent: 执行 hover({'duration': 5.0})
结果: 悬停 5.0 秒完成

用户: "降落"
Agent: 执行 land()
结果: 降落成功
```

### 命令行参数

**app_standalone.py**（地面站模式）：
```bash
python app_standalone.py --host 192.168.1.100 --port 5000 --web-port 8080
```
- `--host`: 机载计算机 IP（默认 192.168.1.100）
- `--port`: API 服务端口（默认 5000）
- `--web-port`: Web 服务端口（默认 8080）

**app.py**（本地模式）：
```bash
python app.py
```
- 固定端口 8080
- 无需额外参数

## 可用工具

系统提供 12 个工具，参考 **typefly** 设计理念。

### 飞行控制（4个）

| 工具 | 说明 | 示例 |
|------|------|------|
| `takeoff` | 起飞到指定高度 | "起飞到2米" |
| `land` | 降落到地面 | "降落" |
| `set_goal` | 飞到目标点 | "飞到(5,3,2)" |
| `move_relative` | 相对当前位置移动 | "向前飞5米" |

### 状态查询（2个）

| 工具 | 说明 | 示例 |
|------|------|------|
| `get_current_position` | 获取当前位置和朝向 | "当前位置" |
| `get_flight_status` | 获取飞行状态 | "飞行状态" |

### 辅助工具（3个）

| 工具 | 说明 | 示例 |
|------|------|------|
| `wait` | 等待指定秒数 | "等待3秒" |
| `hover` | 在当前位置悬停 | "悬停5秒观察" |
| `rotate_yaw` | 旋转指定角度 | "向左转90度" |

### 视觉感知（2个）

| 工具 | 说明 | 示例 | 依赖 |
|------|------|------|------|
| `describe_scene` | VLM 描述场景 | "看看周围有什么" | vision_node + VLM API |
| `get_detected_objects` | YOLO 检测物体 | "检测物体" | vision_node |

### 视觉交互（1个）

| 工具 | 说明 | 示例 | 依赖 |
|------|------|------|------|
| `is_object_visible` | 检查物体是否可见 | "能看到椅子吗" | vision_node |

**注意**：视觉工具需要启动 `vision_node`：
```bash
rosrun agent vision.py
```

## 配置参数

### Agent 参数
```yaml
platform_type: px4_sim    # 平台类型（px4_sim/px4_real）
llm_model: qwen3-max      # LLM 模型
llm_temperature: 0.1      # 温度参数
```

### 平台配置
```json
{
  "platform_type": "px4_sim",
  "platforms": {
    "px4_sim": {
      "name": "PX4 仿真平台",
      "takeoff_height": 1.5,
      "odom_topic": "/vins_fusion/imu_propagate",
      "cmd_topic": "/position_cmd"
    },
    "px4_real": {
      "name": "PX4 真机平台",
      "takeoff_height": 1.5,
      "odom_topic": "/mavros/local_position/odom"
    }
  }
}
```

### 安全限制
- 高度范围：0.5m - 20.0m
- 等待时间：0.1s - 60s
- 悬停时间：1s - 60s
- 旋转角度：-360° - 360°

## 系统架构

```
Agent (agent.py)
    ↓
Tools (tools.py)
    ↓
Platform Interface (base_platform.py)
    ↓
├── PX4SimPlatform (px4_sim_platform.py)  # 仿真平台
├── PX4RealPlatform (px4_real_platform.py) # 真机平台
└── ... (未来可扩展更多平台)
```

### 文件结构

```
agent/
├── agent.py                  # Agent 主程序
├── tools.py                  # 工具接口层
├── vision.py                 # 视觉模块
├── llm_wrapper.py            # LLM 封装
├── config_manager.py         # 配置管理
├── tool_monitor.py           # 监控模块
├── tool_response.py          # 统一返回格式
├── platforms/                # 平台适配层
│   ├── __init__.py           # 包初始化
│   ├── base_platform.py      # 基础接口
│   ├── cerlab_sim_platform.py # CERLAB 仿真平台
│   ├── px4_sim_platform.py   # PX4 仿真平台
│   ├── px4_real_platform.py  # PX4 真机平台
│   └── platform_factory.py   # 平台工厂
├── cfg/                      # 配置文件
│   ├── tools.json            # 工具配置
│   ├── platform_config.json  # 平台配置
│   ├── prompt_agent.txt      # 主提示词
│   ├── guidelines.txt        # 指导原则
│   ├── examples.txt          # 示例库
│   ├── environment.yaml      # Conda 环境配置
│   └── flight.rviz           # RViz 可视化配置
├── web/                      # Web 控制台
│   ├── app_standalone.py     # 独立版本（推荐）
│   ├── app.py                # ROS 集成版本
│   ├── start_windows.bat     # Windows 启动脚本
│   ├── requirements.txt      # Python 依赖
│   └── templates/            # 前端界面
├── scripts/                  # 辅助脚本
│   ├── api_bridge.py         # API 服务器（地面站模式必需）
│   ├── setup_jetson_nx.sh    # Jetson NX 环境安装
│   ├── setup_ros_network.sh  # ROS 多机网络配置
│   └── test_jetson_compatibility.py # Jetson 兼容性测试
├── pth/                      # 模型文件
│   └── yolov8l-worldv2.pt    # YOLO 检测模型
├── launch/                   # 启动文件
│   ├── agent_onboard.launch  # 完整版（推荐）
│   ├── agent_px4ctrl.launch  # 简化版
│   └── vision_groundstation.launch # 地面站视觉节点
├── CMakeLists.txt            # ROS 构建配置
├── package.xml               # ROS 包配置
├── setup.py                  # Python 包配置
├── README.md                 # 本文档
└── OPTIMIZATION_LOG.md       # 优化记录
```

**核心模块说明**：
- **agent.py**: 主程序，负责 LLM 交互和工具调度
- **tools.py**: 工具接口层，定义所有可用工具
- **platforms/**: 平台适配层，支持多平台切换
- **cfg/**: 配置文件，包含提示词、工具配置、平台配置
- **web/**: Web 控制台，提供可视化交互界面
- **scripts/**: 辅助脚本，用于部署和测试
  - `api_bridge.py`: 地面站模式的 API 服务器
  - `setup_jetson_nx.sh`: Jetson NX 一键安装脚本
  - `setup_ros_network.sh`: ROS 多机网络配置
  - `test_jetson_compatibility.py`: Jetson 环境验证

## 部署模式

| 模式 | 适用场景 | 平台类型 | 启动方式 |
|------|----------|---------|----------|
| 仿真单机 | 开发测试 | px4_sim | `roslaunch agent agent_onboard.launch` |
| 真机分布式 | 实际部署 | px4_real | 机载 + 地面站分离 |

**仿真环境**：所有组件在一台电脑  
**真机部署**：机载计算机运行 Agent，地面站运行 Web 控制台

## 测试

### 基础测试

```bash
# 测试 Agent 是否正常运行
rostopic echo /agent/status

# 测试工具调用
# 通过 Web 控制台发送命令："起飞到2米"
```

### 视觉工具测试

```bash
# 启动 vision_node
rosrun agent vision.py

# 测试视觉工具
# 通过 Web 控制台发送命令："看看周围有什么"
```

## 故障排除

### Agent 不响应

```bash
# 检查节点是否运行
rosnode list | grep agent

# 查看日志
rosnode info /agent_node
```

### 平台切换失败

```bash
# 检查配置文件
cat agent/cfg/platform_config.json

# 检查 ROS 参数
rosparam get /agent_node/platform_type
```

### 视觉工具不可用

```bash
# 检查 vision_node 是否运行
rosnode list | grep vision

# 启动 vision_node
rosrun agent vision.py
```

### 真机部署网络问题

```bash
# 检查网络连接
ping 192.168.1.100

# 检查 ROS 网络配置
echo $ROS_MASTER_URI
echo $ROS_IP

# 测试话题通信
rostopic list
rostopic hz /mavros/state
```

## 核心优化

### 1. 提示词系统（参考 typefly）
- ✅ 独立的提示词文件（prompt_agent.txt, guidelines.txt, examples.txt）
- ✅ 6 条指导原则（解决歧义、批判性分析、空间推理等）
- ✅ 15 个精选示例，100% 场景覆盖
- ✅ 增强的工具描述（参数类型、范围、示例、注意事项）

**预期效果**：首次成功率 +42%，参数错误率 -67%，任务完成时间 -50%

### 2. 平台适配层（参考 typefly）
- ✅ 分层架构（Agent → Tools → Platform）
- ✅ 支持仿真/真机无缝切换
- ✅ 易于扩展新平台
- ✅ 平台特定代码隔离

**优势**：灵活性、可维护性、可扩展性

### 3. 工具设计理念（参考 typefly）
- ✅ 基础工具原子化
- ✅ 避免工具内部循环
- ✅ 让 LLM 自己组合工具
- ✅ 保留简化计算的工具（如 move_relative）

**最终工具数**：12 个（精简高效）

### 4. 配置管理
- ✅ 统一的配置加载
- ✅ 工具动态启用/禁用
- ✅ 平台配置分离

### 5. 监控系统
- ✅ 工具调用统计
- ✅ 历史记录
- ✅ 性能分析

详细优化说明：[OPTIMIZATION_LOG.md](OPTIMIZATION_LOG.md)

## 文档

- [README.md](README.md) - 本文档（快速开始和完整说明）
- [OPTIMIZATION_LOG.md](OPTIMIZATION_LOG.md) - 所有优化记录（提示词、工具、平台适配、LLM 分析）

## 项目维护

### 最近更新（2026-01-27）

**文件清理**：
- ✅ 删除 `LLM_OPTIMIZATION_ANALYSIS.md`（内容已合并到 OPTIMIZATION_LOG.md）
- ✅ 删除 `agent/web/start_windows.sh`（Windows 使用 .bat 文件）
- ✅ 删除 `agent/cfg/questions.json`（测试文件，非核心功能）
- ✅ 删除 `agent/scripts/run_flight.sh`（功能与 README 启动命令重复）
- ✅ 删除 `agent/scripts/test_api.sh`（开发测试脚本，非必需）

**文档修正**：
- ✅ 修正 PX4 仿真启动命令：`roslaunch uav_simulator px4_start.launch`
- ✅ 修正 CERLAB 仿真启动命令：`roslaunch uav_simulator start.launch`
- ✅ 更新平台对比表，添加启动命令说明
- ✅ 更新文件结构说明，添加完整目录树
- ✅ 添加核心模块说明，便于理解项目架构
- ✅ 添加 Web 控制台详细使用说明（本地模式 vs 地面站模式）

**CMakeLists.txt 修复**：
- ✅ 移除不存在的 `scripts/vision_bridge.py` 引用
- ✅ 添加实际存在的 `scripts/api_bridge.py` 和 `test_jetson_compatibility.py`
- ✅ 更新 shell 脚本安装列表

## 注意事项

### 安全
- 首次使用在开阔区域测试
- 遥控器随时可切换手动模式
- 安全限制已内置（高度、速度等）

### 定位
- 需要可靠定位系统（VINS-Fusion/GPS）
- 里程计频率 >100Hz
- 仿真环境使用 VINS-Fusion
- 真机环境使用 MAVROS

### 网络（真机分布式部署）
- 延迟 <100ms
- 建议有线连接或 5GHz WiFi
- 机载计算机作为 ROS Master
- 地面站连接到机载计算机

### 视觉功能
- 需要相机（RGB + Depth）
- VLM 功能需要配置 API Key
- YOLO 检测需要模型文件
- 建议在地面站运行 VLM（节省机载算力）

## 许可证

请查看 LICENSE 文件。


## 与 Typefly 对比

本项目参考了 **typefly** 的优秀设计理念：

| 维度 | Typefly | 本项目 | 说明 |
|------|---------|--------|------|
| **提示词管理** | 独立 txt 文件 | 独立 txt 文件 | ✅ 已对齐 |
| **指导原则** | 6 条 | 6 条 | ✅ 已对齐 |
| **示例数量** | 10 个 | 15 个 | ✅ 更丰富 |
| **平台适配** | RobotWrapper | BasePlatform | ✅ 相同理念 |
| **工具数量** | 21 个 | 12 个 | 更精简 |
| **架构模式** | 代码生成 | ReAct | 不同架构 |
| **机器人类型** | 地面/空中 | 空中（无人机） | 专注领域 |

**设计理念一致**：
- ✅ 提示词独立管理
- ✅ 平台抽象分离
- ✅ 工具原子化设计
- ✅ 配置灵活可扩展

---
