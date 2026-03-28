"""
上传 Summary 文件夹中的文件到 Dify
功能：
1. 读取 summary 文件夹中的所有文件
2. 调用 Dify 文件上传 API (/files/upload)
3. 将返回的 file_id 和文件名记录到 config.py 中

使用方法：
    python upload_summary_to_dify.py
"""

import os
import sys
import json
import glob
import mimetypes
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加项目根目录到路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import DIFY_CONFIG

# =============================================================================
# 配置
# =============================================================================
SUMMARY_DIR = os.path.join(BASE_DIR, "summary")
CONFIG_FILE = os.path.join(BASE_DIR, "config.py")


def get_dify_config() -> Dict[str, Any]:
    """获取 Dify 配置"""
    return {
        "base_url": DIFY_CONFIG.get("base_url", "").rstrip("/"),
        "api_key": DIFY_CONFIG.get("api_key", ""),
        "upload_endpoint": DIFY_CONFIG.get("upload_endpoint", "/files/upload"),
        "timeout": DIFY_CONFIG.get("timeout", 30)
    }


def get_summary_files() -> List[str]:
    """获取 summary 文件夹中的所有文件"""
    if not os.path.exists(SUMMARY_DIR):
        print(f"[错误] Summary 目录不存在: {SUMMARY_DIR}")
        return []
    
    # 支持的文件类型
    extensions = ['*.txt', '*.md', '*.doc', '*.docx', '*.pdf', '*.json', '*.csv']
    files = []
    
    for ext in extensions:
        files.extend(glob.glob(os.path.join(SUMMARY_DIR, ext)))
    
    # 也获取所有文件（不限制扩展名）
    all_files = glob.glob(os.path.join(SUMMARY_DIR, "*"))
    files = list(set([f for f in all_files if os.path.isfile(f)]))
    
    files.sort()
    print(f"[信息] 在 {SUMMARY_DIR} 中找到 {len(files)} 个文件")
    for f in files:
        print(f"  - {os.path.basename(f)}")
    return files


