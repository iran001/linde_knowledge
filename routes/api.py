"""
API路由 - RESTful API接口
只保留路由定义，业务逻辑委托给服务模块
"""

from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import logging

from config import (
    ROLE_DISPLAY_MAP, ROLE_LEVEL_MAP, ROLE_PROMPT_MAP,
    MOCK_USERS, APP_INFO, PAGE_CONFIG, TEMPLATE_DIR,
    RAGFLOW_CONFIG
)
import os
from fastapi import UploadFile, File
from fastapi.templating import Jinja2Templates

from data_store import sessions, knowledge_upload_db
from chat_history import save_chat_message, load_chat_history, get_user_conversations, delete_chat_history

# 导入服务模块
from services import (
    fetch_documents_from_api,
    upload_to_ragflow,
    search_chunks_from_ragflow,
)


logger = logging.getLogger(__name__)

# 创建路由器和模板
router = APIRouter(prefix="/api")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


# =============================================================================
# Pydantic 模型
# =============================================================================

class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    role: str
    message: str
    conversation_id: Optional[str] = None


class DocumentFilterRequest(BaseModel):
    role: str
    search_keyword: Optional[str] = None


class KnowledgeUploadRequest(BaseModel):
    title: str
    content: str
    priority: str = "normal"


class SaveMessageRequest(BaseModel):
    conversation_id: str
    role: str
    content: str
    think_content: str = ""


class ChatHistoryResponse(BaseModel):
    conversation_id: str
    history: List[Dict[str, Any]]


# =============================================================================
# 工具函数
# =============================================================================

def get_user_role_level(role: str) -> int:
    """获取角色的权限级别"""
    return ROLE_LEVEL_MAP.get(role, 0)


def get_system_prompt_by_role(role: str) -> str:
    """根据角色获取对应的System Prompt"""
    return ROLE_PROMPT_MAP.get(role, ROLE_PROMPT_MAP["reception"])


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """从会话中获取当前用户"""
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        return sessions[session_id]
    return None


# =============================================================================
# 认证 API
# =============================================================================

@router.post("/login")
async def api_login(request: Request, login_data: LoginRequest):
    """API登录接口"""
    user = MOCK_USERS.get(login_data.username)
    
    if not user or user["password"] != login_data.password:
        return {"success": False, "message": "用户名或密码错误"}
    
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"]
    }
    
    response = {
        "success": True,
        "message": "登录成功",
        "user": {
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"]
        }
    }
    
    resp = JSONResponse(content=response)
    resp.set_cookie(key="session_id", value=session_id, httponly=True)
    return resp


@router.post("/login-form")
async def api_login_form(request: Request, username: str = Form(...), password: str = Form(...)):
    """表单登录接口"""
    user = MOCK_USERS.get(username)
    
    if not user or user["password"] != password:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "app_name": APP_INFO["name"],
            "logo": APP_INFO["logo"],
            "background_image": PAGE_CONFIG["login"]["background_image"],
            "error": "用户名或密码错误",
            "warning": None,
            "user": None
        })
    
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"]
    }
    
    response = RedirectResponse(url="/page/chat", status_code=302)
    response.set_cookie(key="session_id", value=session_id, httponly=True)
    return response


@router.post("/logout")
async def api_logout(request: Request):
    """登出接口"""
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        del sessions[session_id]
    
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="session_id")
    return response


# =============================================================================
# 聊天 API
# =============================================================================

@router.post("/chat")
async def api_chat(request: Request, chat_data: ChatRequest):
    """聊天接口 - 代理转发到 Dify Chat API"""
    from services.dify_service import call_dify_chat
    
    system_prompt = get_system_prompt_by_role(chat_data.role)
    return await call_dify_chat(
        role=chat_data.role,
        message=chat_data.message,
        conversation_id=chat_data.conversation_id or "",
        system_prompt=system_prompt
    )


# =============================================================================
# 文档 API
# =============================================================================

