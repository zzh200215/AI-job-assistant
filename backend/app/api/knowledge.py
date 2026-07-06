# -*- coding: utf-8 -*-
"""Knowledge base management APIs."""
import os
import traceback

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.knowledge import KnowledgeDocument
from app.models.user import User
from app.schemas.knowledge import (
    DOC_TYPE_CHOICES,
    KBDocumentChunkResp,
    KBSearchReq,
    KBSearchResult,
    KBUploadResp,
    QueryRewriteReq,
)
from app.services import knowledge_service, rag_service
from app.services.embedding_service import get_embedding_daily_stats, get_embedding_stats
from app.services.query_rewrite_service import rewrite_queries
from app.services.rag_confidence_service import confidence_from_flat_results
from app.utils.file_access import resolve_upload_path
from app.utils.response import ERR_AUTH, ERR_COMMON, ERR_FILE, ERR_PARAM, fail, ok

router = APIRouter()

ALLOWED_EXTENSIONS = {"txt", "md", "pdf", "docx", "doc"}
ALLOWED_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/octet-stream",
}
MAX_FILE_SIZE = 20 * 1024 * 1024


def _is_admin(user: User) -> bool:
    return user.username in settings.admin_usernames_list


def _can_access_document(doc: KnowledgeDocument, user: User) -> bool:
    return _is_admin(user) or doc.user_id in (None, user.id)


def _serialize_document(doc: KnowledgeDocument) -> dict:
    return {
        "id": doc.id,
        "user_id": doc.user_id,
        "title": doc.title,
        "file_name": doc.file_name,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "doc_type": doc.doc_type,
        "chunk_count": doc.chunk_count or 0,
        "status": doc.status,
        "error_msg": doc.error_msg,
        "create_time": doc.create_time.isoformat() if doc.create_time else None,
        "update_time": doc.update_time.isoformat() if doc.update_time else None,
    }


