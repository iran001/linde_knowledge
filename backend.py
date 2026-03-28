"""
林德亚太知识库管理平台 - FastAPI 后端
使用Jinja2模板引擎和配置文件
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import logging
import os
from datetime import datetime

# 导入配置文件
from config import SERVER_CONFIG, APP_INFO

# 导入路由
from routes import pages_router, api_router


# =============================================================================
# 日志配置 - 按日期命名文件
# =============================================================================
def setup_logging():
    """配置日志记录，每天一个文件，文件名按日期命名"""
    # 日志目录
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 日志文件名格式: logs/backend_2025-03-13.log
    today = datetime.now().strftime('%Y-%m-%d')
    log_file = os.path.join(log_dir, f'backend_{today}.log')
    
    # 创建文件处理器
    file_handler = logging.FileHandler(
        filename=log_file,
        encoding='utf-8'
    )
    
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    # 配置根日志记录器
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            file_handler,
            logging.StreamHandler()  # 同时输出到控制台
        ]
    )
    
    # 设置 uvicorn 访问日志
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = [file_handler, logging.StreamHandler()]
    uvicorn_access.propagate = False
    
    print(f"[Logging] 日志文件: {log_file}")
    print(f"[Logging] 日志目录: {log_dir}")


# 初始化日志
setup_logging()

# =============================================================================
# FastAPI 应用实例
# =============================================================================
app = FastAPI(
    title=APP_INFO["name"],
    description="支持RBAC权限控制和动态Prompt注入的AI知识管理后端",
    version=APP_INFO["version"]
)

# =============================================================================
# CORS 配置
# =============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# 注册路由
# =============================================================================
app.include_router(pages_router)
app.include_router(api_router)

# =============================================================================
# 静态文件配置
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/", StaticFiles(directory=BASE_DIR, check_dir=False), name="static")

# =============================================================================
# 启动入口
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print(f"{APP_INFO['name']} - FastAPI 服务")
    print("=" * 60)
    print("服务地址:")
    print(f"  • 首页:      http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['backend_port']}/")
    print(f"  • API文档:   http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['backend_port']}/docs")
    print(f"  • ReDoc:     http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['backend_port']}/redoc")
    print("=" * 60)

    uvicorn.run(
        "backend:app",
        host=str(SERVER_CONFIG["host"]),
        port=int(SERVER_CONFIG["backend_port"]),
        reload=bool(SERVER_CONFIG["reload"]),
        log_config=None  # 使用我们自定义的日志配置
    )
