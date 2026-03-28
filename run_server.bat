@echo off
cd /d C:\Users\Thinkpad\Desktop\IHG-POC\knowledge_poc
python -m uvicorn backend:app --host 0.0.0.0 --port 8000 --reload