@router.get("/documents")
async def api_get_documents(
    request: Request,
    keyword: str = "",
    page: int = 1,
    page_size: int = 10
):
    """获取文档列表接口 (GET) - 供前端 AJAX 调用"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    result = await fetch_documents_from_api(
        role=user["role"],
        keyword=keyword,
        page=page,
        page_size=page_size
    )
    
    return {
        "success": True,
        "role": user["role"],
        "role_display": ROLE_DISPLAY_MAP.get(user["role"], {}).get("name", "未知"),
        "total_count": result["total"],
        "current_page": page,
        "total_pages": (result["total"] + page_size - 1) // page_size if result["total"] > 0 else 1,
        "page_size": page_size,
        "visible_permission": ROLE_DISPLAY_MAP.get(user["role"], {}).get("name", "未知"),
        "documents": result["documents"]
    }


# =============================================================================
# 知识上传 API
# =============================================================================

@router.get("/knowledge-upload")
async def api_get_knowledge_upload(request: Request):
    """获取文件列表"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    return {"success": True, "knowledge": knowledge_upload_db}


@router.post("/knowledge-upload")
async def api_add_knowledge_upload(request: Request, data: KnowledgeUploadRequest):
    """添加文件API接口（仅管理员）"""
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    new_knowledge = {
        "id": f"ku_{len(knowledge_upload_db) + 1:03d}",
        "title": data.title,
        "content": data.content,
        "priority": data.priority,
        "added_at": datetime.now().strftime("%Y-%m-%d")
    }
    
    knowledge_upload_db.append(new_knowledge)
    
    return {"success": True, "message": "文件添加成功", "knowledge": new_knowledge}


@router.post("/knowledge-upload-form")
async def api_add_knowledge_upload_form(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    priority: str = Form("normal")
):
    """添加文件表单接口（仅管理员）"""
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    new_knowledge = {
        "id": f"ku_{len(knowledge_upload_db) + 1:03d}",
        "title": title,
        "content": content,
        "priority": priority,
        "added_at": datetime.now().strftime("%Y-%m-%d")
    }
    
    knowledge_upload_db.append(new_knowledge)
    
    return RedirectResponse(url="/page/knowledge-upload", status_code=302)


# =============================================================================
# 对话历史 API
# =============================================================================

@router.post("/chat-history/save")
async def api_save_chat_message(request: Request, data: SaveMessageRequest):
    """保存对话消息"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    metadata = {
        "user_id": user.get("username"),
        "user_role": user.get("role"),
        "user_display_name": user.get("display_name")
    }
    
    success = save_chat_message(
        conversation_id=data.conversation_id,
        role=data.role,
        content=data.content,
        think_content=data.think_content,
        metadata=metadata
    )
    
    return {"success": success, "conversation_id": data.conversation_id}


@router.get("/chat-history/{conversation_id}")
async def api_get_chat_history(request: Request, conversation_id: str):
    """获取对话历史"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    history = load_chat_history(conversation_id)
    
    user_history = [
        msg for msg in history 
        if msg.get("metadata", {}).get("user_id") == user.get("username")
    ]
    
    return {"success": True, "conversation_id": conversation_id, "history": user_history}


@router.get("/chat-history")
async def api_get_user_conversations(request: Request):
    """获取用户的所有会话列表"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    conversations = get_user_conversations(user.get("username"))
    
    return {"success": True, "conversations": conversations}


@router.delete("/chat-history/{conversation_id}")
async def api_delete_chat_history(request: Request, conversation_id: str):
    """删除对话历史"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    history = load_chat_history(conversation_id)
    user_messages = [m for m in history if m.get("metadata", {}).get("user_id") == user.get("username")]
    
    if not user_messages:
        raise HTTPException(status_code=403, detail="无权删除此对话")
    
    success = delete_chat_history(conversation_id)
    
    return {"success": success, "conversation_id": conversation_id}


# =============================================================================
# 文档上传 API (带冲突检测)
# =============================================================================

ALLOWED_EXTENSIONS = ['.txt', '.pdf', '.doc', '.docx', '.md']


