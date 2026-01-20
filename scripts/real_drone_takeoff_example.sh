#!/bin/bash
# 真机起飞脚本示例
# 用法: ./real_drone_takeoff_example.sh <height>

HEIGHT=${1:-1.5}

echo "=========================================="
echo "真机起飞脚本"
echo "目标高度: ${HEIGHT}m"
echo "=========================================="

# 检查高度参数
if ! [[ "$HEIGHT" =~ ^[0-9]+\.?[0-9]*$ ]]; then
    echo "错误: 高度参数无效 '$HEIGHT'" >&2
    exit 1
fi

if (( $(echo "$HEIGHT < 0.5" | bc -l) )) || (( $(echo "$HEIGHT > 20.0" | bc -l) )); then
    echo "错误: 高度超出范围 (0.5-20.0m)" >&2
    exit 1
fi

# 方案1: 使用mavros服务（PX4/ArduPilot）
if rosservice list | grep -q "/mavros/cmd/takeoff"; then
    echo "使用mavros起飞..."
    rosservice call /mavros/cmd/takeoff "{min_pitch: 0.0, yaw: 0.0, latitude: 0.0, longitude: 0.0, altitude: $HEIGHT}"
    
    if [ $? -eq 0 ]; then
        echo "✅ 起飞命令发送成功"
        
        # 等待起飞完成（可选）
        echo "等待起飞到目标高度..."
        sleep 5
        
        echo "✅ 起飞成功"
        exit 0
    else
        echo "❌ 起飞命令失败" >&2
        exit 1
    fi
fi

# 方案2: 发布到自定义话题
if rostopic list | grep -q "/drone/takeoff"; then
    echo "使用自定义话题起飞..."
    rostopic pub -1 /drone/takeoff std_msgs/Float64 "data: $HEIGHT"
    
    if [ $? -eq 0 ]; then
        echo "✅ 起飞成功"
        exit 0
    else
        echo "❌ 起飞失败" >&2
        exit 1
    fi
fi

# 方案3: 调用自定义程序
# if [ -x "/path/to/drone_control" ]; then
#     /path/to/drone_control takeoff $HEIGHT
#     exit $?
# fi

echo "❌ 未找到可用的起飞接口" >&2
echo "请根据实际硬件修改此脚本" >&2
exit 1
