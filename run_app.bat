@echo off
cd /d C:\Users\Thinkpad\Desktop\IHG-POC\knowledge_poc
echo 启动 IHG 智能问答平台...
echo.
python -m uvicorn backend:app --host 0.0.0.0 --port 8000 --reload
pause
