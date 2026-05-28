#!/usr/bin/env python3
"""Start the Redbook backend server with visible output for debugging."""
import os
import sys
import subprocess
import time

# Get the project root directory
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)

def start_server():
    """Start the backend server with visible output."""
    print("=" * 50)
    print("启动后端服务器...")
    print("=" * 50)
    print(f"工作目录: {project_root}")
    print(f"Python: {sys.executable}")
    print()

    # First, check if required packages are installed
    print("检查依赖...")
    try:
        import fastapi
        import uvicorn
        import sentry_sdk
        print(f"  fastapi: OK")
        print(f"  uvicorn: OK")
        print(f"  sentry-sdk: OK")
    except ImportError as e:
        print(f"  缺少依赖: {e}")
        print("请运行: pip install -r requirements.txt")
        return
    print()

    # Start uvicorn server
    cmd = [
        sys.executable, "-m", "uvicorn",
        "config-ui.backend.main:app",
        "--host", "0.0.0.0",
        "--port", "8080",
        "--reload"
    ]

    print(f"执行命令: {' '.join(cmd)}")
    print()

    # Use Popen without DEVNULL to see output
    process = subprocess.Popen(
        cmd,
        cwd=project_root,
        stdin=subprocess.DEVNULL
        # Don't redirect stdout/stderr so we can see errors
    )

    print(f"后端服务器启动中 (PID: {process.pid})...")
    print()

    # Wait and check status
    for i in range(10):
        time.sleep(1)
        if process.poll() is not None:
            print(f"服务器启动失败! 退出码: {process.returncode}")
            return
        # Try to connect using liveness endpoint (lighter than /api/health)
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8080/api/live", timeout=1)
            print("服务器启动成功!")
            print(f"API 地址: http://localhost:8080")
            print(f"API 文档: http://localhost:8080/docs")
            return
        except:
            print(f"  等待启动... ({i+1}/10)")
            continue

    print("服务器启动超时，但仍可能正在运行")
    print(f"PID: {process.pid}")


if __name__ == "__main__":
    start_server()
