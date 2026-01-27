#!/bin/bash

# ============================================================================
# ROS 多机网络配置脚本
# ============================================================================
# 
# 用途：配置机载计算机和地面站之间的 ROS 通信
# 
# 使用方法：
#   1. 机载计算机（作为 ROS Master）： 本机IP地址
#      ./setup_ros_network.sh onboard 192.168.1.100
#   
#   2. 地面站： 本机IP地址，Master IP地址
#      ./setup_ros_network.sh groundstation 192.168.1.200 192.168.1.100
# 
# 参数说明：
#   $1: 角色 (onboard/groundstation)
#   $2: 本机IP地址
#   $3: Master IP地址（仅地面站需要）
# 
# ============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查参数
if [ $# -lt 2 ]; then
    print_error "参数不足"
    echo ""
    echo "使用方法："
    echo "  机载计算机: $0 onboard <本机IP>"
    echo "  地面站:     $0 groundstation <本机IP> <Master IP>"
    echo ""
    echo "示例："
    echo "  机载计算机: $0 onboard 192.168.1.100"
    echo "  地面站:     $0 groundstation 192.168.1.200 192.168.1.100"
    exit 1
fi

ROLE=$1
LOCAL_IP=$2

# 验证IP格式
if ! [[ $LOCAL_IP =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
    print_error "无效的IP地址格式: $LOCAL_IP"
    exit 1
fi

echo ""
echo "============================================================================"
echo "  ROS 多机网络配置"
echo "============================================================================"
echo ""

# 配置机载计算机
if [ "$ROLE" == "onboard" ]; then
    print_info "配置机载计算机（ROS Master）"
    print_info "本机IP: $LOCAL_IP"
    
    MASTER_URI="http://${LOCAL_IP}:11311"
    
    # 设置环境变量
    export ROS_MASTER_URI=$MASTER_URI
    export ROS_IP=$LOCAL_IP
    export ROS_HOSTNAME=$LOCAL_IP
    
    # 写入 bashrc
    BASHRC_FILE="$HOME/.bashrc"
    
    # 移除旧配置
    sed -i '/# ROS Multi-Machine Config/,/# End ROS Multi-Machine Config/d' $BASHRC_FILE
    
    # 添加新配置
    cat >> $BASHRC_FILE << EOF

# ROS Multi-Machine Config (Onboard)
export ROS_MASTER_URI=$MASTER_URI
export ROS_IP=$LOCAL_IP
export ROS_HOSTNAME=$LOCAL_IP
# End ROS Multi-Machine Config
EOF
    
    print_success "机载计算机配置完成"
    echo ""
    print_info "环境变量已设置："
    echo "  ROS_MASTER_URI = $MASTER_URI"
    echo "  ROS_IP         = $LOCAL_IP"
    echo "  ROS_HOSTNAME   = $LOCAL_IP"
    echo ""
    print_warning "请运行以下命令使配置生效："
    echo "  source ~/.bashrc"
    echo ""
    print_info "或者在新终端中运行"

# 配置地面站
elif [ "$ROLE" == "groundstation" ]; then
    if [ $# -lt 3 ]; then
        print_error "地面站配置需要 Master IP 参数"
        echo "使用方法: $0 groundstation <本机IP> <Master IP>"
        exit 1
    fi
    
    MASTER_IP=$3
    
    # 验证Master IP格式
    if ! [[ $MASTER_IP =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        print_error "无效的Master IP地址格式: $MASTER_IP"
        exit 1
    fi
    
    print_info "配置地面站"
    print_info "本机IP:   $LOCAL_IP"
    print_info "Master IP: $MASTER_IP"
    
    MASTER_URI="http://${MASTER_IP}:11311"
    
    # 设置环境变量
    export ROS_MASTER_URI=$MASTER_URI
    export ROS_IP=$LOCAL_IP
    export ROS_HOSTNAME=$LOCAL_IP
    
    # 写入 bashrc
    BASHRC_FILE="$HOME/.bashrc"
    
    # 移除旧配置
    sed -i '/# ROS Multi-Machine Config/,/# End ROS Multi-Machine Config/d' $BASHRC_FILE
    
    # 添加新配置
    cat >> $BASHRC_FILE << EOF

# ROS Multi-Machine Config (Ground Station)
export ROS_MASTER_URI=$MASTER_URI
export ROS_IP=$LOCAL_IP
export ROS_HOSTNAME=$LOCAL_IP
# End ROS Multi-Machine Config
EOF
    
    print_success "地面站配置完成"
    echo ""
    print_info "环境变量已设置："
    echo "  ROS_MASTER_URI = $MASTER_URI"
    echo "  ROS_IP         = $LOCAL_IP"
    echo "  ROS_HOSTNAME   = $LOCAL_IP"
    echo ""
    print_warning "请运行以下命令使配置生效："
    echo "  source ~/.bashrc"
    echo ""
    print_info "或者在新终端中运行"
    
    # 测试连接
    echo ""
    print_info "测试与 Master 的连接..."
    if ping -c 1 -W 2 $MASTER_IP > /dev/null 2>&1; then
        print_success "可以 ping 通 Master ($MASTER_IP)"
    else
        print_warning "无法 ping 通 Master ($MASTER_IP)"
        print_warning "请检查网络连接"
    fi

else
    print_error "未知角色: $ROLE"
    echo "支持的角色: onboard, groundstation"
    exit 1
fi

echo ""
echo "============================================================================"
echo "  配置完成"
echo "============================================================================"
echo ""
print_info "下一步："
echo ""

if [ "$ROLE" == "onboard" ]; then
    echo "1. 使配置生效："
    echo "   source ~/.bashrc"
    echo ""
    echo "2. 启动 ROS Master（如果还未启动）："
    echo "   roscore"
    echo ""
    echo "3. 启动机载系统："
    echo "   roslaunch mavros px4.launch"
    echo "   roslaunch vins vins_rviz.launch"
    echo "   roslaunch px4ctrl run_ctrl.launch"
    echo "   roslaunch agent agent_onboard.launch"
    echo ""
    echo "4. 在地面站运行配置脚本："
    echo "   ./setup_ros_network.sh groundstation <地面站IP> $LOCAL_IP"
else
    echo "1. 使配置生效："
    echo "   source ~/.bashrc"
    echo ""
    echo "2. 测试连接："
    echo "   rostopic list"
    echo ""
    echo "3. 启动地面站视觉处理："
    echo "   roslaunch agent vision_groundstation.launch"
    echo ""
    echo "4. 启动控制界面（可选）："
    echo "   rosrun agent agent_cli.py"
fi

echo ""
print_info "网络诊断命令："
echo "  查看话题:     rostopic list"
echo "  查看节点:     rosnode list"
echo "  测试延迟:     rostopic hz /camera/color/image_raw"
echo "  查看带宽:     rostopic bw /camera/color/image_raw"
echo ""
