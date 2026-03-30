"""
审计日志服务 - 记录系统关键操作日志
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum
from pathlib import Path
import asyncio
from dataclasses import dataclass, asdict

# 审计日志文件路径
AUDIT_LOG_DIR = Path(__file__).parent.parent / "logs"
AUDIT_LOG_FILE = AUDIT_LOG_DIR / "audit.log"

# 确保日志目录存在
AUDIT_LOG_DIR.mkdir(exist_ok=True)

# 审计日志操作类型
class AuditActionType(str, Enum):
    KNOWLEDGE_IMPORT = "knowledge_import"      # 知识导入
    KNOWLEDGE_QUERY = "knowledge_query"        # 知识查询
    KNOWLEDGE_SEARCH = "knowledge_search"      # 知识搜索
    CHAT_QUESTION = "chat_question"            # 问答对话
    DOCUMENT_DOWNLOAD = "document_download"    # 文档下载
    USER_LOGIN = "user_login"                  # 用户登录
    USER_LOGOUT = "user_logout"                # 用户登出


# 审计日志数据类
@dataclass
class AuditLogEntry:
    timestamp: str                    # ISO格式时间戳
    action: str                       # 操作类型
    user_id: str                      # 用户ID
    user_name: str                    # 用户名
    user_role: str                    # 用户角色
    ip_address: Optional[str]         # IP地址
    details: Dict[str, Any]           # 操作详情
    status: str                       # 操作状态 (success/failure)
    message: Optional[str] = None     # 附加消息

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AuditLogger:
    """审计日志记录器"""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.logger = logging.getLogger("audit")
            self.logger.setLevel(logging.INFO)
            
            # 创建文件处理器
            file_handler = logging.FileHandler(AUDIT_LOG_FILE, encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            
            # 设置格式 - 使用JSON格式
            formatter = logging.Formatter('%(message)s')
            file_handler.setFormatter(formatter)
            
            # 清除现有处理器，避免重复
            self.logger.handlers = []
            self.logger.addHandler(file_handler)
    
    async def log(
        self,
        action: AuditActionType,
        user_id: str,
        user_name: str,
        user_role: str,
        details: Dict[str, Any],
        status: str = "success",
        message: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """
        记录审计日志
        
        Args:
            action: 操作类型
            user_id: 用户ID
            user_name: 用户名
            user_role: 用户角色
            details: 操作详情
            status: 操作状态
            message: 附加消息
            ip_address: IP地址
        """
        entry = AuditLogEntry(
            timestamp=datetime.now().isoformat(),
            action=action.value,
            user_id=user_id,
            user_name=user_name,
            user_role=user_role,
            ip_address=ip_address,
            details=details,
            status=status,
            message=message
        )
        
        async with self._lock:
            self.logger.info(entry.to_json())
    
    def read_logs(
        self,
        page: int = 1,
        page_size: int = 50,
        action_filter: Optional[str] = None,
        user_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        读取审计日志
        
        Args:
            page: 页码
            page_size: 每页数量
            action_filter: 操作类型过滤
            user_filter: 用户过滤
            date_from: 开始日期 (ISO格式)
            date_to: 结束日期 (ISO格式)
            
        Returns:
            包含日志列表和总数的字典
        """
        logs = []
        
        if not AUDIT_LOG_FILE.exists():
            return {"logs": [], "total": 0}
        
        try:
            with open(AUDIT_LOG_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        log_entry = json.loads(line)
                        
                        # 过滤操作类型
                        if action_filter and log_entry.get('action') != action_filter:
                            continue
                        
                        # 过滤用户
                        if user_filter:
                            if user_filter not in log_entry.get('user_id', '') and \
                               user_filter not in log_entry.get('user_name', ''):
                                continue
                        
                        # 过滤日期范围
                        timestamp = log_entry.get('timestamp', '')
                        if date_from and timestamp < date_from:
                            continue
                        if date_to and timestamp > date_to:
                            continue
                        
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            return {"logs": [], "total": 0, "error": str(e)}
        
        # 按时间倒序排列
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        total = len(logs)
        
        # 分页
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_logs = logs[start_idx:end_idx]
        
        return {
            "logs": paginated_logs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    
    def get_action_types(self) -> List[Dict[str, str]]:
        """获取所有操作类型列表"""
        return [
            {"value": action.value, "label": self._get_action_label(action)}
            for action in AuditActionType
        ]
    
    def _get_action_label(self, action: AuditActionType) -> str:
        """获取操作类型的中文标签"""
        labels = {
            AuditActionType.KNOWLEDGE_IMPORT: "知识导入",
            AuditActionType.KNOWLEDGE_QUERY: "知识查询",
            AuditActionType.KNOWLEDGE_SEARCH: "知识搜索",
            AuditActionType.CHAT_QUESTION: "问答对话",
            AuditActionType.DOCUMENT_DOWNLOAD: "文档下载",
            AuditActionType.USER_LOGIN: "用户登录",
            AuditActionType.USER_LOGOUT: "用户登出",
        }
        return labels.get(action, action.value)


# 全局审计日志实例
audit_logger = AuditLogger()


# 便捷函数
async def log_knowledge_import(
    user_id: str,
    user_name: str,
    user_role: str,
    file_name: str,
    file_size: int,
    status: str = "success",
    message: Optional[str] = None,
    ip_address: Optional[str] = None
):
    """记录知识导入日志"""
    await audit_logger.log(
        action=AuditActionType.KNOWLEDGE_IMPORT,
        user_id=user_id,
        user_name=user_name,
        user_role=user_role,
        details={
            "file_name": file_name,
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2)
        },
        status=status,
        message=message,
        ip_address=ip_address
    )


async def log_knowledge_search(
    user_id: str,
    user_name: str,
    user_role: str,
    keyword: str,
    result_count: int,
    dataset_id: Optional[str] = None,
    status: str = "success",
    ip_address: Optional[str] = None
):
    """记录知识搜索日志"""
    await audit_logger.log(
        action=AuditActionType.KNOWLEDGE_SEARCH,
        user_id=user_id,
        user_name=user_name,
        user_role=user_role,
        details={
            "keyword": keyword,
            "result_count": result_count,
            "dataset_id": dataset_id
        },
        status=status,
        ip_address=ip_address
    )


async def log_chat_question(
    user_id: str,
    user_name: str,
    user_role: str,
    question: str,
    conversation_id: Optional[str] = None,
    status: str = "success",
    ip_address: Optional[str] = None
):
    """记录问答对话日志"""
    await audit_logger.log(
        action=AuditActionType.CHAT_QUESTION,
        user_id=user_id,
        user_name=user_name,
        user_role=user_role,
        details={
            "question": question[:500],  # 限制长度
            "conversation_id": conversation_id
        },
        status=status,
        ip_address=ip_address
    )


async def log_document_download(
    user_id: str,
    user_name: str,
    user_role: str,
    document_id: str,
    document_name: str,
    status: str = "success",
    ip_address: Optional[str] = None
):
    """记录文档下载日志"""
    await audit_logger.log(
        action=AuditActionType.DOCUMENT_DOWNLOAD,
        user_id=user_id,
        user_name=user_name,
        user_role=user_role,
        details={
            "document_id": document_id,
            "document_name": document_name
        },
        status=status,
        ip_address=ip_address
    )


async def log_user_login(
    user_id: str,
    user_name: str,
    user_role: str,
    status: str = "success",
    message: Optional[str] = None,
    ip_address: Optional[str] = None
):
    """记录用户登录日志"""
    await audit_logger.log(
        action=AuditActionType.USER_LOGIN,
        user_id=user_id,
        user_name=user_name,
        user_role=user_role,
        details={},
        status=status,
        message=message,
        ip_address=ip_address
    )


async def log_user_logout(
    user_id: str,
    user_name: str,
    user_role: str,
    ip_address: Optional[str] = None
):
    """记录用户登出日志"""
    await audit_logger.log(
        action=AuditActionType.USER_LOGOUT,
        user_id=user_id,
        user_name=user_name,
        user_role=user_role,
        details={},
        status="success",
        ip_address=ip_address
    )
