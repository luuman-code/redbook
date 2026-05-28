#!/usr/bin/env python3
"""Stop all Redbook services (backend on port 8080, frontend on port 5173)."""
import os
import subprocess
import re


def find_processes_by_port(port):
    """Find process IDs listening on the specified port."""
    pids = []
    if os.name == 'nt':
        try:
            result = subprocess.run(
                f'netstat -ano | findstr :{port} | findstr LISTENING',
                shell=True,
                capture_output=True,
                text=True
            )
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                # Parse netstat output: Proto Local Address Foreign Address State PID
                parts = line.split()
                if len(parts) >= 5 and parts[3] == 'LISTENING':
                    pid = parts[4]
                    if pid.isdigit():
                        pids.append(pid)
        except Exception as e:
            print(f"  查找端口 {port} 进程时出错: {e}")
    else:
        # Unix/Linux/Mac
        try:
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True,
                text=True
            )
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.isdigit():
                    pids.append(line)
        except Exception as e:
            # Fallback: try fuser
            try:
                result = subprocess.run(
                    ['fuser', f'{port}/tcp'],
                    capture_output=True,
                    text=True
                )
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line.isdigit():
                        pids.append(line)
            except Exception as e2:
                print(f"  查找端口 {port} 进程时出错: {e2}")
    return list(set(pids))  # Remove duplicates


def kill_process(pid):
    """Kill a process by PID."""
    if os.name == 'nt':
        subprocess.run(['cmd', '/c', 'taskkill', '/F', '/PID', pid],
                      capture_output=True)
    else:
        subprocess.run(['kill', '-9', pid], capture_output=True)


def stop_all():
    """Stop both backend and frontend servers."""
    print("=" * 50)
    print("关闭小红书 Agent 服务")
    print("=" * 50)
    print()

    # Stop backend (port 8080)
    print("正在关闭后端服务器 (端口 8080)...")
    backend_pids = find_processes_by_port(8080)
    if backend_pids:
        for pid in backend_pids:
            print(f"  终止后端进程 PID: {pid}")
            kill_process(pid)
    else:
        print("  未找到后端进程或端口未被占用")

    # Stop frontend (port 5173)
    print("正在关闭前端服务器 (端口 5173)...")
    frontend_pids = find_processes_by_port(5173)
    if frontend_pids:
        for pid in frontend_pids:
            print(f"  终止前端进程 PID: {pid}")
            kill_process(pid)
    else:
        print("  未找到前端进程或端口未被占用")

    print()
    print("=" * 50)
    print("所有服务已关闭")
    print("=" * 50)


if __name__ == "__main__":
    stop_all()
