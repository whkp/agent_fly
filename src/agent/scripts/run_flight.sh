#!/bin/bash
# 飞行系统启动脚本 (Non-PX4 仿真器)
# 
# 使用方法:
#   ./run_flight.sh           # 启动完整导航系统
#   ./run_flight.sh takeoff   # 仅启动起飞悬停
#   ./run_flight.sh sim       # 仅启动仿真环境
#   ./run_flight.sh agent     # 仅启动 Agent 节点

MODE=${1:-"full"}

case $MODE in
    "full")
        echo "🚀 启动完整导航系统..."
        roslaunch agent flight.launch
        ;;
    "takeoff")
        echo "🚁 启动起飞悬停..."
        roslaunch agent takeoff.launch
        ;;
    "sim")
        echo "🌍 启动仿真环境..."
        roslaunch uav_simulator start.launch
        ;;
    "agent")
        echo "🤖 启动 Agent 节点..."
        rosrun agent agent.py
        ;;
    *)
        echo "用法: $0 [full|takeoff|sim|agent]"
        echo "  full    - 启动完整导航系统 (默认)"
        echo "  takeoff - 仅启动起飞悬停"
        echo "  sim     - 仅启动仿真环境"
        echo "  agent   - 仅启动 Agent 节点"
        exit 1
        ;;
esac
