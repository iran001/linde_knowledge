"""
数据存储模块 - 共享内存数据存储
用于在生产环境迁移到Redis/数据库前的临时存储
"""

from typing import Dict, Any, List
from config import MOCK_KNOWLEDGE_UPLOAD

# 会话存储
sessions: Dict[str, Dict[str, Any]] = {}

# 文件数据
knowledge_upload_db: List[Dict[str, Any]] = MOCK_KNOWLEDGE_UPLOAD.copy()
