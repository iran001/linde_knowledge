"""
页面路由 - 使用Jinja2模板渲染的页面
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, Dict, Any
import httpx

from config import (
    APP_INFO, PAGE_CONFIG, TEMPLATE_DIR,
    ROLE_LEVEL_MAP, ROLE_PROMPT_MAP, ROLE_DISPLAY_MAP, DIFY_CONFIG,
    DIFY_ROLE_INPUTS_MAP, RAGFLOW_CONFIG
)
from data_store import sessions, knowledge_upload_db
import json

# 创建路由器和模板
router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATE_DIR)


def get_user_role_level(role: str) -> int:
    """获取角色的权限级别"""
    return ROLE_LEVEL_MAP.get(role, 0)


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """从会话中获取当前用户"""
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        return sessions[session_id]
    return None


async def fetch_documents_from_api(
    role: str,
    keyword: str = "",
    page: int = 1,
    page_size: int = 10
) -> Dict[str, Any]:
    """
    从 RAGFlow API 获取文档列表
    
    Args:
        role: 用户角色 (admin, manager, reception)
        keyword: 搜索关键词
        page: 页码
        page_size: 每页数量
    
    Returns:
        Dict 包含 documents 列表和 total 总数
    """
    try:
        base_url = RAGFLOW_CONFIG["base_url"]
        dataset_id = RAGFLOW_CONFIG["dataset_id"]
        api_key = RAGFLOW_CONFIG["api_key"]
        
        # 构建 metadata_condition 用于权限过滤
        metadata_condition = {
            "logic": "and",
            "conditions": [
                {
                    "name": "role",
                    "comparison_operator": "is",
                    "value": role
                }
            ]
        }
        
        # 构建请求 URL
        url = f"{base_url}/datasets/{dataset_id}/documents"
        params = {
            "page": page,
            "page_size": page_size,
            "orderby": "create_time",
            "desc": "true",
            "keywords": keyword,
            "metadata_condition": json.dumps(metadata_condition, ensure_ascii=False)
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        print(f"[RAGFlow API] Fetching documents for role: {role}, page: {page}, keyword: {keyword}")
        
        async with httpx.AsyncClient(timeout=float(RAGFLOW_CONFIG.get("timeout", 30))) as client:
            response = await client.get(url, params=params, headers=headers)
            
            if response.status_code != 200:
                print(f"[RAGFlow API] Error: {response.status_code}, {response.text}")
                return {"documents": [], "total": 0}
            
            data = response.json()
            
            # 解析 API 响应
            if data.get("code") == 0:
                docs_data = data.get("data", {})
                docs = docs_data.get("docs", [])
                total = docs_data.get("total", 0)
                
                # 转换文档格式
                documents = []
                for doc in docs:
                    # 格式化更新日期
                    updated_at = doc.get("update_time") or doc.get("create_time")
                    formatted_date = _format_datetime(updated_at)
                    
                    documents.append({
                        "id": doc.get("id", ""),
                        "title": doc.get("name", "未命名文档"),
                        "content": doc.get("content", "") or doc.get("description", "暂无描述"),
                        "type": doc.get("type", "未知"),
                        "updated_at": formatted_date,
                        "permission_level": get_permission_level_by_role(role),
                        "chunk_count": doc.get("chunk_count", 0),
                        "token_count": doc.get("token_count", 0),
                        "progress": doc.get("progress", 0),
                        "progress_msg": doc.get("progress_msg", "")
                    })
                
                print(f"[RAGFlow API] Fetched {len(documents)} documents, total: {total}")
                return {"documents": documents, "total": total}
            else:
                print(f"[RAGFlow API] API Error: {data.get('message', 'Unknown error')}")
                return {"documents": [], "total": 0}
                
    except Exception as e:
        print(f"[RAGFlow API] Exception: {e}")
        return {"documents": [], "total": 0}


def _format_datetime(dt_value) -> str:
    """
    格式化日期时间为可读字符串
    支持时间戳(秒/毫秒)和ISO格式字符串
    """
    if not dt_value:
        return "未知"
    
    try:
        from datetime import datetime
        
        # 如果是数字（时间戳）
        if isinstance(dt_value, (int, float)):
            # 判断是秒还是毫秒（大于1e10认为是毫秒）
            if dt_value > 1e10:
                dt_value = dt_value / 1000
            dt = datetime.fromtimestamp(dt_value)
        # 如果是字符串（ISO格式）
        elif isinstance(dt_value, str):
            # 替换 Z 为 +00:00 以兼容 Python 3.6+
            dt_str = dt_value.replace('Z', '+00:00')
            # 尝试解析 ISO 格式
            try:
                dt = datetime.fromisoformat(dt_str)
            except:
                # 如果解析失败，直接返回原字符串
                return dt_value
        else:
            return str(dt_value)
        
        # 格式化为中文日期时间格式
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        # 格式化失败返回原值
        return str(dt_value)


def get_permission_level_by_role(role: str) -> int:
    """根据角色获取权限级别"""
    role_level_map = {
        "admin": 3,
        "manager": 2,
        "reception": 1
    }
    return role_level_map.get(role, 1)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页 - 未登录显示登录页，已登录重定向到聊天页"""
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/page/chat")
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "app_name": APP_INFO["name"],
        "logo": APP_INFO["logo"],
        "background_image": PAGE_CONFIG["login"]["background_image"],
        "error": None,
        "warning": None,
        "user": None
    })


