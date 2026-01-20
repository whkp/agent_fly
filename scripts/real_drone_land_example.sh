#!/bin/bash
# 真机降落脚本示例
# 用法: ./real_drone_land_example.sh

echo "=========================================="
echo "真机降落脚本"
echo "=========================================="

# 方案1: 使用mavros服务（PX4/ArduPilot）
if rosservice list | grep -q "/mavros/cmd/land"; then
    echo "使用mavros降落..."
    rosservice call /mavros/cmd/land "{min_pitch: 0.0, yaw: 0.0, latitude: 0.0, longitude: 0.0, altitude: 0.0}"
    
    if [ $? -eq 0 ]; then
        echo "✅ 降落命令发送成功"
        
        # 等待降落完成（可选）
        echo "等待降落..."
        sleep 10
        
        echo "✅ 降落成功"
        exit 0
    else
        echo "❌ 降落命令失败" >&2
        exit 1
    fi
fi

# 方案2: 发布到自定义话题
if rostopic list | grep -q "/drone/land"; then
    echo "使用自定义话题降落..."
    rostopic pub -1 /drone/land std_msgs/Empty "{}"
    
    if [ $? -eq 0 ]; then
        echo "✅ 降落成功"
        exit 0
    else
        echo "❌ 降落失败" >&2
        exit 1
    fi
fi

# 方案3: 调用自定义程序
# if [ -x "/path/to/drone_control" ]; then
#     /path/to/drone_control land
#     exit $?
# fi

echo "❌ 未找到可用的降落接口" >&2
echo "请根据实际硬件修改此脚本" >&2
exit 1