@router.post("/upload-document")
async def api_upload_document(
    request: Request,
    file: UploadFile = File(...)
):
    """
    上传文档到知识库（直接上传并解析，无冲突检测）
    1. 直接上传文件到 RAGFlow
    2. 触发文档解析
    """
    user = get_current_user(request)
    if not user:
        logger.warning("[Upload Document] Unauthorized access attempt")
        raise HTTPException(status_code=401, detail="未登录")
    
    filename = file.filename or ""
    _validate_file_extension(filename)
    
    try:
        # 读取文件内容
        file_content = await file.read()
        logger.info(f"[Upload Document] File read successful, size: {len(file_content)} bytes")
        
        # 直接上传到 RAGFlow
        logger.info("[Upload Document] Uploading file to RAGFlow...")
        upload_result = await upload_to_ragflow(file, file_content)
        
        if upload_result["success"]:
            logger.info("[Upload Document] Upload successful")
            return {"success": True, "message": "文件上传成功", "filename": file.filename}
        else:
            error_msg = upload_result.get("error", "未知错误")
            logger.error(f"[Upload Document] Upload failed: {error_msg}")
            raise HTTPException(
                status_code=500, 
                detail=f"上传到知识库失败: {error_msg}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Upload Document] Exception: {e}")
        logger.error(f"[Upload Document] Exception Type: {type(e).__name__}")
        import traceback
        logger.error(f"[Upload Document] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


def _validate_file_extension(filename: str):
    """验证文件扩展名"""
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        logger.error(f"[Upload Document] Invalid file type: {file_ext}")
        raise HTTPException(
            status_code=400, 
            detail=f"不支持的文件类型，请上传: {', '.join(ALLOWED_EXTENSIONS)}"
        )


# =============================================================================
# 链接代理 API - 用于访问需要 api_key 的外部链接
# =============================================================================

class ProxyLinkRequest(BaseModel):
    """代理链接请求"""
    url: str


@router.post("/proxy-link")
async def proxy_link(request: ProxyLinkRequest):
    """
    代理访问外部链接，自动添加 Ragflow api_key 到 header
    用于支持 [text](url) 格式的链接点击访问
    """
    import httpx
    from config import RAGFLOW_CONFIG
    
    target_url = request.url
    api_key = str(RAGFLOW_CONFIG.get("api_key", ""))
    
    logger.info(f"[Proxy Link] Proxying request to: {target_url}, api_key: {api_key}")
    
    try:
        # 使用 GET 方式访问目标 URL，添加 Authorization header
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(target_url, headers=headers)
            
            logger.info(f"[Proxy Link] Response status: {response.status_code}")
            logger.info(f"[Proxy Link] Response headers: {dict(response.headers)}")
            
            # 从 Content-Disposition header 中提取文件名
            original_filename = None
            content_disposition = response.headers.get("Content-Disposition", "")
            if content_disposition:
                # 解析 filename="xxx" 或 filename*=UTF-8''xxx
                import re
                # 优先匹配 filename="..." 或 filename='...' 引号内的所有内容
                filename_match = re.search(r'filename=[\'"]([^\'"]*)[\'"]', content_disposition, re.IGNORECASE)
                if not filename_match:
                    # 尝试匹配 filename*=UTF-8''xxx 格式
                    filename_match = re.search(r'filename\*=[\'"]?(?:UTF-8[\'"]{0,3})?([^;\s]+)', content_disposition, re.IGNORECASE)
                if filename_match:
                    original_filename = filename_match.group(1)
                    # URL decode if needed
                    try:
                        from urllib.parse import unquote
                        original_filename = unquote(original_filename)
                    except:
                        pass
            
            # 如果 header 中没有 filename，从 URL 路径提取
            if not original_filename:
                from urllib.parse import urlparse, unquote
                parsed_url = urlparse(target_url)
                path_parts = parsed_url.path.split('/')
                if path_parts and path_parts[-1]:
                    original_filename = unquote(path_parts[-1])
            
            logger.info(f"[Proxy Link] Original filename: {original_filename}")
            
            # 获取响应的 Content-Type
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            
            # 如果响应是 JSON 格式，说明可能是错误信息，返回给前端显示
            if "application/json" in content_type:
                try:
                    json_data = response.json()
                    error_msg = json_data.get("message") or json_data.get("error") or str(json_data)
                    logger.error(f"[Proxy Link] Target returned JSON error: {error_msg}")
                    raise HTTPException(status_code=400, detail=f"目标接口返回错误: {error_msg}")
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"[Proxy Link] Failed to parse JSON response: {e}")
                    raise HTTPException(status_code=400, detail="目标接口返回错误数据")
            
            # 返回响应内容，附加原始文件名到自定义 header（用于文件下载）
            from fastapi.responses import Response
            from urllib.parse import quote
            response_headers = {
                "Content-Type": content_type
            }
            if original_filename:
                # 对文件名进行 URL 编码，避免中文导致的 latin-1 编码错误
                encoded_filename = quote(original_filename, safe='')
                response_headers["X-Original-Filename"] = encoded_filename
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers
            )
            
    except httpx.TimeoutException:
        logger.error("[Proxy Link] Request timeout")
        raise HTTPException(status_code=504, detail="请求超时")
    except Exception as e:
        logger.error(f"[Proxy Link] Error: {e}")
        raise HTTPException(status_code=500, detail=f"代理请求失败: {str(e)}")


