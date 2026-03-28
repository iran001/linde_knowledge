"""
Dify API 服务 - 封装所有与 Dify 平台的交互
"""

import json
import logging
import mimetypes
import os
from typing import Dict, Any, Optional

import httpx
from fastapi import UploadFile

from config import DIFY_CONFIG

logger = logging.getLogger(__name__)


# =============================================================================
# Dify 文件上传
# =============================================================================

async def upload_file_to_dify(file: UploadFile, file_content: bytes) -> Dict[str, Any]:
    """
    上传文件到 Dify，获取 file_id
    
    Args:
        file: 上传的文件对象
        file_content: 文件内容字节
        
    Returns:
        成功返回 {"success": True, "file_id": xxx}
        失败返回 {"success": False, "error": "错误信息"}
    """
    try:
        base_url = str(DIFY_CONFIG.get("base_url", "")).rstrip("/")
        api_key = str(DIFY_CONFIG.get("api_key", ""))
        upload_endpoint = str(DIFY_CONFIG.get("upload_endpoint", "/files/upload"))
        
        url = f"{base_url}{upload_endpoint}"
        mime_type = _detect_mime_type(file.filename or "")
        
        logger.info("=" * 80)
        logger.info("[Dify File Upload] REQUEST")
        logger.info(f"[Dify File Upload] URL: {url}")
        logger.info(f"[Dify File Upload] Filename: {file.filename}")
        logger.info(f"[Dify File Upload] MIME Type: {mime_type}")
        logger.info(f"[Dify File Upload] File Size: {len(file_content)} bytes")
        
        headers = {"Authorization": f"Bearer {api_key}"}
        files = {'file': (file.filename, file_content, mime_type)}
        
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, headers=headers, files=files)

            logger.info("[Dify File Upload] RESPONSE")
            logger.info(f"[Dify File Upload] Status Code: {response.status_code}")
            
            if response.status_code in [200, 201]:
                data = response.json()
                file_id = data.get('id')
                if file_id:
                    logger.info(f"[Dify File Upload] Success, file_id: {file_id}")
                    return {"success": True, "file_id": file_id}
                else:
                    error_msg = f"响应缺少 'id' 字段: {data}"
                    logger.error(f"[Dify File Upload] {error_msg}")
                    return {"success": False, "error": error_msg}
            else:
                error_text = response.text
                logger.error(f"[Dify File Upload] HTTP Error: {response.status_code}")
                logger.error(f"[Dify File Upload] Error Response: {error_text[:500]}")
                # 尝试解析 JSON 错误响应
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message') or error_data.get('error') or f"HTTP {response.status_code}: {error_text[:200]}"
                except:
                    error_msg = f"HTTP {response.status_code}: {error_text[:200]}"
                return {"success": False, "error": error_msg}
                
    except httpx.TimeoutException as e:
        error_msg = "上传超时，请稍后重试"
        logger.error(f"[Dify File Upload] Timeout: {e}")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"上传异常: {str(e)}"
        logger.error(f"[Dify File Upload] Exception: {e}")
        import traceback
        logger.error(f"[Dify File Upload] Traceback: {traceback.format_exc()}")
        return {"success": False, "error": error_msg}


def _detect_mime_type(filename: str) -> str:
    """检测文件的 MIME 类型"""
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        return mime_type
    
    ext = os.path.splitext(filename)[1].lower()
    mime_map = {
        '.txt': 'text/plain',
        '.md': 'text/markdown',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.pdf': 'application/pdf',
        '.json': 'application/json',
        '.csv': 'text/csv'
    }
    return mime_map.get(ext, 'application/octet-stream')


# =============================================================================
# Dify 冲突检查 (Workflow API)
# =============================================================================

