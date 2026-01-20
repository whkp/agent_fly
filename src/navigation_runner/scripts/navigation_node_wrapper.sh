#!/bin/bash
# Navigation Node Wrapper - 在 NavRL 环境中启动导航节点

# 清理冲突的 Python 路径（移除 my_ws）
if [ -n "$PYTHONPATH" ]; then
    export PYTHONPATH=$(echo $PYTHONPATH | tr ':' '\n' | grep -v 'my_ws' | tr '\n' ':' | sed 's/:$//')
fi

# 清理冲突的 ROS 包路径（移除 my_ws）
if [ -n "$ROS_PACKAGE_PATH" ]; then
    export ROS_PACKAGE_PATH=$(echo $ROS_PACKAGE_PATH | tr ':' '\n' | grep -v 'my_ws' | tr '\n' ':' | sed 's/:$//')
fi

# 激活 NavRL conda 环境
eval "$(conda shell.bash hook)"
conda activate NavRL

# 执行 navigation_node.py，传递所有参数
exec python3 "$(dirname "$0")/navigation_node.py" "$@"
