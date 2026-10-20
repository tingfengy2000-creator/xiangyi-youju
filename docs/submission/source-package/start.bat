@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [错误] 尚未部署，请先双击“部署.bat”。
  pause
  exit /b 1
)
echo ==== 乡艺有据：启动本地系统 ====
echo 启动后浏览器将打开 http://127.0.0.1:8780/ ，关闭本窗口即停止服务。
start "" cmd /c "timeout /t 12 >nul & start http://127.0.0.1:8780/"
".venv\Scripts\python.exe" scripts\start_local.py
pause