async def call_dify_conflict_check_with_files(newfile_id: str, overfile_ids: list) -> Dict[str, Any]:
    """
    调用 Dify 冲突检查接口 (使用 file_id)
    
    Args:
        newfile_id: 新上传文件的 Dify file_id
        overfile_ids: 已有文件的 Dify file_id 列表 (支持批量)
        
    Returns:
        冲突检查结果字典
    """
    try:
        filecheck_endpoint = str(DIFY_CONFIG.get("filecheck_endpoint", ""))
        base_url = str(DIFY_CONFIG.get("base_url", "")).rstrip("/")
        api_key = str(DIFY_CONFIG.get("workflow_api_key", ""))
        
        url = f"{base_url}{_ensure_leading_slash(filecheck_endpoint)}"
        payload = build_conflict_check_payload(newfile_id, overfile_ids)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        _log_conflict_check_request(url, newfile_id, overfile_ids, payload)
        
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, json=payload, headers=headers)

            logger.info("[Dify Conflict Check] RESPONSE")
            logger.info(f"[Dify Conflict Check] Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"[Dify Conflict Check] Response Body: {json.dumps(data, ensure_ascii=False)[:2000]}...")
                return parse_dify_workflow_response(data)
            else:
                logger.error(f"[Dify Conflict Check] HTTP Error: {response.status_code}")
                logger.error(f"[Dify Conflict Check] Error Response: {response.text[:500]}")
                return _default_conflict_result()
                
    except Exception as e:
        logger.error(f"[Dify Conflict Check] Exception: {e}")
        import traceback
        logger.error(f"[Dify Conflict Check] Traceback: {traceback.format_exc()}")
        return _default_conflict_result()


def build_conflict_check_payload(newfile_id: str, overfile_ids: list) -> Dict[str, Any]:
    """构建冲突检查请求的 payload，支持批量 overfile"""
    # 支持单个ID或ID列表
    if isinstance(overfile_ids, str):
        overfile_ids = [overfile_ids]
    
    overfile_list = [
        {"transfer_method": "local_file", "upload_file_id": fid, "type": "document"}
        for fid in overfile_ids
    ]
    
    return {
        "inputs": {
            "newfile": [{"transfer_method": "local_file", "upload_file_id": newfile_id, "type": "document"}],
            "overfile": overfile_list
        },
        "user": "admin"
    }


def _log_conflict_check_request(url: str, newfile_id: str, overfile_ids: list, payload: Dict):
    """记录冲突检查请求日志"""
    # 支持单个ID或ID列表
    if isinstance(overfile_ids, str):
        overfile_ids = [overfile_ids]
    
    logger.info("=" * 80)
    logger.info("[Dify Conflict Check] REQUEST")
    logger.info(f"[Dify Conflict Check] URL: {url}")
    logger.info(f"[Dify Conflict Check] newfile_id: {newfile_id}")
    logger.info(f"[Dify Conflict Check] overfile_ids count: {len(overfile_ids)}")
    logger.info(f"[Dify Conflict Check] overfile_ids: {overfile_ids}")
    logger.info(f"[Dify Conflict Check] Payload: {json.dumps(payload, ensure_ascii=False)}")
    logger.info("=" * 80)


def _default_conflict_result() -> Dict[str, Any]:
    """返回默认的冲突检查结果（无冲突）"""
    return {"status": "true", "conflict_point": "", "conflict_reason": "", "prompt": ""}


# =============================================================================
# Dify 冲突检查 (文本内容模式 - 兼容旧版)
# =============================================================================

async def call_dify_conflict_check(new_file_content: str, existing_file_content: str) -> Dict[str, Any]:
    """调用 Dify 冲突检查接口 (Workflow API) - 使用文本内容"""
    try:
        filecheck_endpoint = str(DIFY_CONFIG.get("filecheck_endpoint", ""))
        base_url = str(DIFY_CONFIG.get("base_url", "")).rstrip("/")
        api_key = str(DIFY_CONFIG.get("workflow_api_key", ""))
        
        url = f"{base_url}{_ensure_leading_slash(filecheck_endpoint)}"
        payload = {
            "inputs": {"newfile": new_file_content, "overfile": existing_file_content},
            "response_mode": "blocking",
            "user": "admin"
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        _log_text_conflict_request(url, len(new_file_content), len(existing_file_content))
        
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, json=payload, headers=headers)
            return _handle_conflict_response(response)

    except httpx.TimeoutException as e:
        logger.error(f"[Dify Workflow] Timeout Error: {e}")
        return _default_conflict_result()
    except Exception as e:
        logger.error(f"[Dify Workflow] Exception: {e}")
        import traceback
        logger.error(f"[Dify Workflow] Traceback: {traceback.format_exc()}")
        return _default_conflict_result()


def _log_text_conflict_request(url: str, new_len: int, over_len: int):
    """记录文本冲突检查请求日志"""
    logger.info("=" * 80)
    logger.info("[Dify Workflow] REQUEST")
    logger.info(f"[Dify Workflow] URL: {url}")
    logger.info(f"[Dify Workflow] Method: POST")
    logger.info(f"[Dify Workflow] Headers: {json.dumps({'Authorization': 'Bearer ***', 'Content-Type': 'application/json'}, ensure_ascii=False)}")
    logger.info(f"[Dify Workflow] Payload Summary: newfile_length={new_len}, overfile_length={over_len}")
    logger.info("=" * 80)


def _handle_conflict_response(response: httpx.Response) -> Dict[str, Any]:
    """处理冲突检查响应"""
    logger.info("[Dify Workflow] RESPONSE")
    logger.info(f"[Dify Workflow] Status Code: {response.status_code}")
    logger.info(f"[Dify Workflow] Response Headers: {dict(response.headers)}")
    
    if response.status_code != 200:
        logger.error(f"[Dify Workflow] HTTP Error: {response.status_code}")
        logger.error(f"[Dify Workflow] Error Response: {response.text[:1000]}")
        return _default_conflict_result()
    
    content_type = response.headers.get("content-type", "")
    
    if "text/event-stream" in content_type or "application/x-ndjson" in content_type:
        return _parse_streaming_response(response.text)
    else:
        data = response.json()
        logger.info(f"[Dify Workflow] Response Body: {json.dumps(data, ensure_ascii=False)[:2000]}...")
        return parse_dify_workflow_response(data)


def _parse_streaming_response(text: str) -> Dict[str, Any]:
    """解析流式响应 (SSE 格式)"""
    logger.info(f"[Dify Workflow] Detected streaming response")
    logger.info(f"[Dify Workflow] Raw streaming response: {text[:2000]}...")
    
    last_data = None
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            try:
                data_json = line[5:].strip()
                data = json.loads(data_json)
                last_data = data
                if data.get("event") == "workflow_finished":
                    break
            except json.JSONDecodeError:
                continue
    
    if last_data:
        return parse_dify_workflow_response(last_data)
    
    return _default_conflict_result()


# =============================================================================
# Dify Chat API
# =============================================================================

async def call_dify_chat(role: str, message: str, conversation_id: str, system_prompt: str) -> Dict[str, Any]:
    """调用 Dify Chat API"""
    try:
        base_url = str(DIFY_CONFIG.get("base_url", "")).rstrip("/")
        api_key = str(DIFY_CONFIG.get("api_key", ""))
        
        payload = {
            "inputs": {"sys_prompt": system_prompt},
            "query": message,
            "response_mode": "blocking",
            "conversation_id": conversation_id or "",
            "user": f"user_{role}",
            "files": []
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        url = f"{base_url}/chat-messages"
        
        logger.info("=" * 60)
        logger.info("[Dify Chat API] REQUEST")
        logger.info(f"[Dify Chat API] URL: {url}")
        logger.info(f"[Dify Chat API] Payload: {json.dumps(payload, ensure_ascii=False)[:500]}...")
        
        async with httpx.AsyncClient(timeout=float(DIFY_CONFIG.get("timeout", 180))) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            logger.info("[Dify Chat API] RESPONSE")
            logger.info(f"[Dify Chat API] Status Code: {response.status_code}")
            
            if response.status_code == 200:
                dify_response = response.json()
                logger.info(f"[Dify Chat API] Response: {json.dumps(dify_response, ensure_ascii=False)[:500]}...")
                return {
                    "success": True,
                    "role": role,
                    "system_prompt_injected": True,
                    "dify_response": dify_response
                }
            else:
                logger.error(f"[Dify Chat API] Error: {response.status_code} - {response.text[:500]}")
                return _mock_chat_response(role, message, system_prompt)
                
    except Exception as e:
        logger.error(f"[Dify Chat API] Exception: {e}")
        import traceback
        logger.error(f"[Dify Chat API] Traceback: {traceback.format_exc()}")
        return _mock_chat_response(role, message, system_prompt)


def _mock_chat_response(role: str, message: str, system_prompt: str) -> Dict[str, Any]:
    """返回模拟的聊天响应"""
    return {
        "success": True,
        "role": role,
        "system_prompt_injected": True,
        "mock_mode": True,
        "answer": f"【角色: {role}】\n\n已注入对应角色的System Prompt。\n\n用户问题: {message}"
    }


# =============================================================================
# 响应解析
# =============================================================================

def parse_dify_workflow_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    解析 Dify Workflow API 响应
    支持多种格式: 标准格式、直接格式、event 格式
    """
    outputs = None
    
    # 情况1: 标准嵌套格式 {"data": {"outputs": {...}}}
    if "data" in data and isinstance(data["data"], dict):
        if "outputs" in data["data"]:
            outputs = data["data"]["outputs"]
            logger.info(f"[Dify Response Parser] Found outputs in data.outputs")
    
    # 情况2: 直接格式 {"outputs": {...}}
    if outputs is None and "outputs" in data:
        outputs = data["outputs"]
        logger.info(f"[Dify Response Parser] Found outputs in root.outputs")
    
    # 情况3: event 格式 {"event": "...", "data": {"outputs": {...}}}
    if outputs is None and "event" in data:
        event_data = data.get("data", {})
        if isinstance(event_data, dict) and "outputs" in event_data:
            outputs = event_data["outputs"]
            logger.info(f"[Dify Response Parser] Found outputs in event data.outputs, event={data.get('event')}")
    
    # 情况4: Chat API 格式兼容
    if outputs is None and "answer" in data:
        logger.info(f"[Dify Response Parser] Found answer field, treating as direct output")
        return {
            "status": "false" if "冲突" in str(data.get("answer", "")) else "true",
            "conflict_point": "",
            "conflict_reason": data.get("answer", ""),
            "prompt": data.get("answer", "")
        }
    
    if outputs:
        result = {
            "status": str(outputs.get("status", "true")).lower(),
            "conflict_point": outputs.get("conflict_point", ""),
            "conflict_reason": outputs.get("conflict_reason", ""),
            "prompt": outputs.get("prompt", outputs.get("text", outputs.get("answer", "")))
        }
        logger.info(f"[Dify Response Parser] Parsed outputs: {json.dumps(result, ensure_ascii=False)}")
        return result
    
    logger.warning(f"[Dify Response Parser] Could not find outputs in response, keys: {list(data.keys())}")
    return _default_conflict_result()


# =============================================================================
# 工具函数
# =============================================================================

def _ensure_leading_slash(path: str) -> str:
    """确保路径以 / 开头"""
    return path if path.startswith("/") else f"/{path}"
