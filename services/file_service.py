"""
文件服务 - 处理文件配置管理和内容读取
"""

import glob
import json
import logging
import os
import re
from typing import Optional

from config import DIFY_UPLOADED_FILES

logger = logging.getLogger(__name__)


# =============================================================================
# Dify 上传文件配置管理
# =============================================================================

def update_dify_uploaded_files(filename: str, file_id: str, conflict_filename: Optional[str] = None):
    """
    更新 DIFY_UPLOADED_FILES 配置
    
    Args:
        filename: 新上传的文件名
        file_id: 新上传文件的 Dify file_id
        conflict_filename: 如果替换了冲突文件，记录被替换的文件名（仅用于日志，不删除配置）
    """
    try:
        # 记录冲突文件替换信息（但不删除原配置）
        if conflict_filename and conflict_filename != filename:
            logger.info(f"[Config Update] Replacing conflict file: {conflict_filename} -> {filename}")
        
        # 更新内存中的配置（添加/更新新文件记录）
        DIFY_UPLOADED_FILES[filename] = file_id
        
        # 更新 config.py 文件
        _persist_config_to_file()
        
        logger.info(f"[Config Update] Updated DIFY_UPLOADED_FILES: {filename} -> {file_id}")
        
    except Exception as e:
        logger.error(f"[Config Update] Error updating config: {e}")
        import traceback
        logger.error(f"[Config Update] Traceback: {traceback.format_exc()}")


def _persist_config_to_file():
    """将配置持久化到 config.py 文件"""
    config_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.py")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 构建新的配置字符串
    new_config = json.dumps(DIFY_UPLOADED_FILES, ensure_ascii=False, indent=4)
    replacement = f'DIFY_UPLOADED_FILES: Dict[str, str] = {new_config}'
    
    # 尝试多种匹配模式
    patterns = [
        r'DIFY_UPLOADED_FILES: Dict\[str, str\] = \{[^}]*\}',
        r'DIFY_UPLOADED_FILES:.*?=.*?\{.*?\}'
    ]
    
    new_content = content
    for pattern in patterns:
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        if new_content != content:
            break
    
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(new_content)


# =============================================================================
# Summary 文件内容获取
# =============================================================================

def get_summary_file_content() -> str:
    """获取 summary 目录下的第一个文件内容"""
    summary_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "summary")
    
    logger.info(f"[Summary File] Looking for files in: {summary_dir}")
    
    if not os.path.exists(summary_dir):
        logger.warning(f"[Summary File] Directory not found: {summary_dir}")
        return ""
    
    # 获取所有文本文件
    text_files = []
    for ext in ['*.txt', '*.md', '*.doc', '*.docx', '*.pdf']:
        text_files.extend(glob.glob(os.path.join(summary_dir, ext)))
    
    logger.info(f"[Summary File] Found {len(text_files)} files: {text_files}")
    
    if not text_files:
        logger.warning("[Summary File] No text files found in summary directory")
        return ""
    
    # 读取第一个文件
    try:
        with open(text_files[0], 'r', encoding='utf-8') as f:
            content = f.read()
            logger.info(f"[Summary File] Successfully read file: {text_files[0]}, length: {len(content)} chars")
            return content
    except Exception as e:
        logger.error(f"[Summary File] Error reading file {text_files[0]}: {e}")
        return ""
