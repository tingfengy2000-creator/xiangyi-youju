@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 无需安装任何环境：用浏览器打开界面原型（预设案例，明确标注，不调用本地模型）
start "" "%~dp0frontend\prototype\index.html"
