#!/usr/bin/env python3
"""Start the Redbook Config UI frontend."""
import os
import sys
import subprocess
import shutil

# Get the project root directory
project_root = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(project_root, "config-ui", "frontend")

def find_npm():
    """Find npm executable path."""
    # Try to find npm using shutil.which
    npm_path = shutil.which("npm")
    if npm_path:
        return npm_path

    # Try common Windows paths
    common_paths = [
        r"C:\Program Files\nodejs\npm.cmd",
        r"C:\Program Files\nodejs\npm",
        r"C:\Program Files (x86)\nodejs\npm.cmd",
        os.path.expanduser(r"~\AppData\Roaming\npm\npm.cmd"),
    ]

    for path in common_paths:
        if os.path.exists(path):
            return path

    return None

def start_frontend():
    """Start the frontend dev server."""
    print("=" * 50)
    print("启动前端服务器...")
    print("=" * 50)

    # Find npm
    npm_cmd = find_npm()
    if not npm_cmd:
        print("错误: npm 未找到，请确保 Node.js 已安装")
        sys.exit(1)

    # Check npm version
    try:
        result = subprocess.run(
            [npm_cmd, "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"npm 版本: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: npm 无法执行，请检查 Node.js 安装")
        sys.exit(1)

    # Check if port is already in use
    if is_port_in_use(5178):
        print("错误: 端口 5178 已被占用")
        print("请先停止现有服务或更改端口")
        sys.exit(1)

    # Build command - on Windows with shell=True, use string command
    if os.name == 'nt':
        cmd = f'"{npm_cmd}" run dev -- --host'
        creationflags = subprocess.CREATE_NEW_CONSOLE
        process = subprocess.Popen(
            cmd,
            cwd=frontend_dir,
            shell=True,
            creationflags=creationflags
        )
    else:
        cmd = [npm_cmd, "run", "dev", "--", "--host"]
        process = subprocess.Popen(
            cmd,
            cwd=frontend_dir,
            preexec_fn=os.setsid
        )

    print(f"前端服务器已启动 (PID: {process.pid})")
    print(f"前端地址: http://localhost:5178")
    print("")
    print("按 Ctrl+C 停止服务器")

    try:
        process.wait()
    except KeyboardInterrupt:
        print("\n正在停止服务器...")
        process.terminate()
        process.wait()
        print("服务器已停止")


def is_port_in_use(port):
    """Check if a port is in use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

if __name__ == "__main__":
    start_frontend()
