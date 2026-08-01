"""
知识库业务服务：文档上传 → 解析 → 切片 → 向量化 → 写入 Chroma
"""

import logging
import os
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.chroma_client import get_knowledge_collection
from app.core.config import settings
from app.core.tenant_context import current_tenant_id
from app.models.knowledge import KnowledgeDocument
from app.services.chunk_service import chunk_document
from app.services.document_service import parse_document
from app.services.embedding_service import embed_texts
from app.utils.file_access import resolve_upload_path

logger = logging.getLogger(__name__)


def _get_upload_dir() -> tuple:
    """知识库文件存储目录: uploads/knowledge/YYYY/MM/
    返回 (绝对路径, year, month)
    """
    now = datetime.now()
    kb_dir = os.path.join(
        os.path.abspath(settings.UPLOAD_DIR),
        "knowledge",
        str(now.year),
        f"{now.month:02d}",
    )
    os.makedirs(kb_dir, exist_ok=True)
    return kb_dir, now.year, now.month


def save_and_process(
    db: Session,
    file_bytes: bytes,
    original_filename: str,
    title: str,
    doc_type: str = "general",
    user_id: int = None,
    organization_id: int = None,
    tenant_id: int = None,
) -> KnowledgeDocument:
    """
    保存文件 → 创建 DB 记录 → 解析 → 切片 → 向量化 → 写入 Chroma

    返回处理后的 KnowledgeDocument 对象（status 为 ready 或 failed）。
    """
    # ---- 1) 落盘 ----
    ext = os.path.splitext(original_filename)[1].lower().lstrip(".")
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    kb_dir, year, month = _get_upload_dir()
    abs_path = os.path.join(kb_dir, stored_name)

    with open(abs_path, "wb") as f:
        f.write(file_bytes)

    file_size = len(file_bytes)
    # 保存相对于 uploads/ 的相对路径
    rel_path = os.path.join("knowledge", str(year), f"{month:02d}", stored_name).replace("\\", "/")

    # ---- 2) 创建 DB 记录 ----
    # 租户归属优先级：显式 tenant_id > organization_id（Organization 即租户）> 当前上下文
    doc_tenant_id = (
        tenant_id
        if tenant_id is not None
        else organization_id
        if organization_id is not None
        else current_tenant_id()
    )
    doc = KnowledgeDocument(
        user_id=user_id,
        organization_id=organization_id,
        tenant_id=doc_tenant_id,
        title=title,
        file_name=original_filename,
        file_type=ext,
        file_size=file_size,
        file_path=rel_path,
        doc_type=doc_type,
        status="processing",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # ---- 3) 解析 → 切片 → Embedding → Chroma ----
    try:
        raw_text = parse_document(abs_path, ext)

        chunks = chunk_document(
            raw_text,
            chunk_size=settings.RAG_CHUNK_SIZE,
            overlap=settings.RAG_CHUNK_OVERLAP,
        )

        if not chunks:
            raise ValueError("文档内容为空，无法切片")

        # 构建 Chroma 数据
        chunk_texts = [c["text"] for c in chunks]
        chunk_ids = [f"doc_{doc.id}_chunk_{c['index']}" for c in chunks]
        metadatas = [
            {
                "doc_id": str(doc.id),
                "doc_title": title,
                "doc_type": doc_type,
                "chunk_index": c["index"],
                "file_name": original_filename,
                "tenant_id": str(doc.tenant_id or 0),
            }
            for c in chunks
        ]

        # 批量向量化并写入 Chroma
        collection = get_knowledge_collection()
        embeddings = embed_texts(chunk_texts)
        collection.add(
            ids=chunk_ids,
            documents=chunk_texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # 更新 DB 记录
        doc.chunk_count = len(chunks)
        doc.status = "ready"
        doc.error_msg = None

    except Exception as e:
        doc.status = "failed"
        doc.error_msg = str(e)

    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def delete_document(db: Session, doc_id: int) -> bool:
    """
    删除知识库文档（DB 记录 + Chroma 中的对应切片）。
    """
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc:
        return False

    # 从 Chroma 删除
    try:
        collection = get_knowledge_collection()
        prefix = f"doc_{doc.id}_chunk_"
        all_ids = collection.get()["ids"]
        to_delete = [cid for cid in all_ids if cid.startswith(prefix)]
        if to_delete:
            collection.delete(ids=to_delete)
    except Exception as e:
        logger.warning("从 Chroma 删除文档切片失败（不影响 DB 删除）: doc_id=%s, err=%s", doc_id, e)

    # 删除物理文件
    try:
        abs_path = str(resolve_upload_path(doc.file_path))
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception as e:
        logger.warning("删除文档物理文件失败: doc_id=%s, path=%s, err=%s", doc_id, doc.file_path, e)

    db.delete(doc)
    db.commit()
    return True


def get_document_chunks(doc_id: int) -> list[dict]:
    """Load indexed chunks for a knowledge document from Chroma."""
    collection = get_knowledge_collection()
    try:
        results = collection.get(
            where={"doc_id": str(doc_id)},
            include=["documents", "metadatas"],
        )
    except Exception as e:
        logger.warning("load knowledge chunks failed: doc_id=%s err=%s", doc_id, e)
        return []

    chunk_items = []
    ids = results.get("ids") or []
    documents = results.get("documents") or []
    metadatas = results.get("metadatas") or []
    for index, chunk_id in enumerate(ids):
        meta = metadatas[index] if index < len(metadatas) else {}
        chunk_items.append(
            {
                "chunk_id": chunk_id,
                "chunk_index": int((meta or {}).get("chunk_index", index)),
                "text": documents[index] if index < len(documents) else "",
                "doc_title": (meta or {}).get("doc_title", ""),
                "doc_type": (meta or {}).get("doc_type", ""),
            }
        )

    return sorted(chunk_items, key=lambda item: item["chunk_index"])


def reprocess_document(db: Session, doc_id: int) -> KnowledgeDocument | None:
    """Re-parse, re-chunk, and re-index a single knowledge document."""
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc:
        return None

    try:
        abs_path = str(resolve_upload_path(doc.file_path))
    except ValueError:
        doc.status = "failed"
        doc.error_msg = "invalid source path"
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc
    if not os.path.exists(abs_path):
        doc.status = "failed"
        doc.error_msg = "source file not found"
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    try:
        collection = get_knowledge_collection()
        existing = collection.get(where={"doc_id": str(doc.id)}, include=[])
        existing_ids = existing.get("ids") or []
        if existing_ids:
            collection.delete(ids=existing_ids)
    except Exception as e:
        logger.warning("delete old knowledge chunks failed before reprocess: doc_id=%s err=%s", doc.id, e)

    doc.status = "processing"
    doc.error_msg = None
    doc.chunk_count = 0
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        raw_text = parse_document(abs_path, doc.file_type)
        chunks = chunk_document(
            raw_text,
            chunk_size=settings.RAG_CHUNK_SIZE,
            overlap=settings.RAG_CHUNK_OVERLAP,
        )
        if not chunks:
            raise ValueError("document content is empty after parsing")

        chunk_texts = [chunk["text"] for chunk in chunks]
        chunk_ids = [f"doc_{doc.id}_chunk_{chunk['index']}" for chunk in chunks]
        metadatas = [
            {
                "doc_id": str(doc.id),
                "doc_title": doc.title,
                "doc_type": doc.doc_type,
                "chunk_index": chunk["index"],
                "file_name": doc.file_name,
                "tenant_id": str(doc.tenant_id or 0),
            }
            for chunk in chunks
        ]

        collection = get_knowledge_collection()
        embeddings = embed_texts(chunk_texts)
        collection.add(
            ids=chunk_ids,
            documents=chunk_texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        doc.chunk_count = len(chunks)
        doc.status = "ready"
        doc.error_msg = None
    except Exception as e:
        doc.status = "failed"
        doc.error_msg = str(e)

    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def rebuild_all(db: Session):
    """重建所有文档（先清空 Chroma 再重新处理所有 ready 文档）"""
    from app.core.chroma_client import reset_collection

    reset_collection()

    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.status.in_(["ready", "failed"])).all()

    for doc in docs:
        try:
            abs_path = str(resolve_upload_path(doc.file_path))
            if not os.path.exists(abs_path):
                doc.status = "failed"
                doc.error_msg = "文件已丢失"
                continue

            raw_text = parse_document(abs_path, doc.file_type)
            chunks = chunk_document(raw_text)
            if not chunks:
                doc.status = "failed"
                doc.error_msg = "文档内容为空"
                continue

            chunk_texts = [c["text"] for c in chunks]
            chunk_ids = [f"doc_{doc.id}_chunk_{c['index']}" for c in chunks]
            metadatas = [
                {
                    "doc_id": str(doc.id),
                    "doc_title": doc.title,
                    "doc_type": doc.doc_type,
                    "chunk_index": c["index"],
                    "file_name": doc.file_name,
                    "tenant_id": str(doc.tenant_id or 0),
                }
                for c in chunks
            ]

            collection = get_knowledge_collection()
            embeddings = embed_texts(chunk_texts)
            collection.add(ids=chunk_ids, documents=chunk_texts, embeddings=embeddings, metadatas=metadatas)

            doc.chunk_count = len(chunks)
            doc.status = "ready"
            doc.error_msg = None
        except Exception as e:
            doc.status = "failed"
            doc.error_msg = str(e)

        db.add(doc)

    db.commit()
