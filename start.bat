@echo off
chcp 65001 >nul
echo ==========================================
echo   林德亚太知识库管理平台 - 统一启动脚本
echo ==========================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python
    exit /b 1
)

echo [1/2] 检查依赖...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖...
    pip install -r requirements.txt -q
)

echo [2/2] 启动统一服务...
echo.
echo 访问地址:
echo   - 统一入口: http://localhost:8000
echo   - 前端直访: http://localhost:8501
echo   - API文档:  http://localhost:8000/docs
echo.

python start.py

pause
