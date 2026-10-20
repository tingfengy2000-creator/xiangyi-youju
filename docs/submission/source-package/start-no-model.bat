@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==== 乡艺有据：免模型启动（只启动业务服务，不启动本地大模型）====
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [错误] 未找到 Python 启动器 py。请先安装 Python 3.12（64 位），安装时勾选 "Add python.exe to PATH" 与 "py launcher"。
    pause
    exit /b 1
  )
  echo [1/2] 创建 Python 3.12 虚拟环境 .venv
  py -3.12 -m venv .venv
  if errorlevel 1 goto :fail
)
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, httpx, langgraph, jieba, rank_bm25" >nul 2>nul
if errorlevel 1 (
  echo [2/2] 安装 Python 依赖（requirements-lock.txt，不下载大模型）
  ".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
  if errorlevel 1 goto :fail
) else (
  echo [2/2] Python 依赖已就绪
)
echo.
echo 业务服务启动后浏览器将打开 http://127.0.0.1:8780/ ，关闭本窗口即停止服务。
echo 本模式不启动本地大模型：界面顶部显示“本地模型尚未就绪”，需要模型的操作会如实提示模型不可用。
start "" cmd /c "timeout /t 6 >nul & start http://127.0.0.1:8780/"
".venv\Scripts\python.exe" scripts\start_local.py --api-only
pause
exit /b 0
:fail
echo.
echo [错误] 环境准备未完成，请检查网络后重新运行本文件。
pause
exit /b 1
