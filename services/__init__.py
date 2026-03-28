"""
服务模块 - 封装外部 API 调用和业务逻辑
"""

from .dify_service import (
    upload_file_to_dify,
    call_dify_conflict_check,
    call_dify_conflict_check_with_files,
    build_conflict_check_payload,
    parse_dify_workflow_response,
    call_dify_chat,
)

from .ragflow_service import (
    fetch_documents_from_api,
    upload_to_ragflow,
    search_chunks_from_ragflow,
)

from .file_service import (
    update_dify_uploaded_files,
    get_summary_file_content,
)

__all__ = [
    # Dify 服务
    'upload_file_to_dify',
    'call_dify_conflict_check',
    'call_dify_conflict_check_with_files',
    'build_conflict_check_payload',
    'parse_dify_workflow_response',
    'call_dify_chat',
    # RAGFlow 服务
    'fetch_documents_from_api',
    'upload_to_ragflow',
    'search_chunks_from_ragflow',
    # 文件服务
    'update_dify_uploaded_files',
    'get_summary_file_content',
]
