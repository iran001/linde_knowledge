"""
文本相似度服务 - 用于本地快速预筛选相似文件
使用 Jaccard 相似度和关键词匹配，无需外部 API
"""

import os
import re
import glob
import logging
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FileSimilarity:
    """文件相似度结果"""
    filename: str
    file_id: str
    content: str
    similarity_score: float  # 0-1 之间的相似度分数
    keyword_match_count: int  # 关键词匹配数量


def _extract_keywords(text: str) -> Set[str]:
    """
    提取文本中的关键词（中文和英文）
    - 提取 2-8 个字符的词组
    - 过滤常见停用词
    """
    if not text:
        return set()
    
    # 转换为小写并清理
    text = text.lower()
    # 移除特殊字符，保留中英文和数字
    text = re.sub(r'[^\u4e00-\u9fa5a-z0-9\s]', ' ', text)
    
    keywords = set()
    
    # 提取中文词语（2-8个字符）
    chinese_chars = re.findall(r'[\u4e00-\u9fa5]{2,8}', text)
    keywords.update(chinese_chars)
    
    # 提取英文单词（3-20个字符）
    english_words = re.findall(r'\b[a-z]{3,20}\b', text)
    # 过滤常见停用词
    stopwords = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use', 'with', 'have', 'this', 'will', 'your', 'from', 'they', 'know', 'want', 'been', 'good', 'much', 'some', 'time', 'very', 'when', 'come', 'here', 'just', 'like', 'long', 'make', 'many', 'over', 'such', 'take', 'than', 'them', 'well', 'were', 'what', 'would', 'there', 'could', 'other', 'after', 'first', 'never', 'these', 'think', 'where', 'being', 'every', 'great', 'might', 'shall', 'still', 'those', 'while', 'zh-cn', 'txt', 'pdf', 'doc', 'docx', 'ihg', 'hotel', 'and', 'the', 'for'
    }
    english_words = [w for w in english_words if w not in stopwords]
    keywords.update(english_words)
    
    # 提取数字编号（如 2025, Q1, 1028 等）
    numbers = re.findall(r'\b(20\d{2}|q[1-4]|\d{3,4})\b', text)
    keywords.update(numbers)
    
    return keywords


def _calculate_jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """计算两个集合的 Jaccard 相似度"""
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def _calculate_text_similarity(text1: str, text2: str) -> Tuple[float, int]:
    """
    计算两段文本的相似度
    
    Returns:
        (similarity_score, keyword_match_count)
    """
    keywords1 = _extract_keywords(text1)
    keywords2 = _extract_keywords(text2)
    
    # Jaccard 相似度
    jaccard_score = _calculate_jaccard_similarity(keywords1, keywords2)
    
    # 关键词匹配数量
    match_count = len(keywords1 & keywords2)
    
    # 综合评分：Jaccard 相似度 * 0.7 + 匹配数量归一化 * 0.3
    # 假设最多匹配 50 个关键词为满分
    normalized_match = min(match_count / 50, 1.0)
    final_score = jaccard_score * 0.7 + normalized_match * 0.3
    
    return final_score, match_count


def load_summary_files_content() -> Dict[str, str]:
    """
    加载所有 summary 文件的内容
    
    Returns:
        {filename: content}
    """
    summary_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "summary")
    
    if not os.path.exists(summary_dir):
        logger.warning(f"[Similarity] Summary directory not found: {summary_dir}")
        return {}
    
    file_contents = {}
    
    # 获取所有文本文件
    for ext in ['*.txt', '*.md']:
        files = glob.glob(os.path.join(summary_dir, ext))
        for file_path in files:
            filename = os.path.basename(file_path)
            try:
                # 只读取前 5000 字符用于相似度计算（提高效率）
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(5000)
                    file_contents[filename] = content
            except Exception as e:
                logger.error(f"[Similarity] Error reading file {filename}: {e}")
    
    logger.info(f"[Similarity] Loaded {len(file_contents)} summary files for comparison")
    return file_contents


def find_top_similar_files(
    new_file_content: str,
    existing_files: Dict[str, str],
    existing_file_ids: Dict[str, str],
    top_k: int = 5,
    similarity_threshold: float = 0.05
) -> List[FileSimilarity]:
    """
    找出与新文件最相似的 Top-K 个文件
    
    Args:
        new_file_content: 新文件内容
        existing_files: {filename: content} 已有文件内容
        existing_file_ids: {filename: file_id} 已有文件的 Dify file_id
        top_k: 返回最相似的前 K 个文件
        similarity_threshold: 相似度阈值，低于此值的文件将被过滤
    
    Returns:
        按相似度排序的文件列表
    """
    if not existing_files:
        logger.info("[Similarity] No existing files to compare")
        return []
    
    logger.info(f"[Similarity] Comparing with {len(existing_files)} files, will return top {top_k}")
    
    similarities = []
    
    for filename, content in existing_files.items():
        score, match_count = _calculate_text_similarity(new_file_content, content)
        
        # 只保留高于阈值的文件
        if score >= similarity_threshold:
            similarities.append(FileSimilarity(
                filename=filename,
                file_id=existing_file_ids.get(filename, ""),
                content=content,
                similarity_score=score,
                keyword_match_count=match_count
            ))
    
    # 按相似度排序（降序）
    similarities.sort(key=lambda x: x.similarity_score, reverse=True)
    
    # 取前 K 个
    top_results = similarities[:top_k]
    
    logger.info(f"[Similarity] Found {len(similarities)} files above threshold, returning top {len(top_results)}")
    for i, result in enumerate(top_results, 1):
        logger.info(f"[Similarity] #{i}: {result.filename} (score: {result.similarity_score:.3f}, matches: {result.keyword_match_count})")
    
    return top_results


def quick_conflict_check_by_similarity(
    new_file_content: str,
    existing_files: Dict[str, str],
    high_similarity_threshold: float = 0.3
) -> Tuple[bool, List[str]]:
    """
    快速冲突检查 - 基于高相似度判断
    
    如果新文件与某个已有文件的相似度超过阈值，认为可能存在冲突
    
    Returns:
        (has_potential_conflict, list_of_suspicious_files)
    """
    suspicious_files = []
    
    for filename, content in existing_files.items():
        score, _ = _calculate_text_similarity(new_file_content, content)
        if score >= high_similarity_threshold:
            suspicious_files.append(filename)
    
    has_conflict = len(suspicious_files) > 0
    
    if has_conflict:
        logger.info(f"[Similarity] High similarity detected with {len(suspicious_files)} files: {suspicious_files}")
    else:
        logger.info("[Similarity] No high similarity files detected")
    
    return has_conflict, suspicious_files
