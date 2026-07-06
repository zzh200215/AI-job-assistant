# -*- coding: utf-8 -*-
"""重置 Chroma 知识库 collection"""
from app.core.chroma_client import reset_collection
from app.core.database import SessionLocal
from app.models.knowledge import KnowledgeDocument

collection = reset_collection()
print(f"Collection reset: {collection.name}, count={collection.count()}")

# 将所有文档状态重置为 failed，让用户重新上传
with SessionLocal() as db:
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.status == "ready").all()
    for doc in docs:
        doc.status = "failed"
        doc.error_msg = "Collection 已重置，请重新上传"
    db.commit()
    print(f"Reset {len(docs)} documents to failed status")
