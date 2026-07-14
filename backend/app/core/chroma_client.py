"""
Chroma 向量数据库客户端初始化

- 使用持久化模式，数据存储在项目根目录下的 chroma_db/ 文件夹
- 对外提供 get_collection() 单例
- collection 名称: "knowledge_base"
"""

import contextlib
import os

import chromadb
from chromadb.config import Settings

# 持久化目录（项目根目录下的 chroma_db/）
_CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "chroma_db")

_client = None
_collection = None


def get_chroma_client() -> chromadb.PersistentClient:
    """获取 Chroma 持久化客户端（单例）"""
    global _client
    if _client is None:
        os.makedirs(_CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=_CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_knowledge_collection():
    """
    获取知识库 collection（单例）
    collection 包含的 metadata 字段:
      - doc_id:    kb_document 表主键
      - doc_title: 文档标题
      - doc_type:  文档类型
      - chunk_index: 切片序号
      - file_name: 原始文件名
    """
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"},  # 余弦相似度
        )
    return _collection


def reset_collection():
    """重置 collection（用于测试）"""
    global _collection
    client = get_chroma_client()
    with contextlib.suppress(Exception):
        client.delete_collection("knowledge_base")
    _collection = None
    return get_knowledge_collection()
