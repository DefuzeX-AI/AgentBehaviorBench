@echo off
REM 桌面 App：雙擊本檔，會開一個原生視窗跑台灣 AI 求職 Co-pilot（不用開瀏覽器）。
REM 第一次使用前請先建置前端：cd frontend ^&^& npm run build
cd /d "%~dp0"
.venv\Scripts\python.exe desktop.py
if errorlevel 1 pause
