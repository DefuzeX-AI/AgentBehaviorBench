@echo off
REM 一鍵啟動台灣 AI 求職 Co-pilot 伺服器（獨立於 Claude Code 工作階段）。
REM 用法：在檔案總管雙擊本檔，或在一般終端機執行。視窗保持開著即代表伺服器運作中。
cd /d "%~dp0"
echo Starting server at http://localhost:8000  (Ctrl+C to stop)
.venv\Scripts\python.exe -m uvicorn app.server:app --host 127.0.0.1 --port 8000
pause
