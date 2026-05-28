#!/usr/bin/env python3
"""Stop the Redbook Config API server."""
import os
import subprocess
import re


def find_uvicorn_processes():
    """Find uvicorn process IDs using WMIC."""
    pids = []
    if os.name == 'nt':
        try:
            result = subprocess.run(
                'wmic process where "name=\'python.exe\'" get ProcessId,CommandLine',
                shell=True,
                capture_output=True,
                text=True
            )
            for line in result.stdout.split('\n'):
                if 'uvicorn' in line:
                    match = re.search(r'(\d+)\s*$', line.strip())
                    if match:
                        pids.append(match.group(1))
        except Exception as e:
            print(f"查找进程时出错: {e}")
    else:
        # Unix/Linux/Mac
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True
            )
            for line in result.stdout.split('\n'):
                if 'uvicorn' in line and 'grep' not in line:
                    parts = line.split()
                    for part in parts:
                        if part.isdigit():
                            pids.append(part)
                            break
        except Exception as e:
            print(f"查找进程时出错: {e}")
    return pids


def kill_process(pid):
    """Kill a process by PID."""
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'taskkill', '/F', '/PID', pid],
                      capture_output=True)
    else:
        subprocess.run(['kill', '-9', pid], capture_output=True)


def stop_backend():
    """Stop the backend server by finding uvicorn processes."""
    print("正在关闭后端服务器...")

    pids = find_uvicorn_processes()
    if pids:
        for pid in pids:
            print(f"终止进程 PID: {pid}")
            kill_process(pid)
        print("后端服务器已关闭")
    else:
        print("未找到后端服务器进程 (uvicorn)")


if __name__ == "__main__":
    stop_backend()