@router.get("/page/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """智能对话页面"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    # 获取用户角色相关的 Dify 配置
    user_role = user.get("role", "reception")
    display_name = user.get("display_name", "访客")

    # 根据角色获取系统提示词和输入变量
    system_prompt = ROLE_PROMPT_MAP.get(user_role, ROLE_PROMPT_MAP["reception"])
    role_inputs = DIFY_ROLE_INPUTS_MAP.get(user_role, DIFY_ROLE_INPUTS_MAP["reception"])

    # 打印配置信息到控制台
    print("=" * 60)
    print(f"[Dify Chatbot Config] User: {display_name} (Role: {user_role})")
    print(f"[Dify Chatbot Config] system_prompt: {system_prompt}")
    print(f"[Dify Chatbot Config] role_inputs: {json.dumps(role_inputs, ensure_ascii=False)}")
    print("=" * 60)

    return templates.TemplateResponse("chat.html", {
        "request": request,
        "app_name": APP_INFO["name"],
        "logo": APP_INFO["logo"],
        "page_title": PAGE_CONFIG["chat"]["title"],
        "user": user,
        "active_page": "chat",
        # Dify API 配置
        "dify_config": DIFY_CONFIG,
        "role_inputs": json.dumps(role_inputs, ensure_ascii=False),
        "system_prompt": system_prompt,
        "user_role": user_role
    })


@router.get("/page/documents", response_class=HTMLResponse)
async def documents_page(request: Request):
    """文档中心页面 - 仅渲染页面框架，数据通过 AJAX 获取"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")
    
    return templates.TemplateResponse("documents.html", {
        "request": request,
        "app_name": APP_INFO["name"],
        "logo": APP_INFO["logo"],
        "page_title": PAGE_CONFIG["documents"]["title"],
        "user": user,
        "active_page": "documents"
    })


@router.get("/page/knowledge-upload", response_class=HTMLResponse)
async def knowledge_upload_page(request: Request):
    """文件上传页面"""
    from fastapi import HTTPException
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")
    
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    return templates.TemplateResponse("knowledge_upload.html", {
        "request": request,
        "app_name": APP_INFO["name"],
        "logo": APP_INFO["logo"],
        "page_title": PAGE_CONFIG["knowledge_upload"]["title"],
        "user": user,
        "active_page": "knowledge_upload",
        "knowledge_list": knowledge_upload_db
    })


@router.get("/page/search", response_class=HTMLResponse)
async def search_page(request: Request, keyword: str = ""):
    """知识搜索页面 - 用于对 RAGFlow chunks 进行搜索"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")
    
    return templates.TemplateResponse("search.html", {
        "request": request,
        "app_name": APP_INFO["name"],
        "logo": APP_INFO["logo"],
        "page_title": PAGE_CONFIG["search"]["title"],
        "user": user,
        "active_page": "search",
        "keyword": keyword,
        "dataset_id": RAGFLOW_CONFIG.get("dataset_id", ""),
        "vl_dataset_id": RAGFLOW_CONFIG.get("dataset2_id", "")
    })