def upload_file_to_dify(file_path: str, config: Dict[str, Any]) -> Optional[str]:
    """
    上传单个文件到 Dify
    
    Args:
        file_path: 本地文件路径
        config: Dify 配置
        
    Returns:
        成功返回 file_id，失败返回 None
    """
    filename = os.path.basename(file_path)
    url = f"{config['base_url']}{config['upload_endpoint']}"
    
    # 检测 MIME 类型
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        # 根据扩展名默认使用 text/plain
        ext = os.path.splitext(filename)[1].lower()
        mime_type = {
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.pdf': 'application/pdf',
            '.json': 'application/json',
            '.csv': 'text/csv'
        }.get(ext, 'application/octet-stream')
    
    print(f"\n[上传] {filename}")
    print(f"[信息] URL: {url}")
    print(f"[信息] MIME Type: {mime_type}")
    
    headers = {
        "Authorization": f"Bearer {config['api_key']}"
    }
    
    try:
        with open(file_path, 'rb') as f:
            files = {
                'file': (filename, f, mime_type)
            }
            
            response = requests.post(
                url,
                headers=headers,
                files=files,
                timeout=config['timeout']
            )
        
        print(f"[响应] Status: {response.status_code}")
        
        if response.status_code == 200 or response.status_code == 201:
            data = response.json()
            print(f"[响应] Body: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
            # 获取 file_id
            file_id = data.get('id')
            if file_id:
                print(f"[成功] 文件上传成功，ID: {file_id}")
                return file_id
            else:
                print(f"[错误] 响应中没有 id 字段")
                return None
        else:
            print(f"[错误] HTTP {response.status_code}: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"[错误] 请求超时")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[错误] 请求异常: {e}")
        return None
    except Exception as e:
        print(f"[错误] 未知异常: {e}")
        return None


def read_config_content() -> str:
    """读取 config.py 文件内容"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return f.read()


def write_config_content(content: str):
    """写入 config.py 文件内容"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(content)


def update_config_with_uploaded_files(uploaded_files: Dict[str, str], mode: str = "incremental"):
    """
    更新 config.py 文件，添加或更新 DIFY_UPLOADED_FILES 配置
    
    Args:
        uploaded_files: {文件名: file_id} 的字典（本次上传的文件）
        mode: 更新模式
            - "incremental": 增量更新，保留已有配置，只更新/添加新文件（默认）
            - "replace": 完全替换，只保留本次上传的文件
    """
    print("\n[信息] 正在更新 config.py...")
    
    config_content = read_config_content()
    
    # 尝试从现有配置中读取已上传的文件映射
    existing_files: Dict[str, str] = {}
    if mode == "incremental" and "DIFY_UPLOADED_FILES" in config_content:
        try:
            import re
            # 尝试匹配 DIFY_UPLOADED_FILES = {...}
            pattern = r'DIFY_UPLOADED_FILES:.*?Dict\[str, str\].*?=\s*(\{.*?\})'
            match = re.search(pattern, config_content, re.DOTALL)
            if match:
                dict_str = match.group(1)
                existing_files = json.loads(dict_str)
                print(f"[信息] 发现已有 {len(existing_files)} 个文件配置，将增量更新")
        except Exception as e:
            print(f"[警告] 读取现有配置失败: {e}，将创建新配置")
    
    # 合并配置：保留现有文件，更新/添加新文件
    merged_files = existing_files.copy()
    updated_count = 0
    added_count = 0
    
    for filename, file_id in uploaded_files.items():
        if filename in merged_files:
            if merged_files[filename] != file_id:
                print(f"[更新] {filename}: {merged_files[filename][:8]}... -> {file_id[:8]}...")
                updated_count += 1
            merged_files[filename] = file_id
        else:
            print(f"[添加] {filename}: {file_id[:8]}...")
            merged_files[filename] = file_id
            added_count += 1
    
    # 准备新的配置项
    new_config = f"""
# =============================================================================
# Dify 已上传文件记录（自动生成的文件 ID 映射）
# 文件名 -> Dify file_id
# =============================================================================
DIFY_UPLOADED_FILES: Dict[str, str] = {json.dumps(merged_files, ensure_ascii=False, indent=4)}
"""
    
    # 检查是否已存在 DIFY_UPLOADED_FILES 配置
    if "DIFY_UPLOADED_FILES" in config_content:
        # 替换现有的配置
        import re
        # 使用正则表达式替换整个 DIFY_UPLOADED_FILES 定义
        pattern = r'DIFY_UPLOADED_FILES:.*?Dict\[str, str\].*?=.*?\{[^}]*\}'
        replacement = f'DIFY_UPLOADED_FILES: Dict[str, str] = {json.dumps(merged_files, ensure_ascii=False, indent=4)}'
        
        # 如果上面的正则不匹配，尝试匹配多行格式
        if not re.search(pattern, config_content, re.DOTALL):
            pattern = r'DIFY_UPLOADED_FILES:.*?=.*?\{.*?\}'
        
        new_content = re.sub(pattern, replacement, config_content, flags=re.DOTALL)
        
        # 如果替换失败（格式不匹配），则追加到文件末尾
        if new_content == config_content:
            print("[警告] 无法替换现有配置，将追加新配置")
            # 移除旧的 DIFY_UPLOADED_FILES 定义
            lines = config_content.split('\n')
            new_lines = []
            skip = False
            for line in lines:
                if 'DIFY_UPLOADED_FILES' in line or (skip and line.strip() and not line.startswith('#')):
                    if 'DIFY_UPLOADED_FILES' in line:
                        skip = True
                    continue
                skip = False
                new_lines.append(line)
            new_content = '\n'.join(new_lines) + new_config
    else:
        # 在文件末尾添加新配置
        new_content = config_content.rstrip() + '\n' + new_config
    
    write_config_content(new_content)
    print("[成功] config.py 已更新")
    print(f"[统计] 新增: {added_count}, 更新: {updated_count}, 总计: {len(merged_files)}")


def main():
    """主函数"""
    print("=" * 80)
    print("上传 Summary 文件到 Dify")
    print("=" * 80)
    
    # 获取配置
    config = get_dify_config()
    print(f"\n[配置]")
    print(f"  Base URL: {config['base_url']}")
    print(f"  Upload Endpoint: {config['upload_endpoint']}")
    print(f"  API Key: {'*' * 10}{config['api_key'][-4:] if config['api_key'] else '未设置'}")
    
    # 获取 summary 文件列表
    files = get_summary_files()
    
    if not files:
        print("\n[警告] 没有找到可上传的文件")
        return
    
    # 上传文件并收集结果
    uploaded_files: Dict[str, str] = {}
    success_count = 0
    fail_count = 0
    
    for file_path in files:
        filename = os.path.basename(file_path)
        file_id = upload_file_to_dify(file_path, config)
        
        if file_id:
            uploaded_files[filename] = file_id
            success_count += 1
        else:
            fail_count += 1
    
    # 更新 config.py（增量更新模式：保留已有配置，只更新/添加新文件）
    if uploaded_files:
        update_config_with_uploaded_files(uploaded_files, mode="incremental")
    
    # 输出统计
    print("\n" + "=" * 80)
    print("上传完成")
    print("=" * 80)
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"总计: {len(files)}")
    
    if uploaded_files:
        print("\n已记录的文件映射:")
        for filename, file_id in uploaded_files.items():
            print(f"  {filename} -> {file_id}")


if __name__ == "__main__":
    main()
