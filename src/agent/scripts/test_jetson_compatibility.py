#!/usr/bin/env python3
"""
Jetson NX 兼容性测试脚本

测试所有依赖是否正确安装并兼容 PyTorch 1.13
"""

import sys
import os

# 颜色定义
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_test(name):
    print(f"\n{Colors.BLUE}[TEST]{Colors.END} {name}...", end=" ")

def print_pass():
    print(f"{Colors.GREEN}✓ PASS{Colors.END}")

def print_fail(error):
    print(f"{Colors.RED}✗ FAIL{Colors.END}")
    print(f"  Error: {error}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ WARNING{Colors.END} {msg}")

def print_info(msg):
    print(f"{Colors.BLUE}[INFO]{Colors.END} {msg}")

# ============================================================================
# 测试函数
# ============================================================================

def test_python_version():
    """测试 Python 版本"""
    print_test("Python 版本")
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print_pass()
        print_info(f"  Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_fail(f"需要 Python 3.8+，当前版本: {version.major}.{version.minor}")
        return False

def test_pytorch():
    """测试 PyTorch"""
    print_test("PyTorch")
    try:
        import torch
        version = torch.__version__
        
        # 检查版本
        if not version.startswith('1.13'):
            print_warning(f"期望 PyTorch 1.13.x，当前版本: {version}")
        
        print_pass()
        print_info(f"  版本: {version}")
        print_info(f"  CUDA 可用: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            print_info(f"  CUDA 版本: {torch.version.cuda}")
            print_info(f"  GPU: {torch.cuda.get_device_name(0)}")
            print_info(f"  GPU 内存: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
        
        return True
    except ImportError as e:
        print_fail(str(e))
        return False

def test_torchvision():
    """测试 torchvision"""
    print_test("torchvision")
    try:
        import torchvision
        version = torchvision.__version__
        print_pass()
        print_info(f"  版本: {version}")
        return True
    except ImportError as e:
        print_fail(str(e))
        return False

def test_ultralytics():
    """测试 Ultralytics YOLO"""
    print_test("Ultralytics YOLO")
    try:
        from ultralytics import YOLO
        import ultralytics
        version = ultralytics.__version__
        print_pass()
        print_info(f"  版本: {version}")
        
        # 测试模型加载（如果模型文件存在）
        model_path = os.path.join(os.path.dirname(__file__), '../pth/yolov8l-worldv2.pt')
        if os.path.exists(model_path):
            print_info(f"  模型文件存在: {model_path}")
        else:
            print_warning(f"  模型文件不存在: {model_path}")
        
        return True
    except ImportError as e:
        print_fail(str(e))
        return False
    except Exception as e:
        print_fail(f"YOLO 导入错误: {e}")
        return False

def test_opencv():
    """测试 OpenCV"""
    print_test("OpenCV")
    try:
        import cv2
        version = cv2.__version__
        print_pass()
        print_info(f"  版本: {version}")
        
        # 测试 CUDA 支持
        if cv2.cuda.getCudaEnabledDeviceCount() > 0:
            print_info(f"  CUDA 设备数: {cv2.cuda.getCudaEnabledDeviceCount()}")
        
        return True
    except ImportError as e:
        print_fail(str(e))
        return False
    except Exception:
        # cv2.cuda 可能不可用
        return True

def test_langchain():
    """测试 LangChain"""
    print_test("LangChain")
    try:
        from langchain_openai import ChatOpenAI
        import langchain
        version = langchain.__version__
        print_pass()
        print_info(f"  版本: {version}")
        return True
    except ImportError as e:
        print_fail(str(e))
        return False

def test_openai():
    """测试 OpenAI"""
    print_test("OpenAI")
    try:
        from openai import OpenAI
        import openai
        version = openai.__version__
        print_pass()
        print_info(f"  版本: {version}")
        
        # 检查 API Key
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if api_key:
            print_info(f"  API Key: {'*' * 20}{api_key[-4:]}")
        else:
            print_warning("  未设置 OPENAI_API_KEY 环境变量")
        
        return True
    except ImportError as e:
        print_fail(str(e))
        return False

def test_ros():
    """测试 ROS"""
    print_test("ROS")
    try:
        import rospy
        import cv_bridge
        print_pass()
        print_info("  rospy: ✓")
        print_info("  cv_bridge: ✓")
        return True
    except ImportError as e:
        print_fail(str(e))
        return False

def test_numpy():
    """测试 NumPy"""
    print_test("NumPy")
    try:
        import numpy as np
        version = np.__version__
        print_pass()
        print_info(f"  版本: {version}")
        return True
    except ImportError as e:
        print_fail(str(e))
        return False

def test_performance():
    """测试性能"""
    print_test("GPU 性能测试")
    try:
        import torch
        
        if not torch.cuda.is_available():
            print_warning("CUDA 不可用，跳过性能测试")
            return True
        
        # 简单的矩阵乘法测试
        size = 1000
        device = torch.device('cuda:0')
        
        a = torch.randn(size, size, device=device)
        b = torch.randn(size, size, device=device)
        
        # 预热
        for _ in range(10):
            c = torch.matmul(a, b)
        
        # 计时
        import time
        torch.cuda.synchronize()
        start = time.time()
        
        for _ in range(100):
            c = torch.matmul(a, b)
        
        torch.cuda.synchronize()
        elapsed = time.time() - start
        
        print_pass()
        print_info(f"  矩阵乘法 ({size}x{size}, 100次): {elapsed:.3f}s")
        print_info(f"  平均: {elapsed/100*1000:.2f}ms/次")
        
        return True
    except Exception as e:
        print_fail(str(e))
        return False

# ============================================================================
# 主函数
# ============================================================================

def main():
    print("=" * 70)
    print("  Jetson NX 兼容性测试")
    print("  PyTorch 1.13 | JetPack 5.0")
    print("=" * 70)
    
    tests = [
        ("Python 版本", test_python_version),
        ("PyTorch", test_pytorch),
        ("torchvision", test_torchvision),
        ("NumPy", test_numpy),
        ("OpenCV", test_opencv),
        ("Ultralytics YOLO", test_ultralytics),
        ("LangChain", test_langchain),
        ("OpenAI", test_openai),
        ("ROS", test_ros),
        ("GPU 性能", test_performance),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_fail(f"测试异常: {e}")
            results.append((name, False))
    
    # 总结
    print("\n" + "=" * 70)
    print("  测试总结")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{Colors.GREEN}✓{Colors.END}" if result else f"{Colors.RED}✗{Colors.END}"
        print(f"  {status} {name}")
    
    print("\n" + "=" * 70)
    print(f"  通过: {passed}/{total}")
    
    if passed == total:
        print(f"  {Colors.GREEN}所有测试通过！{Colors.END}")
        print("=" * 70)
        return 0
    else:
        print(f"  {Colors.RED}部分测试失败{Colors.END}")
        print("=" * 70)
        return 1

if __name__ == '__main__':
    sys.exit(main())
