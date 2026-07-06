# -*- coding: utf-8 -*-
"""文本切片服务

策略:
1. 按 Markdown 标题(## 或 ###)分割（若识别到标题）
2. 否则按段落(连续两个换行)分割
3. 单个切片控制在 200-500 字符，过长则再按句子拆分
4. 切片间保留 50 字符重叠
"""
import re
from typing import List, Dict


DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50


def _split_by_headings(text: str) -> List[str]:
    """按 Markdown 标题分割"""
    lines = text.split("\n")
    chunks = []
    current = []
    for line in lines:
        if re.match(r"^#{1,3}\s+", line):
            if current:
                chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _split_by_paragraphs(text: str) -> List[str]:
    """按段落(连续两个换行)分割"""
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _split_by_sentences(text: str, max_size: int = DEFAULT_CHUNK_SIZE) -> List[str]:
    """
    按句子拆分，保证每段不超过 max_size 字符。
    中文句号、问号、感叹号、换行都是分割点。
    """
    # 先按句子分割
    sentences = re.split(r'(?<=[。！？\n])\s*', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks = []
    current = ""
    for s in sentences:
        if len(current) + len(s) <= max_size:
            current += s
        else:
            if current:
                chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    return chunks


def _add_overlap(chunks: List[str], overlap_chars: int = DEFAULT_OVERLAP) -> List[str]:
    """给相邻切片添加重叠"""
    if len(chunks) <= 1:
        return chunks
    result = []
    for i, chunk in enumerate(chunks):
        if i > 0:
            # 从前一片的尾部取 overlap_chars 字符作为前缀
            prefix = chunks[i - 1][-overlap_chars:] if len(chunks[i - 1]) > overlap_chars else chunks[i - 1]
            chunk = prefix + chunk
        result.append(chunk)
    return result


def chunk_document(text: str,
                   chunk_size: int = DEFAULT_CHUNK_SIZE,
                   overlap: int = DEFAULT_OVERLAP) -> List[Dict]:
    """
    将文档文本切片。

    返回: [{"index": 0, "text": "..."}, ...]
    """
    if not text or not text.strip():
        return []

    # Step 1: 尝试按标题分割
    heading_chunks = _split_by_headings(text)

    # Step 2: 如果标题分割结果太长，再按段落
    all_chunks = []
    for hc in heading_chunks:
        if len(hc) <= chunk_size:
            all_chunks.append(hc)
        else:
            para_chunks = _split_by_paragraphs(hc)
            for pc in para_chunks:
                if len(pc) <= chunk_size:
                    all_chunks.append(pc)
                else:
                    # 过长的段落按句子拆分
                    all_chunks.extend(_split_by_sentences(pc, chunk_size))

    # Step 3: 去空 + 去重（保留顺序）
    seen = set()
    unique = []
    for c in all_chunks:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            unique.append(c)

    # Step 4: 添加重叠
    final = _add_overlap(unique, overlap)

    # Step 5: 组装返回
    return [{"index": i, "text": t} for i, t in enumerate(final)]
