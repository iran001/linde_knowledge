"""
林德亚太知识库管理平台 - 启动脚本
启动 FastAPI 后端服务
"""

import subprocess
import sys
import time
import os
import signal
import atexit
from datetime import datetime

# 存储子进程
processes = []


def cleanup():
    """清理所有子进程"""
    print("\n正在关闭服务...")
    for process in processes:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except:
                process.kill()
    print("服务已关闭")


def start_backend():
    """启动 FastAPI 后端"""
    cmd = [
        sys.executable, "-m", "uvicorn",
        "backend:app",
        "--host", "0.0.0.0",
        "--port", "80",
        "--reload"
    ]
    # 将输出重定向到 logs 目录下的日期命名文件
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    log_file_path = os.path.join(log_dir, f'backend_{today}.log')
    log_file = open(log_file_path, "a", encoding="utf-8", buffering=1)  # 行缓冲模式
    
    # 设置环境变量，确保 Python 输出无缓冲
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    
    return subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env)


def main():
    """主函数"""
    from config import APP_INFO

    print("=" * 70)
    print(" " * 15 + f"{APP_INFO['name']} - 启动脚本")
    print("=" * 70)
    print()

    # 注册清理函数
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    # 启动后端
    print("正在启动 FastAPI 服务...")
    backend_process = start_backend()
    processes.append(backend_process)
    time.sleep(3)
    print(f"      [OK] 服务已启动: http://localhost")
    print()

    print("-" * 70)
    print("访问地址:")
    print(f"  - 首页:      http://localhost")
    print(f"  - API文档:   http://localhost/docs")
    print(f"  - ReDoc:     http://localhost/redoc")
    print("-" * 70)
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 70)

    # 等待进程结束
    try:
        while True:
            time.sleep(1)
            if backend_process.poll() is not None:
                print(f"\n后端进程已退出 (返回码: {backend_process.returncode})")
                return
    except KeyboardInterrupt:
        print("\n收到中断信号，正在关闭...")


if __name__ == "__main__":
    main()
