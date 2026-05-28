#!/usr/bin/env python3
"""Stop the Redbook Config UI frontend."""
import os
import subprocess

def stop_frontend():
    """Stop the frontend server using port 5178."""
    print("正在关闭前端服务器 (端口 5178)...")

    if os.name == 'nt':
        # Windows
        try:
            result = subprocess.run(
                f'netstat -ano | findstr :5178',
                shell=True,
                capture_output=True,
                text=True
            )
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'LISTENING' in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == 'LISTENING' and i > 0:
                            pid = parts[i + 1]
                            print(f"终止进程 PID: {pid}")
                            subprocess.run(f'taskkill /F /PID {pid}', shell=True)
                            print("前端服务器已关闭")
                            return
            print("未找到在端口 5178 上运行的进程")
        except Exception as e:
            print(f"错误: {e}")
    else:
        # Unix/Linux/Mac
        try:
            result = subprocess.run(
                f'lsof -ti:5178',
                shell=True,
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                pid = result.stdout.strip()
                print(f"终止进程 PID: {pid}")
                subprocess.run(['kill', '-9', pid], shell=False)
                print("前端服务器已关闭")
            else:
                print("未找到在端口 5178 上运行的进程")
        except Exception as e:
            print(f"错误: {e}")

if __name__ == "__main__":
    stop_frontend()
