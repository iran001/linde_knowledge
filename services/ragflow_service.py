"""
RAGFlow API 服务 - 封装所有与 RAGFlow 平台的交互
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List

import httpx
from fastapi import UploadFile

from config import RAGFLOW_CONFIG

logger = logging.getLogger(__name__)


def _format_datetime(dt_value) -> str:
    """
    格式化日期时间为可读字符串
    支持时间戳(秒/毫秒)和ISO格式字符串
    """
    if not dt_value:
        return "未知"
    
    try:
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


# =============================================================================
# 文档列表获取
# =============================================================================

async def fetch_documents_from_api(
    role: str,
    keyword: str = "",
    page: int = 1,
    page_size: int = 10
) -> Dict[str, Any]:
    """
    从 RAGFlow API 获取文档列表
    - admin/manager 角色：从 dataset_id、vl_dataset_id 两个 dataset 查询并合并
    - reception 角色：仅从 dataset_id 查询
    """
    logger.info("\n" + "=" * 80)
    logger.info("[RAGFlow API] fetch_documents_from_api START")
    logger.info(f"[RAGFlow API] Input params: role={role}, keyword={keyword}, page={page}, page_size={page_size}")
    
    try:
        base_url = str(RAGFLOW_CONFIG["base_url"])
        dataset_id = str(RAGFLOW_CONFIG["dataset_id"])
        vl_dataset_id = str(RAGFLOW_CONFIG.get("vl_dataset_id", ""))
        api_key = str(RAGFLOW_CONFIG["api_key"])
        
        logger.info(f"[RAGFlow API] Configuration: base_url={base_url}, dataset_id={dataset_id}, vl_dataset_id={vl_dataset_id}")
        
        async with httpx.AsyncClient(timeout=float(RAGFLOW_CONFIG.get("timeout", 60))) as client:
            if role == "reception":
                return await _fetch_reception_documents(
                    client, base_url, api_key, dataset_id,
                    keyword, page, page_size
                )
            else:
                return await _fetch_admin_documents(
                    client, base_url, api_key, dataset_id, vl_dataset_id,
                    keyword, page, page_size, role
                )
                
    except Exception as e:
        logger.error(f"[RAGFlow API] Exception: {e}")
        logger.error(f"[RAGFlow API] Exception Type: {type(e).__name__}")
        import traceback
        logger.error(f"[RAGFlow API] Traceback: {traceback.format_exc()}")
        logger.info("=" * 80)
        return {"documents": [], "total": 0}


async def _fetch_reception_documents(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    dataset_id: str,
    keyword: str,
    page: int,
    page_size: int
) -> Dict[str, Any]:
    """获取 reception 角色的文档列表"""
    logger.info(f"[RAGFlow API] Role is 'reception', fetching from dataset_id")
    
    docs_from_primary = await _fetch_all_documents_from_dataset(
        client, base_url, dataset_id, api_key, keyword
    )
    
    logger.info(f"[RAGFlow API] Primary dataset: {len(docs_from_primary)} docs")
    
    # 设置权限级别
    all_documents = {}
    for doc in docs_from_primary:
        doc["permission_level"] = 1
        all_documents[doc["id"]] = doc
    
    return _paginate_documents(list(all_documents.values()), page, page_size)


async def _fetch_admin_documents(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    dataset_id: str,
    vl_dataset_id: str,
    keyword: str,
    page: int,
    page_size: int,
    role: str
) -> Dict[str, Any]:
    """获取 admin/manager 角色的文档列表"""
    logger.info(f"[RAGFlow API] Role is '{role}', fetching from dataset_id and vl_dataset_id")
    
    docs_from_primary = await _fetch_all_documents_from_dataset(
        client, base_url, dataset_id, api_key, keyword
    )
    docs_from_vl = await _fetch_all_documents_from_dataset(
        client, base_url, vl_dataset_id, api_key, keyword
    )
    
    logger.info(f"[RAGFlow API] Primary dataset: {len(docs_from_primary)} docs")
    logger.info(f"[RAGFlow API] VL dataset: {len(docs_from_vl)} docs")
    
    # 合并数据（按 id 去重）
    all_documents = {}
    permission_level = {"admin": 3, "manager": 2}.get(role, 2)
    
    for doc in docs_from_primary:
        doc["permission_level"] = permission_level
        all_documents[doc["id"]] = doc
    
    for doc in docs_from_vl:
        doc["permission_level"] = permission_level
        if doc["id"] not in all_documents:
            all_documents[doc["id"]] = doc
    
    return _paginate_documents(list(all_documents.values()), page, page_size)


def _paginate_documents(documents: List[Dict], page: int, page_size: int) -> Dict[str, Any]:
    """对文档列表进行排序和分页"""
    documents.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    total = len(documents)
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_docs = documents[start_idx:end_idx]
    
    logger.info(f"[RAGFlow API] Merged: {len(documents)} unique documents")
    logger.info(f"[RAGFlow API] Paginated: page {page}, showing {len(paginated_docs)} of {total} docs")
    logger.info("=" * 80)
    
    return {"documents": paginated_docs, "total": total}


async def _fetch_all_documents_from_dataset(
    client: httpx.AsyncClient,
    base_url: str,
    dataset_id: str,
    api_key: str,
    keyword: str
) -> List[Dict[str, Any]]:
    """从单个 dataset 获取所有文档（处理分页获取全部）"""
    all_docs = []
    page = 1
    page_size = 100
    
    logger.info(f"[RAGFlow API] Starting fetch all documents from dataset: {dataset_id}")
    
    while True:
        result = await _fetch_single_dataset(
            client, base_url, dataset_id, api_key, keyword, page, page_size
        )
        
        docs = result.get("documents", [])
        if not docs:
            logger.info(f"[RAGFlow API] No more documents at page {page}")
            break
        
        all_docs.extend(docs)
        logger.info(f"[RAGFlow API] Page {page}: Added {len(docs)} docs, total collected: {len(all_docs)}")
        
        if len(docs) < page_size:
            logger.info(f"[RAGFlow API] Last page reached at page {page}")
            break
        
        page += 1
        
        # 安全限制：最多获取 1000 条
        if len(all_docs) >= 1000:
            logger.warning(f"[RAGFlow API] Reached maximum limit (1000) for dataset {dataset_id}")
            break
    
    logger.info(f"[RAGFlow API] Completed fetch from dataset {dataset_id}: {len(all_docs)} documents total")
    return all_docs


async def _fetch_single_dataset(
    client: httpx.AsyncClient,
    base_url: str,
    dataset_id: str,
    api_key: str,
    keyword: str,
    page: int,
    page_size: int
) -> Dict[str, Any]:
    """从单个 RAGFlow dataset 获取文档列表"""
    url = f"{base_url}/datasets/{dataset_id}/documents"
    params = {
        "page": page,
        "page_size": page_size,
        "orderby": "create_time",
        "desc": "true",
        "keywords": keyword
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    
    logger.info("=" * 60)
    logger.info("[RAGFlow API] REQUEST - Fetch Single Dataset")
    logger.info(f"[RAGFlow API] Dataset ID: {dataset_id}")
    logger.info(f"[RAGFlow API] URL: {url}")
    logger.info(f"[RAGFlow API] Method: GET")
    logger.info(f"[RAGFlow API] Params: {json.dumps(params, ensure_ascii=False)}")
    logger.info(f"[RAGFlow API] Headers: {json.dumps({'Authorization': 'Bearer ***'}, ensure_ascii=False)}")
    
    response = await client.get(url, params=params, headers=headers)
    
    logger.info("[RAGFlow API] RESPONSE")
    logger.info(f"[RAGFlow API] Status Code: {response.status_code}")
    
    if response.status_code != 200:
        logger.error(f"[RAGFlow API] HTTP Error from dataset {dataset_id}: {response.status_code}")
        logger.error(f"[RAGFlow API] Error Response: {response.text[:500]}")
        return {"documents": [], "total": 0}
    
    data = response.json()
    logger.info(f"[RAGFlow API] Response Body: {json.dumps(data, ensure_ascii=False)[:1000]}...")
    
    if data.get("code") != 0:
        logger.error(f"[RAGFlow API] API Error from dataset {dataset_id}: code={data.get('code')}, message={data.get('message', 'Unknown')}")
        return {"documents": [], "total": 0}
    
    return _parse_document_response(data)


def _parse_document_response(data: Dict) -> Dict[str, Any]:
    """解析 RAGFlow 文档响应"""
    docs_data = data.get("data", {})
    docs = docs_data.get("docs", [])
    total = docs_data.get("total", 0)
    
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
            "chunk_count": doc.get("chunk_count", 0),
            "token_count": doc.get("token_count", 0),
            "progress": doc.get("progress", 0),
            "progress_msg": doc.get("progress_msg", ""),
            "run": doc.get("run", ""),
            "status": doc.get("status", "")
        })
    
    logger.info(f"[RAGFlow API] Fetched {len(documents)} documents, total: {total}")
    return {"documents": documents, "total": total}


# =============================================================================
# 文档上传
# =============================================================================

async def upload_to_ragflow(file: UploadFile, file_content: bytes) -> Dict[str, Any]:
    """上传文件到 RAGFlow"""
    try:
        base_url = str(RAGFLOW_CONFIG.get("base_url", ""))
        api_key = str(RAGFLOW_CONFIG.get("api_key", ""))
        dataset_id = str(RAGFLOW_CONFIG.get("dataset_id", ""))
        
        url = f"{base_url}/datasets/{dataset_id}/documents"
        
        headers = {"Authorization": f"Bearer {api_key}"}
        files = {
            "file": (file.filename, file_content, file.content_type or "application/octet-stream")
        }
        data = {
            "parser_config": '{"chunk_token_num": 512, "layout_recognize": true}'
        }
        
        _log_upload_request(url, file, len(file_content), data)
        
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, files=files, data=data)
            
            logger.info("[RAGFlow Upload] RESPONSE")
            logger.info(f"[RAGFlow Upload] Status Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[RAGFlow Upload] Response Body: {json.dumps(result, ensure_ascii=False)[:2000]}...")
                
                # 获取上传成功的 document_ids
                document_ids = _extract_document_ids(result)
                if document_ids:
                    logger.info(f"[RAGFlow Upload] Extracted document_ids: {document_ids}")
                    # 调用文档解析 API
                    parse_result = await _parse_documents(client, base_url, dataset_id, api_key, document_ids)
                    logger.info(f"[RAGFlow Upload] Parse result: {parse_result}")
                else:
                    logger.warning("[RAGFlow Upload] No document_ids found in response, skipping parse")
                
                logger.info("[RAGFlow Upload] Upload successful")
                return {"success": True, "data": result}
            else:
                error_text = response.text
                logger.error(f"[RAGFlow Upload] HTTP Error: {response.status_code}")
                logger.error(f"[RAGFlow Upload] Error Response: {error_text}")
                return {"success": False, "error": f"HTTP {response.status_code}: {error_text}"}
                
    except Exception as e:
        logger.error(f"[RAGFlow Upload] Exception: {e}")
        logger.error(f"[RAGFlow Upload] Exception Type: {type(e).__name__}")
        import traceback
        logger.error(f"[RAGFlow Upload] Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


def _log_upload_request(url: str, file: UploadFile, file_size: int, data: Dict):
    """记录上传请求日志"""
    logger.info("=" * 80)
    logger.info("[RAGFlow Upload] REQUEST")
    logger.info(f"[RAGFlow Upload] URL: {url}")
    logger.info(f"[RAGFlow Upload] Method: POST")
    logger.info(f"[RAGFlow Upload] Headers: {json.dumps({'Authorization': 'Bearer ***'}, ensure_ascii=False)}")
    logger.info(f"[RAGFlow Upload] Filename: {file.filename}")
    logger.info(f"[RAGFlow Upload] Content-Type: {file.content_type}")
    logger.info(f"[RAGFlow Upload] File Size: {file_size} bytes")
    logger.info(f"[RAGFlow Upload] Parser Config: {data['parser_config']}")
    logger.info("=" * 80)


def _extract_document_ids(result: Dict[str, Any]) -> List[str]:
    """从上传响应中提取 document_ids"""
    document_ids = []
    try:
        # 根据 RAGFlow 响应结构提取 document_ids
        # 通常在 data 字段下的 docs 数组中
        docs = result.get("data", [])
        for doc in docs:
            doc_id = doc.get("id")
            if doc_id:
                document_ids.append(doc_id)
    except Exception as e:
        logger.error(f"[RAGFlow Upload] Error extracting document_ids: {e}")
    return document_ids


async def _parse_documents(
    client: httpx.AsyncClient,
    base_url: str,
    dataset_id: str,
    api_key: str,
    document_ids: List[str]
) -> Dict[str, Any]:
    """
    调用 RAGFlow 文档解析 API
    POST /api/v1/datasets/{dataset_id}/chunks
    """
    try:
        url = f"{base_url}/datasets/{dataset_id}/chunks"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "document_ids": document_ids
        }
        
        logger.info("=" * 80)
        logger.info("[RAGFlow Parse] REQUEST")
        logger.info(f"[RAGFlow Parse] URL: {url}")
        logger.info(f"[RAGFlow Parse] Document IDs: {document_ids}")
        
        response = await client.post(url, headers=headers, json=payload)
        
        logger.info("[RAGFlow Parse] RESPONSE")
        logger.info(f"[RAGFlow Parse] Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"[RAGFlow Parse] Response: {json.dumps(result, ensure_ascii=False)[:1000]}...")
            logger.info("[RAGFlow Parse] Parse request sent successfully")
            return {"success": True, "data": result}
        else:
            error_text = response.text
            logger.error(f"[RAGFlow Parse] HTTP Error: {response.status_code}")
            logger.error(f"[RAGFlow Parse] Error Response: {error_text}")
            return {"success": False, "error": f"HTTP {response.status_code}: {error_text}"}
            
    except Exception as e:
        logger.error(f"[RAGFlow Parse] Exception: {e}")
        logger.error(f"[RAGFlow Parse] Exception Type: {type(e).__name__}")
        import traceback
        logger.error(f"[RAGFlow Parse] Traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Chunks 搜索功能
# =============================================================================

async def search_chunks_from_ragflow(
    keyword: str,
    dataset_id: str = "",
    page: int = 1,
    page_size: int = 10,
    similarity_threshold: float = 0.6,
    user_role: str = "reception"
) -> Dict[str, Any]:
    """
    从 RAGFlow 搜索 chunks
    
    Args:
        keyword: 搜索关键词
        dataset_id: 指定知识库ID（可选，为空则搜索所有可用知识库）
        page: 页码
        page_size: 每页数量
        similarity_threshold: 相似度阈值
        user_role: 用户角色，用于权限控制
    
    Returns:
        Dict 包含 chunks 列表和总数
    """
    logger.info("\n" + "=" * 80)
    logger.info("[RAGFlow Search] search_chunks_from_ragflow START")
    logger.info(f"[RAGFlow Search] Input params: keyword={keyword}, dataset_id={dataset_id}, page={page}, page_size={page_size}, similarity={similarity_threshold}, role={user_role}")
    
    try:
        base_url = str(RAGFLOW_CONFIG["base_url"])
        api_key = str(RAGFLOW_CONFIG["api_key"])
        default_dataset_id = str(RAGFLOW_CONFIG.get("dataset_id", ""))
        vl_dataset_id = str(RAGFLOW_CONFIG.get("vl_dataset_id", ""))
        
        # 根据角色确定要搜索的知识库
        datasets_to_search = []
        if dataset_id:
            # 如果指定了知识库，只搜索该知识库
            datasets_to_search = [dataset_id]
        else:
            # 根据角色确定可搜索的知识库
            if user_role in ["admin", "manager"]:
                datasets_to_search = [d for d in [default_dataset_id, vl_dataset_id] if d]
            else:
                # reception 只能搜索默认知识库
                datasets_to_search = [default_dataset_id] if default_dataset_id else []
        
        if not datasets_to_search:
            logger.warning("[RAGFlow Search] No available datasets for search")
            return {"success": True, "chunks": [], "total": 0}
        
        logger.info(f"[RAGFlow Search] Will search in datasets: {datasets_to_search}")
        
        async with httpx.AsyncClient(timeout=float(RAGFLOW_CONFIG.get("timeout", 60))) as client:
            # 同时查询所有知识库
            all_chunks = await _search_chunks_in_datasets(
                client, base_url, api_key, datasets_to_search, keyword, similarity_threshold
            )
            logger.info(f"[RAGFlow Search] Total found {len(all_chunks)} chunks from all datasets")
        
        # 按相似度排序
        all_chunks.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        
        # 分页
        total = len(all_chunks)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_chunks = all_chunks[start_idx:end_idx]
        
        logger.info(f"[RAGFlow Search] Total chunks: {total}, returning page {page} with {len(paginated_chunks)} items")
        logger.info("=" * 80)
        
        return {
            "success": True,
            "chunks": paginated_chunks,
            "total": total
        }
        
    except Exception as e:
        logger.error(f"[RAGFlow Search] Exception: {e}")
        logger.error(f"[RAGFlow Search] Exception Type: {type(e).__name__}")
        import traceback
        logger.error(f"[RAGFlow Search] Traceback: {traceback.format_exc()}")
        logger.info("=" * 80)
        return {"success": False, "error": str(e)}


async def _search_chunks_in_datasets(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    dataset_ids: List[str],
    keyword: str,
    similarity_threshold: float
) -> List[Dict[str, Any]]:
    """
    在多个数据集中同时搜索 chunks
    
    使用 RAGFlow 的 retrieval API 进行语义检索，一次查询所有指定的知识库
    """
    try:
        # 获取所有数据集中的文档映射
        doc_map = {}
        for ds_id in dataset_ids:
            ds_doc_map = await _get_documents_map_in_dataset(client, base_url, api_key, ds_id)
            doc_map.update(ds_doc_map)
            logger.info(f"[RAGFlow Search] Loaded {len(ds_doc_map)} documents map for dataset {ds_id}")
        
        logger.info(f"[RAGFlow Search] Total documents map: {len(doc_map)} entries")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # RAGFlow retrieval API 请求参数 - 同时查询所有数据集
        payload = {
            "dataset_ids": dataset_ids,
            "question": keyword,
            "similarity_threshold": float(similarity_threshold),
            "top_k": 100,
            "rerank_id": ""
        }
        
        # 使用 /api/v1/retrieval 端点
        url = f"{base_url}/retrieval"
        
        logger.info(f"[RAGFlow Search] POST {url}")
        logger.info(f"[RAGFlow Search] Payload: {json.dumps(payload, ensure_ascii=False)}")
        
        response = await client.post(url, headers=headers, json=payload, timeout=30)
        logger.info(f"[RAGFlow Search] Response status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"[RAGFlow Search] HTTP Error: {response.status_code}")
            logger.error(f"[RAGFlow Search] Error Response: {response.text[:500]}")
            return []
        
        data = response.json()
        logger.info(f"[RAGFlow Search] Response code: {data.get('code')}, message: {data.get('message', 'None')}")
        
        if data.get("code") != 0:
            logger.error(f"[RAGFlow Search] API Error: code={data.get('code')}, message={data.get('message', 'Unknown')}")
            return []
        
        # 解析响应数据
        response_data = data.get("data", {})
        logger.info(f"[RAGFlow Search] Response data type: {type(response_data).__name__}")
        
        chunk_list = []
        if isinstance(response_data, list):
            chunk_list = response_data
            logger.info(f"[RAGFlow Search] Data is list with {len(chunk_list)} items")
        elif isinstance(response_data, dict):
            # 尝试多种可能的键名
            for key in ["chunks", "retrieval", "results", "data", "items", "list"]:
                if key in response_data:
                    chunk_list = response_data[key]
                    logger.info(f"[RAGFlow Search] Found chunks in key '{key}': {len(chunk_list)} items")
                    break
            if not chunk_list:
                logger.info(f"[RAGFlow Search] No chunks found in data keys: {list(response_data.keys())}")
        
        logger.info(f"[RAGFlow Search] Total chunks found: {len(chunk_list)}")
        
        if not chunk_list:
            return []
        
        chunks = []
        for chunk in chunk_list:
            doc_id = chunk.get("document_id", "")
            # 从映射中获取文档名称，如果不存在则使用 API 返回的或默认值
            doc_name = doc_map.get(doc_id) or chunk.get("document_name") or chunk.get("doc_name") or "未命名文档"
            # 获取 chunk 所属的数据集ID
            chunk_dataset_id = chunk.get("dataset_id", "")
            
            # 提取 image_id 并构造图片 URL
            image_id = chunk.get("image_id", "")
            image_url = ""
            if image_id:
                # RAGFlow 图片获取 URL 格式
                image_url = f"{base_url}/document/image?image_id={image_id}"
            
            chunk_data = {
                "id": chunk.get("chunk_id", chunk.get("id", "")),
                "content": chunk.get("content", chunk.get("text", "")),
                "document_id": doc_id,
                "document_name": doc_name,
                "dataset_id": chunk_dataset_id,
                "dataset_name": _get_dataset_name(chunk_dataset_id),
                "similarity": chunk.get("similarity", chunk.get("score", 0)),
                "position": chunk.get("position", chunk.get("page", [])),
                "content_length": len(chunk.get("content", chunk.get("text", ""))),
                "image_id": image_id,
                "image_url": image_url
            }
            chunks.append(chunk_data)
        
        logger.info(f"[RAGFlow Search] Parsed {len(chunks)} chunks from response")
        return chunks
        
    except Exception as e:
        logger.error(f"[RAGFlow Search] Error searching in datasets {dataset_ids}: {e}")
        return []


async def _get_documents_map_in_dataset(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    dataset_id: str
) -> Dict[str, str]:
    """
    获取数据集中所有文档的 ID 和名称映射
    
    Returns:
        Dict[document_id, document_name]
    """
    try:
        url = f"{base_url}/datasets/{dataset_id}/documents"
        params = {
            "page": 1,
            "page_size": 1000,  # 获取足够多的文档
            "orderby": "create_time",
            "desc": "true"
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        
        logger.info(f"[RAGFlow Search] Fetching documents for dataset: {dataset_id}")
        
        response = await client.get(url, params=params, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"[RAGFlow Search] Failed to fetch documents: {response.status_code}")
            return {}
        
        data = response.json()
        
        if data.get("code") != 0:
            logger.error(f"[RAGFlow Search] API error fetching documents: {data.get('message')}")
            return {}
        
        # 构建文档映射
        doc_map = {}
        docs_data = data.get("data", {})
        docs = docs_data.get("docs", [])
        
        for doc in docs:
            doc_id = doc.get("id", "")
            doc_name = doc.get("name", "")
            if doc_id and doc_name:
                doc_map[doc_id] = doc_name
        
        logger.info(f"[RAGFlow Search] Built document map with {len(doc_map)} entries")
        return doc_map
        
    except Exception as e:
        logger.error(f"[RAGFlow Search] Error building document map: {e}")
        return {}


def _get_dataset_name(dataset_id: str) -> str:
    """根据 dataset_id 获取数据集名称"""
    default_id = RAGFLOW_CONFIG.get("dataset_id", "")
    vl_id = RAGFLOW_CONFIG.get("vl_dataset_id", "")
    
    if dataset_id == default_id:
        return "默认知识库"
    elif dataset_id == vl_id:
        return "VL 知识库"
    else:
        return "知识库"
