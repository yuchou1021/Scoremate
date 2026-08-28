@echo off
rem 谱伴 ScoreMate —— 一键启动云端服务（双击运行，关窗口即停止）
cd /d "%~dp0"
echo ================================================
echo  谱伴 ScoreMate 云端服务启动中...
echo  浏览器打开 http://127.0.0.1:8000/api/health 可验证
echo  关闭本窗口即停止服务
echo ================================================
".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000
pause
