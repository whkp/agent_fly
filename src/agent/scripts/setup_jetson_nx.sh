#!/bin/bash

# ============================================================================
# Jetson Xavier NX 环境安装脚本
# ============================================================================
# 
# 适用于：Jetson Xavier NX with JetPack 5.0
# PyTorch: 1.13.0
# Python: 3.8
# CUDA: 11.4
# 
# 使用方法：
#   chmod +x setup_jetson_nx.sh
#   ./setup_jetson_nx.sh
# 
# ============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

echo ""
echo "============================================================================"
echo "  Jetson Xavier NX 环境安装"
echo "  JetPack 5.0 | PyTorch 1.13 | Python 3.8"
echo "============================================================================"
echo ""

# 检查是否在 Jetson 设备上
if [ ! -f /etc/nv_tegra_release ]; then
    print_error "此脚本仅适用于 Jetson 设备"
    exit 1
fi

print_info "检测到 Jetson 设备"
cat /etc/nv_tegra_release
echo ""

# ============================================================================
# 1. 系统更新
# ============================================================================

print_info "步骤 1/8: 更新系统包"
sudo apt-get update
sudo apt-get upgrade -y

# ============================================================================
# 2. 安装系统依赖
# ============================================================================

print_info "步骤 2/8: 安装系统依赖"
sudo apt-get install -y \
    python3-pip \
    python3-dev \
    python3-opencv \
    libopencv-dev \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    libhdf5-serial-dev \
    hdf5-tools \
    libhdf5-dev \
    zlib1g-dev \
    zip \
    libjpeg8-dev \
    liblapack-dev \
    libblas-dev \
    gfortran

print_success "系统依赖安装完成"

# ============================================================================
# 3. 升级 pip
# ============================================================================

print_info "步骤 3/8: 升级 pip"
python3 -m pip install --upgrade pip
export PATH=$HOME/.local/bin:$PATH

print_success "pip 升级完成"

# ============================================================================
# 4. 安装 PyTorch 1.13 (预编译版本)
# ============================================================================

print_info "步骤 4/8: 安装 PyTorch 1.13.0"

# 检查是否已安装
if python3 -c "import torch; print(torch.__version__)" 2>/dev/null | grep -q "1.13"; then
    print_warning "PyTorch 1.13 已安装，跳过"
else
    print_info "下载 PyTorch 1.13.0 for JetPack 5.0..."
    
    # 下载预编译的 wheel 文件
    TORCH_WHL="torch-1.13.0a0+d0d6b1f2.nv22.09-cp38-cp38-linux_aarch64.whl"
    TORCH_URL="https://developer.download.nvidia.cn/compute/redist/jp/v50/pytorch/${TORCH_WHL}"
    
    if [ ! -f "/tmp/${TORCH_WHL}" ]; then
        wget -O /tmp/${TORCH_WHL} ${TORCH_URL} || {
            print_error "下载失败，请手动下载："
            echo "  ${TORCH_URL}"
            exit 1
        }
    fi
    
    print_info "安装 PyTorch..."
    python3 -m pip install /tmp/${TORCH_WHL}
    
    # 验证安装
    if python3 -c "import torch; print(f'PyTorch {torch.__version__} installed'); print(f'CUDA available: {torch.cuda.is_available()}')"; then
        print_success "PyTorch 1.13.0 安装成功"
    else
        print_error "PyTorch 安装失败"
        exit 1
    fi
fi

# ============================================================================
# 5. 安装 torchvision (兼容 PyTorch 1.13)
# ============================================================================

print_info "步骤 5/8: 安装 torchvision"

if python3 -c "import torchvision" 2>/dev/null; then
    print_warning "torchvision 已安装，跳过"
else
    print_info "从源码编译 torchvision 0.14.0..."
    
    cd /tmp
    if [ ! -d "vision" ]; then
        git clone --branch v0.14.0 https://github.com/pytorch/vision torchvision
    fi
    cd torchvision
    
    export BUILD_VERSION=0.14.0
    python3 setup.py install --user
    
    cd ~
    print_success "torchvision 安装完成"
fi

# ============================================================================
# 6. 安装 Ultralytics YOLO (兼容 PyTorch 1.13)
# ============================================================================

print_info "步骤 6/8: 安装 Ultralytics YOLO"

# 安装兼容版本的依赖
python3 -m pip install --user \
    numpy==1.23.5 \
    opencv-python==4.6.0.66 \
    pillow==9.3.0 \
    pyyaml==6.0 \
    requests==2.28.1 \
    scipy==1.9.3 \
    tqdm==4.64.1 \
    pandas==1.5.2 \
    seaborn==0.12.1

# 安装 ultralytics (8.0.x 版本兼容 PyTorch 1.13)
python3 -m pip install --user ultralytics==8.0.196

print_success "Ultralytics YOLO 安装完成"

# ============================================================================
# 7. 安装 LangChain 和 OpenAI
# ============================================================================