@router.post("/upload", summary="Upload a knowledge document")
async def upload_knowledge(
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: str = Form("general"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file or not file.filename:
        return fail(message="empty file", code=ERR_FILE)

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        return fail(message=f"unsupported file extension: .{ext}", code=ERR_FILE)

    mime = (file.content_type or "").lower()
    if mime and mime not in ALLOWED_MIME_TYPES:
        return fail(message=f"unsupported content-type: {mime}", code=ERR_FILE)

    if doc_type not in DOC_TYPE_CHOICES:
        return fail(message=f"unsupported doc_type: {doc_type}", code=ERR_PARAM)
    if not title or not title.strip():
        return fail(message="title is required", code=ERR_PARAM)

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        return fail(message=f"file too large: {len(raw)} bytes", code=ERR_FILE)

    try:
        doc = knowledge_service.save_and_process(
            db,
            raw,
            file.filename,
            title.strip(),
            doc_type,
            user_id=current_user.id,
        )
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"document processing failed: {exc}", code=ERR_COMMON)

    return ok(
        data=KBUploadResp(
            id=doc.id,
            title=doc.title,
            file_name=doc.file_name,
            file_type=doc.file_type,
            file_size=doc.file_size or 0,
            doc_type=doc.doc_type,
            status=doc.status,
            create_time=doc.create_time.isoformat() if doc.create_time else None,
        ).model_dump(),
        message=f"uploaded with status={doc.status}",
    )


@router.get("/list", summary="List knowledge documents")
async def list_knowledge(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    doc_type: str | None = Query(None),
    status: str | None = Query(None),
    my_only: bool = Query(True, description="Only show current user's uploads"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(KnowledgeDocument)
    if doc_type:
        query = query.filter(KnowledgeDocument.doc_type == doc_type)
    if status:
        query = query.filter(KnowledgeDocument.status == status)
    if my_only or not _is_admin(current_user):
        query = query.filter(KnowledgeDocument.user_id == current_user.id)

    query = query.order_by(KnowledgeDocument.create_time.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return ok(
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_serialize_document(item) for item in items],
        }
    )


@router.get("/{doc_id}", summary="Get knowledge document detail")
async def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc:
        return fail(message="document not found", code=ERR_PARAM)
    if not _can_access_document(doc, current_user):
        return fail(message="permission denied", code=ERR_AUTH)
    return ok(data=_serialize_document(doc))


@router.get("/{doc_id}/chunks", summary="Get indexed chunks for a document")
async def get_document_chunks(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc:
        return fail(message="document not found", code=ERR_PARAM)
    if not _can_access_document(doc, current_user):
        return fail(message="permission denied", code=ERR_AUTH)
    chunks = knowledge_service.get_document_chunks(doc_id)
    return ok(
        data={
            "document": _serialize_document(doc),
            "chunks": [KBDocumentChunkResp(**item).model_dump() for item in chunks],
        }
    )


@router.delete("/{doc_id}", summary="Delete a knowledge document")
async def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc:
        return fail(message="document not found", code=ERR_PARAM)
    if doc.user_id is not None and doc.user_id != current_user.id:
        return fail(message="permission denied", code=ERR_AUTH)

    deleted = knowledge_service.delete_document(db, doc_id)
    if not deleted:
        return fail(message="document not found", code=ERR_PARAM)
    return ok(message="deleted")


@router.post("/{doc_id}/reprocess", summary="Reprocess a knowledge document")
async def reprocess_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc:
        return fail(message="document not found", code=ERR_PARAM)

    is_admin = current_user.username in settings.admin_usernames_list
    if doc.user_id is not None and doc.user_id != current_user.id and not is_admin:
        return fail(message="permission denied", code=ERR_AUTH)

    processed = knowledge_service.reprocess_document(db, doc_id)
    if not processed:
        return fail(message="document not found", code=ERR_PARAM)
    return ok(data=_serialize_document(processed), message=f"status={processed.status}")


@router.get("/{doc_id}/download", summary="Download a knowledge document")
async def download_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.get(KnowledgeDocument, doc_id)
    if not doc:
        return fail(message="document not found", code=ERR_PARAM)
    if not _can_access_document(doc, current_user):
        return fail(message="permission denied", code=ERR_AUTH)

    try:
        abs_path = resolve_upload_path(doc.file_path)
    except ValueError:
        return fail(message="invalid document path", code=ERR_COMMON)

    if not abs_path.exists() or not abs_path.is_file():
        return fail(message="source file not found", code=ERR_FILE)

    return FileResponse(
        path=abs_path,
        filename=doc.file_name,
        media_type="application/octet-stream",
    )


@router.post("/search", summary="Search knowledge base")
async def search_knowledge(
    payload: KBSearchReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    results = rag_service.search_knowledge(
        query=payload.query,
        doc_type=payload.doc_type,
        top_k=payload.top_k,
        db=db,
        user_id=current_user.id,
    )
    return ok(
        data={
            "results": [
                KBSearchResult(
                    chunk_id=item["chunk_id"],
                    text=item["text"],
                    doc_title=item["doc_title"],
                    doc_type=item["doc_type"],
                    chunk_index=item["chunk_index"],
                    score=item["score"],
                ).model_dump()
                for item in results
            ]
        }
    )


@router.post("/rebuild", summary="Rebuild all knowledge vectors")
async def rebuild_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.username not in settings.admin_usernames_list:
        return fail(message="admin only", code=ERR_AUTH)
    try:
        knowledge_service.rebuild_all(db)
        return ok(message="rebuild completed")
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"rebuild failed: {exc}", code=ERR_COMMON)


@router.get("/admin/embedding-stats", summary="Get embedding runtime stats")
async def embedding_stats(current_user: User = Depends(get_current_user)):
    if not _is_admin(current_user):
        return fail(message="admin only", code=ERR_AUTH)
    runtime = get_embedding_stats()
    return ok(
        data={
            **runtime,
            "daily_trend": get_embedding_daily_stats(days=7),
        }
    )


@router.post("/query-rewrite-test", summary="Test query rewrite and retrieval")
async def query_rewrite_test(
    payload: QueryRewriteReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rewritten = rewrite_queries(
        original_query=payload.original_query,
        resume_summary=payload.resume_summary or "",
        jd_summary=payload.jd_summary or "",
        max_queries=payload.max_queries,
    )

    retrieved = rag_service.search_knowledge_multi_queries(
        rewritten_queries=rewritten,
        doc_type=payload.doc_type,
        top_k_per_query=payload.top_k_per_query,
        db=db,
        user_id=current_user.id,
    )
    rag_context = rag_service.build_rag_context_with_rewrite(
        rewritten_queries=rewritten,
        doc_type=payload.doc_type,
        top_k_per_query=payload.top_k_per_query,
        db=db,
        user_id=current_user.id,
    )
    references = rag_service.get_knowledge_references_with_rewrite(
        rewritten_queries=rewritten,
        doc_type=payload.doc_type,
        top_k_per_query=payload.top_k_per_query,
        db=db,
        user_id=current_user.id,
    )
    rag_confidence = confidence_from_flat_results(payload.original_query, retrieved)

    return ok(
        data={
            "original_query": payload.original_query,
            "rewritten_queries": [
                {
                    "query_text": item.query_text,
                    "query_type": item.query_type,
                    "purpose": item.purpose,
                    "priority": item.priority,
                }
                for item in rewritten
            ],
            "retrieved_chunks": [
                {
                    "chunk_id": item["chunk_id"],
                    "text": item["text"],
                    "doc_title": item["doc_title"],
                    "doc_type": item["doc_type"],
                    "chunk_index": item["chunk_index"],
                    "score": item["score"],
                    "final_score": item.get("final_score", 0),
                    "rerank_score": item.get("rerank_score", 0),
                    "rerank_source": item.get("rerank_source", ""),
                    "query_used": item.get("query_used", ""),
                    "query_type": item.get("query_type", ""),
                    "queries": item.get("queries", []),
                }
                for item in retrieved
            ],
            "total_chunks": len(retrieved),
            "rag_confidence": rag_confidence,
            "rag_context": rag_context,
            "references": references,
        }
    )
