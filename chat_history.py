"""
对话历史管理模块
保存和加载每个 conversation_id 的对话历史
"""

import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

# 对话历史存储目录
CHAT_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chat_histories')

# 确保目录存在
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)


def get_history_file_path(conversation_id: str) -> str:
    """获取对话历史文件路径"""
    # 使用 conversation_id 作为文件名（安全处理）
    safe_id = "".join(c for c in conversation_id if c.isalnum() or c in "-_")
    return os.path.join(CHAT_HISTORY_DIR, f"{safe_id}.json")


def save_chat_message(conversation_id: str, role: str, content: str, 
                      think_content: str = "", metadata: Dict[str, Any] = None) -> bool:
    """
    保存单条对话消息
    
    Args:
        conversation_id: 会话ID
        role: 角色 (user/bot)
        content: 消息内容
        think_content: 思考内容（仅bot消息）
        metadata: 额外元数据
    
    Returns:
        bool: 是否保存成功
    """
    try:
        file_path = get_history_file_path(conversation_id)
        
        # 读取现有历史
        history = load_chat_history(conversation_id)
        
        # 添加新消息
        message = {
            "role": role,
            "content": content,
            "think_content": think_content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        history.append(message)
        
        # 保存到文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"[ChatHistory] Error saving message: {e}")
        return False


def load_chat_history(conversation_id: str) -> List[Dict[str, Any]]:
    """
    加载对话历史（按时间正序排序）
    
    Args:
        conversation_id: 会话ID
    
    Returns:
        List[Dict]: 对话历史列表（按时间正序）
    """
    try:
        file_path = get_history_file_path(conversation_id)
        
        if not os.path.exists(file_path):
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        # 按时间戳正序排序
        history.sort(key=lambda x: x.get('timestamp', ''))
        return history
    except Exception as e:
        print(f"[ChatHistory] Error loading history: {e}")
        return []


def get_user_conversations(user_id: str) -> List[Dict[str, Any]]:
    """
    获取用户的所有会话列表
    
    Args:
        user_id: 用户ID
    
    Returns:
        List[Dict]: 会话列表（包含conversation_id和最后消息时间）
    """
    conversations = []
    
    try:
        for filename in os.listdir(CHAT_HISTORY_DIR):
            if filename.endswith('.json'):
                conversation_id = filename[:-5]  # 移除 .json
                history = load_chat_history(conversation_id)
                
                if history:
                    # 检查是否是该用户的对话（通过metadata中的user_id）
                    user_messages = [m for m in history if m.get('metadata', {}).get('user_id') == user_id]
                    
                    if user_messages:
                        last_message = history[-1]
                        first_message = history[0]
                        
                        conversations.append({
                            "conversation_id": conversation_id,
                            "created_at": first_message.get('timestamp'),
                            "updated_at": last_message.get('timestamp'),
                            "message_count": len(history)
                        })
    except Exception as e:
        print(f"[ChatHistory] Error listing conversations: {e}")
    
    # 按更新时间排序
    conversations.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
    return conversations


def delete_chat_history(conversation_id: str) -> bool:
    """
    删除对话历史
    
    Args:
        conversation_id: 会话ID
    
    Returns:
        bool: 是否删除成功
    """
    try:
        file_path = get_history_file_path(conversation_id)
        if os.path.exists(file_path):
            os.remove(file_path)
        return True
    except Exception as e:
        print(f"[ChatHistory] Error deleting history: {e}")
        return False
