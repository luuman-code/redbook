#!/usr/bin/env python3
"""Start all Redbook services (backend and frontend)."""
import os
import sys
import subprocess
import time
import webbrowser

# Get the project root directory
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)

# Windows process creation flags
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010


def start_all():
    """Start both backend and frontend servers."""
    print("=" * 50)
    print("启动小红书 Agent 配置中心")
    print("=" * 50)
    print()

    # First stop any existing servers
    print("正在关闭现有服务器...")
    result = subprocess.run([sys.executable, "stop_all.py"], capture_output=True)
    time.sleep(2)

    # Check if ports are still in use, if so wait a bit more
    for port in [8080, 5173]:
        result = subprocess.run(
            f'netstat -ano | findstr :{port} | findstr LISTENING',
            shell=True,
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            print(f"  端口 {port} 仍在占用，等待...")
            time.sleep(3)
    print()

    if os.name == 'nt':
        backend_creationflags = DETACHED_PROCESS | CREATE_NO_WINDOW
        frontend_creationflags = CREATE_NEW_CONSOLE
    else:
        backend_creationflags = 0
        frontend_creationflags = 0

    # Start backend
    print("[1/2] 启动后端服务器 (端口 8080)...")
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "config-ui.backend.main:app",
        "--host", "0.0.0.0",
        "--port", "8080",
        "--reload"
    ]
    backend_process = subprocess.Popen(
        backend_cmd,
        cwd=project_root,
        creationflags=backend_creationflags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print(f"  后端进程 PID: {backend_process.pid}")
    print("  API 地址: http://localhost:8080")
    print()

    # Wait for backend to start
    time.sleep(3)

    # Start frontend
    print("[2/2] 启动前端服务器 (端口 5173)...")
    if os.name == 'nt':
        # Windows: use cmd /c to run npm command, show new console window
        import shutil
        npm_path = shutil.which("npm") or os.path.join(os.environ.get("ProgramFiles", ""), "nodejs", "npm.cmd")
        frontend_cmd = [npm_path, "run", "dev", "--", "--host"]
        frontend_process = subprocess.Popen(
            frontend_cmd,
            cwd=os.path.join(project_root, "config-ui", "frontend"),
            creationflags=frontend_creationflags,
            stdin=subprocess.DEVNULL,
            shell=True
        )
    else:
        frontend_cmd = ["npm", "run", "dev", "--", "--host"]
        frontend_process = subprocess.Popen(
            frontend_cmd,
            cwd=os.path.join(project_root, "config-ui", "frontend"),
            creationflags=frontend_creationflags
        )
    print(f"  前端进程 PID: {frontend_process.pid}")
    print("  前端地址: http://localhost:5173")
    print()

    # Wait for frontend to start
    time.sleep(3)

    print("=" * 50)
    print("所有服务已启动！")
    print("  后端 API: http://localhost:8080")
    print("  前端 UI:  http://localhost:5173")
    print("=" * 50)
    print()

    # Open browser
    webbrowser.open("http://localhost:5173")

    print("按 Ctrl+C 停止所有服务")
    print()

    try:
        while True:
            # Check if processes are still running
            if backend_process.poll() is not None:
                print("后端服务器意外退出")
                break
            if frontend_process.poll() is not None:
                print("前端服务器意外退出")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止所有服务...")
        # Use stop_all.py for clean shutdown
        subprocess.run([sys.executable, "stop_all.py"])
        print("所有服务已停止")

if __name__ == "__main__":
    start_all()
