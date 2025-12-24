#!/bin/bash
# 启动Agent CLI 控制面板

set -e

echo "=========================================="
echo "启动 Agent UAV CLI 控制面板"
echo "=========================================="

# 检查必要的环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到Python3"
    exit 1
fi

# 激活ROS环境
if [ -z "$ROS_DISTRO" ]; then
    echo "⚠️ 加载ROS环境..."
    source /opt/ros/noetic/setup.bash 2>/dev/null || true
fi

# 自动查找并source工作空间
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
if [ -f "$WS_DIR/devel/setup.bash" ]; then
    source "$WS_DIR/devel/setup.bash"
fi

echo ""
echo "✅ 环境已就绪"
echo "📌 Python: $(which python3)"
echo "📌 ROS: $ROS_DISTRO"
echo ""
echo "=========================================="
echo "🚀 启动CLI控制面板..."
echo "=========================================="
echo ""

# 启动CLI应用
rosrun agent agent_cli.py