# =============================================================================
# 文档下载 API
# =============================================================================

@router.get("/document-download")
async def api_download_document(
    request: Request,
    document_id: str = "",
    dataset_id: str = ""
):
    """
    下载文档
    
    Args:
        document_id: 文档ID
        dataset_id: 知识库ID（可选，如果不提供则尝试从配置中获取）
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    if not document_id:
        raise HTTPException(status_code=400, detail="缺少文档ID")
    
    # 如果没有提供 dataset_id，使用默认的
    if not dataset_id:
        dataset_id = str(RAGFLOW_CONFIG.get("dataset_id", ""))
    
    if not dataset_id:
        raise HTTPException(status_code=400, detail="无法确定知识库ID")
    
    import httpx
    from fastapi.responses import StreamingResponse
    from urllib.parse import quote
    
    base_url = str(RAGFLOW_CONFIG.get("base_url", ""))
    api_key = str(RAGFLOW_CONFIG.get("api_key", ""))
    
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            # 首先获取文档信息以获取文件名
            doc_info_url = f"{base_url}/datasets/{dataset_id}/documents"
            doc_response = await client.get(
                doc_info_url,
                params={"page": 1, "page_size": 1000},
                headers=headers
            )
            
            filename = None
            if doc_response.status_code == 200:
                doc_data = doc_response.json()
                if doc_data.get("code") == 0:
                    docs = doc_data.get("data", {}).get("docs", [])
                    for doc in docs:
                        if doc.get("id") == document_id:
                            filename = doc.get("name", "document")
                            break
            
            if not filename:
                filename = f"document_{document_id}"
            
            # 使用 RAGFlow API 文档指定的端点获取文档内容
            # GET /api/v1/datasets/{dataset_id}/documents/{document_id}
            document_url = f"{base_url}/datasets/{dataset_id}/documents/{document_id}"
            logger.info(f"[Document Download] Fetching document from: {document_url}")
            
            response = await client.get(document_url, headers=headers)
            
            if response.status_code == 200:
                # 记录原始响应内容用于调试
                raw_content = response.content
                logger.info(f"[Document Download] Raw response length: {len(raw_content)} bytes")
                logger.info(f"[Document Download] Raw response start: {raw_content[:200]}")
                
                # 尝试解析 JSON
                try:
                    data = response.json()
                except Exception as json_error:
                    logger.error(f"[Document Download] JSON parse error: {json_error}")
                    # 如果无法解析为 JSON，直接返回原始内容
                    from io import BytesIO
                    file_stream = BytesIO(raw_content)
                    encoded_filename = quote(filename, safe='')
                    return StreamingResponse(
                        file_stream,
                        media_type="application/octet-stream",
                        headers={
                            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                        }
                    )
                
                if data.get("code") == 0:
                    doc_data = data.get("data", {})
                    
                    # 记录数据结构
                    logger.info(f"[Document Download] Document data keys: {list(doc_data.keys())}")
                    
                    # 尝试获取文档内容
                    content = doc_data.get("content", "")
                    
                    # 检查 content 的类型
                    logger.info(f"[Document Download] Content type: {type(content)}, length: {len(content) if content else 0}")
                    
                    # 如果 content 是字符串且不为空
                    if isinstance(content, str) and content:
                        # 检查是否是 base64 编码
                        import base64
                        import re
                        
                        # 尝试 base64 解码（base64 字符串通常是 ASCII）
                        try:
                            # 移除可能的空白字符
                            content_clean = content.strip()
                            # 检查是否是有效的 base64
                            if re.match(r'^[A-Za-z0-9+/]*={0,2}$', content_clean):
                                decoded_content = base64.b64decode(content_clean)
                                logger.info(f"[Document Download] Base64 decoded, length: {len(decoded_content)}")
                                from io import BytesIO
                                file_stream = BytesIO(decoded_content)
                            else:
                                # 不是 base64，作为普通文本处理
                                raise ValueError("Not valid base64")
                        except Exception as decode_error:
                            logger.info(f"[Document Download] Not base64, treating as text: {decode_error}")
                            from io import BytesIO
                            # 使用 errors='replace' 处理编码问题
                            file_stream = BytesIO(content.encode('utf-8', errors='replace'))
                    elif isinstance(content, (bytes, bytearray)):
                        # content 是二进制数据
                        from io import BytesIO
                        file_stream = BytesIO(content)
                    else:
                        # 如果没有有效的 content 字段，返回文档元数据作为 JSON
                        import json
                        from io import BytesIO
                        json_content = json.dumps(doc_data, ensure_ascii=False, indent=2)
                        file_stream = BytesIO(json_content.encode('utf-8', errors='replace'))
                        filename = f"{filename}.json"
                    
                    # 对文件名进行编码
                    encoded_filename = quote(filename, safe='')
                    
                    return StreamingResponse(
                        file_stream,
                        media_type="application/octet-stream",
                        headers={
                            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                        }
                    )
                else:
                    logger.error(f"[Document Download] API error: {data.get('message', 'Unknown')}")
                    raise HTTPException(
                        status_code=400, 
                        detail=f"获取文档失败: {data.get('message', '未知错误')}"
                    )
            else:
                logger.error(f"[Document Download] Failed: {response.status_code}, {response.text[:200]}")
                raise HTTPException(
                    status_code=404, 
                    detail="文档下载失败，文档可能不存在或无法访问"
                )
                
    except httpx.TimeoutException:
        logger.error("[Document Download] Request timeout")
        raise HTTPException(status_code=504, detail="请求超时")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Document Download] Error: {e}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


# =============================================================================
# Chunk 图片代理 API
# =============================================================================

@router.get("/chunk-image")
async def api_get_chunk_image(request: Request, image_id: str = ""):
    """
    代理获取 RAGFlow chunk 图片
    
    Args:
        image_id: 图片ID
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    if not image_id:
        raise HTTPException(status_code=400, detail="缺少图片ID")
    
    import httpx
    from config import RAGFLOW_CONFIG
    from fastapi.responses import Response
    
    img_url = RAGFLOW_CONFIG.get("img_url", "")
    api_key = RAGFLOW_CONFIG.get("api_key", "")
    
    # RAGFlow 图片获取 URL
    image_url = f"{img_url}/{image_id}"
    
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(image_url, headers=headers)
            
            if response.status_code == 200:
                # 返回图片内容
                return Response(
                    content=response.content,
                    media_type=response.headers.get("Content-Type", "image/jpeg"),
                    headers={
                        "Cache-Control": "max-age=3600"
                    }
                )
            else:
                logger.error(f"[Chunk Image] Failed to get image: {response.status_code}, {response.text[:200]}")
                raise HTTPException(status_code=404, detail="图片不存在或无法访问")
                
    except httpx.TimeoutException:
        logger.error("[Chunk Image] Request timeout")
        raise HTTPException(status_code=504, detail="请求超时")
    except Exception as e:
        logger.error(f"[Chunk Image] Error: {e}")
        raise HTTPException(status_code=500, detail=f"获取图片失败: {str(e)}")


