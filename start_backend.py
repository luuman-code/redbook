#!/usr/bin/env python3
"""Start the Redbook Config API server."""
import os
import sys
import subprocess
import time
import socket

# Get the project root directory
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)

# Windows process creation flags
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010


def is_port_in_use(port):
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def wait_for_server(host, port, timeout=30):
    """Wait for server to be ready by checking if it responds."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.5)
    return False


def start_server():
    """Start the backend server."""
    print("=" * 50)
    print("启动后端服务器...")
    print("=" * 50)

    # Check if port is already in use
    if is_port_in_use(8080):
        print("错误: 端口 8080 已被占用")
        print("请先停止现有服务或更改端口")
        return

    # Start uvicorn server
    cmd = [
        sys.executable, "-m", "uvicorn",
        "config-ui.backend.main:app",
        "--host", "0.0.0.0",
        "--port", "8080"
    ]

    # Log file path
    log_file = os.path.join(project_root, "backend.log")

    if os.name == 'nt':
        # On Windows, use DETACHED_PROCESS + CREATE_NO_WINDOW to properly detach
        # but also write logs to file for debugging
        creationflags = DETACHED_PROCESS | CREATE_NO_WINDOW

        log_fd = open(log_file, 'w')

        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            creationflags=creationflags,
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=subprocess.STDOUT
        )
    else:
        # On Unix, use nohup to detach
        log_fd = open(log_file, 'w')

        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid
        )

    print(f"进程已启动 (PID: {process.pid})")
    print(f"日志文件: {log_file}")
    print("等待服务启动...")

    # Wait for server to be ready
    if wait_for_server('localhost', 8080, timeout=30):
        print(f"后端服务器已启动 (PID: {process.pid})")
        print(f"API 地址: http://localhost:8080")
        print(f"API 文档: http://localhost:8080/docs")
    else:
        print(f"服务器启动超时!")
        print(f"请检查日志文件: {log_file}")
        if process.poll() is not None:
            print(f"进程已退出，退出码: {process.returncode}")
        else:
            print("进程仍在运行但未响应，可能是端口冲突")
    log_fd.close()


if __name__ == "__main__":
    start_server()
