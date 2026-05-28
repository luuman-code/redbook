#!/usr/bin/env python3
"""Stop all Redbook services by port."""
import subprocess
import re

def get_pid_by_port(port):
    """Get PID listening on a specific port."""
    pids = []
    try:
        result = subprocess.run(
            f'netstat -ano | findstr :{port} | findstr LISTENING',
            shell=True,
            capture_output=True,
            text=True
        )
        for line in result.stdout.strip().split('\n'):
            if f':{port}' in line:
                parts = line.split()
                # Format: TCP    0.0.0.0:8080    0.0.0.0:0    LISTENING    12345
                # PID is always the last element
                if len(parts) >= 5 and parts[-2] == 'LISTENING':
                    pids.append(parts[-1])
        return pids
    except:
        return []

def kill_pid(pid):
    """Kill process by PID."""
    try:
        subprocess.run(['cmd', '/c', 'taskkill', '/F', '/PID', pid],
                      capture_output=True)
        print(f"  Killed PID: {pid}")
    except Exception as e:
        print(f"  Failed to kill {pid}: {e}")

def stop_all():
    """Stop services on ports 8080 and 5173."""
    print("=" * 50)
    print("关闭小红书 Agent 服务 (按端口)")
    print("=" * 50)
    print()

    for port in [8080, 5173]:
        print(f"检查端口 {port}...")
        pids = get_pid_by_port(port)
        if pids:
            for pid in pids:
                print(f"  找到进程 PID: {pid}")
                kill_pid(pid)
        else:
            print(f"  端口 {port} 未被占用")
        print()

    print("=" * 50)
    print("完成")
    print("=" * 50)

if __name__ == "__main__":
    stop_all()