# =============================================================================
# Chunks 搜索 API
# =============================================================================

@router.get("/search-chunks")
async def api_search_chunks(
    request: Request,
    keyword: str = "",
    dataset_id: str = "",
    page: int = 1,
    page_size: int = 10,
    similarity: float = 0.6
):
    """
    搜索 RAGFlow 知识库中的 chunks
    
    Args:
        keyword: 搜索关键词
        dataset_id: 指定知识库ID（可选）
        page: 页码
        page_size: 每页数量
        similarity: 相似度阈值
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    if not keyword.strip():
        return {
            "success": False,
            "message": "搜索关键词不能为空"
        }
    
    try:
        result = await search_chunks_from_ragflow(
            keyword=keyword,
            dataset_id=dataset_id,
            page=page,
            page_size=page_size,
            similarity_threshold=similarity,
            user_role=user.get("role", "reception")
        )
        
        if result.get("success"):
            return {
                "success": True,
                "chunks": result.get("chunks", []),
                "total": result.get("total", 0),
                "current_page": page,
                "total_pages": (result.get("total", 0) + page_size - 1) // page_size if result.get("total", 0) > 0 else 1,
                "page_size": page_size,
                "keyword": keyword
            }
        else:
            return {
                "success": False,
                "message": result.get("error", "搜索失败")
            }
            
    except Exception as e:
        logger.error(f"[Search Chunks] Error: {e}")
        return {
            "success": False,
            "message": f"搜索出错: {str(e)}"
        }