print_info "步骤 7/8: 安装 LangChain 和 OpenAI"

python3 -m pip install --user \
    langchain==0.0.350 \
    langchain-openai==0.0.2 \
    openai==1.3.7 \
    pydantic==1.10.13 \
    typing-extensions==4.8.0

print_success "LangChain 和 OpenAI 安装完成"

# ============================================================================
# 8. 安装 ROS 相关依赖
# ============================================================================

print_info "步骤 8/8: 安装 ROS Python 依赖"

python3 -m pip install --user \
    rospkg \
    catkin_pkg \
    empy

# 安装 cv_bridge 依赖
sudo apt-get install -y \
    ros-noetic-cv-bridge \
    ros-noetic-vision-opencv

print_success "ROS 依赖安装完成"

# ============================================================================
# 验证安装
# ============================================================================

echo ""
echo "============================================================================"
echo "  验证安装"
echo "============================================================================"
echo ""

print_info "验证 PyTorch..."
python3 << EOF
import torch
print(f"✓ PyTorch version: {torch.__version__}")
print(f"✓ CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"✓ CUDA version: {torch.version.cuda}")
    print(f"✓ GPU: {torch.cuda.get_device_name(0)}")
EOF

print_info "验证 torchvision..."
python3 -c "import torchvision; print(f'✓ torchvision version: {torchvision.__version__}')"

print_info "验证 Ultralytics..."
python3 -c "from ultralytics import YOLO; print('✓ Ultralytics YOLO imported successfully')"

print_info "验证 LangChain..."
python3 -c "from langchain_openai import ChatOpenAI; print('✓ LangChain imported successfully')"

print_info "验证 OpenAI..."
python3 -c "from openai import OpenAI; print('✓ OpenAI imported successfully')"

# ============================================================================
# 性能优化建议
# ============================================================================

echo ""
echo "============================================================================"
echo "  性能优化建议"
echo "============================================================================"
echo ""

print_info "1. 设置 Jetson 为最大性能模式："
echo "   sudo nvpmodel -m 0"
echo "   sudo jetson_clocks"
echo ""

print_info "2. 监控系统资源："
echo "   sudo tegrastats"
echo ""

print_info "3. 检查 CUDA 状态："
echo "   nvidia-smi"
echo ""

# ============================================================================
# 环境变量配置
# ============================================================================

print_info "配置环境变量..."

BASHRC_FILE="$HOME/.bashrc"

# 移除旧配置
sed -i '/# Agent Environment Variables/,/# End Agent Environment Variables/d' $BASHRC_FILE

# 添加新配置
cat >> $BASHRC_FILE << 'EOF'

# Agent Environment Variables
export PATH=$HOME/.local/bin:$PATH
export PYTHONPATH=$HOME/.local/lib/python3.8/site-packages:$PYTHONPATH

# OpenCV 使用系统版本（避免冲突）
export OPENBLAS_CORETYPE=ARMV8

# CUDA 优化
export CUDA_CACHE_MAXSIZE=2147483648
export CUDA_CACHE_PATH=$HOME/.nv/ComputeCache

# End Agent Environment Variables
EOF

print_success "环境变量配置完成"

# ============================================================================
# 下载 YOLO 模型
# ============================================================================

echo ""
print_info "下载 YOLO 模型..."

AGENT_DIR="$HOME/Documents/agent_ws/src/agent"
MODEL_DIR="${AGENT_DIR}/pth"

if [ -d "$AGENT_DIR" ]; then
    mkdir -p "$MODEL_DIR"
    
    if [ ! -f "${MODEL_DIR}/yolov8l-worldv2.pt" ]; then
        print_info "下载 YOLOv8-World 模型..."
        cd "$MODEL_DIR"
        wget https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8l-worldv2.pt || {
            print_warning "模型下载失败，请手动下载到 ${MODEL_DIR}"
        }
        print_success "模型下载完成"
    else
        print_warning "模型已存在，跳过下载"
    fi
else
    print_warning "Agent 目录不存在: ${AGENT_DIR}"
    print_info "请在安装 Agent 后手动下载模型"
fi

# ============================================================================
# 完成
# ============================================================================

echo ""
echo "============================================================================"
echo "  安装完成！"
echo "============================================================================"
echo ""

print_success "所有依赖已安装完成"
echo ""

print_info "下一步："
echo ""
echo "1. 使环境变量生效："
echo "   source ~/.bashrc"
echo ""
echo "2. 设置最大性能模式："
echo "   sudo nvpmodel -m 0"
echo "   sudo jetson_clocks"
echo ""
echo "3. 测试安装："
echo "   python3 -c 'import torch; print(torch.cuda.is_available())'"
echo "   python3 -c 'from ultralytics import YOLO'"
echo ""
echo "4. 启动 Agent："
echo "   roslaunch agent agent_onboard.launch"
echo ""

print_warning "注意：首次运行 YOLO 会下载额外的依赖，需要一些时间"
echo ""
