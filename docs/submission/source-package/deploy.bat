@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==== 乡艺有据：首次部署 ====
where py >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 Python 启动器 py。请先安装 Python 3.12（64 位），安装时勾选 "Add python.exe to PATH" 与 "py launcher"。
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 创建 Python 3.12 虚拟环境 .venv
  py -3.12 -m venv .venv
  if errorlevel 1 goto :fail
)
echo [2/3] 安装 Python 依赖（requirements-lock.txt）
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 goto :fail
echo [3/3] 下载并校验推理运行时与本地大模型（约 10 GB，支持断点续传）
".venv\Scripts\python.exe" scripts\setup_local.py
if errorlevel 1 goto :fail
echo.
echo 部署完成。请双击“启动.bat”启动系统。
pause
exit /b 0
:fail
echo.
echo [错误] 部署未完成，请根据上方提示处理后重新运行本文件；已下载的部分会自动续传。
pause
exit /b 1
