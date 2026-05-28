@echo off
chcp 65001 >nul
echo ================================================
echo 启动小红书 Agent 配置中心
echo ================================================
echo.

cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Python 未安装
    pause
    exit /b 1
)

:: Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Node.js 未安装
    pause
    exit /b 1
)

echo [1/2] 启动后端服务器 (端口 8080)...
start "Redbook Backend" python start_backend.py

echo [2/2] 启动前端服务器 (端口 5173)...
start "Redbook Frontend" python start_frontend.py

echo.
echo ================================================
echo 服务已启动！
echo   后端 API: http://localhost:8080
echo   前端 UI:  http://localhost:5173
echo   API 文档: http://localhost:8080/docs
echo ================================================
echo.
echo 按任意键打开浏览器...
pause >nul
start http://localhost:5173
