# -*- coding: utf-8 -*-
"""岗位数据同步服务

核心流程：
  1. 读取数据源 -> SourceRow 列表
  2. 清洗字段
  3. 去重（按 external_id + user_id）
  4. 写入 tb_jd
  5. 调用 JD 解析逻辑（异步/预留）
  6. 生成 embedding -> 写入 Chroma
  7. 记录同步日志
"""
import time
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.utils.time_helper import utc_now

from app.core.config import settings
from app.core.chroma_client import get_chroma_client
from app.core.prometheus_metrics import record_sync_error, record_sync_job
from app.services.embedding_service import (
    embed_texts,
    get_expected_embedding_dimension,
    set_expected_embedding_dimension,
    validate_embedding_dimension,
)
from app.models.history import JobDescription
from app.models.job_data_source import JobDataSource, JobSyncLog, JobImportBatch
from .adapter import SourceRow
from .csv_source import CsvJobSource
from .json_source import JsonJobSource
from .mock_source import MockJobSource
from .api_source import ApiJobSource
from .arbeitnow_source import ArbeitnowJobSource

logger = logging.getLogger(__name__)

# 适配器工厂
_SOURCE_REGISTRY = {
    "csv": CsvJobSource,
    "json": JsonJobSource,
    "mock": MockJobSource,
    "api": ApiJobSource,
    "arbeitnow": ArbeitnowJobSource,
}


def create_adapter(source_type: str, config: Dict[str, Any]):
    cls = _SOURCE_REGISTRY.get(source_type)
    if not cls:
        raise ValueError(f"不支持的数据源类型: {source_type}")
    return cls(config)


class SyncService:
    """岗位数据同步服务"""

    def __init__(self, db: Session, user_id: Optional[int] = None):
        self.db = db
        self.user_id = user_id
        self._chroma = None
        self._collection = None

    @property
    def collection(self):
        """获取/创建岗位专用的 Chroma collection"""
        if self._collection is None:
            client = get_chroma_client()
            self._collection = client.get_or_create_collection(
                name="job_descriptions",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def test_source(self, source: JobDataSource) -> Tuple[bool, List[Dict[str, Any]], str]:
        """测试数据源连接并返回样本"""
        try:
            adapter = create_adapter(source.source_type, source.config or {})
            ok = adapter.connect()
            if not ok:
                return False, [], "数据源连接失败，请检查配置"
            sample = adapter.read(limit=3)
            return True, [s.raw for s in sample], f"连接成功，读取到 {len(sample)} 条样本"
        except Exception as e:
            logger.exception("测试数据源失败")
            return False, [], f"测试失败: {str(e)[:200]}"

    def sync(self, source: JobDataSource, dry_run: bool = False, limit: int = 0) -> JobSyncLog:
        """执行同步"""
        log = JobSyncLog(
            source_id=source.id,
            user_id=self.user_id,
            status="running",
            started_at=utc_now(),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)

        started = time.time()
        total = success = fail = duplicate = embed_ok = 0
        detail_errors: List[Dict[str, Any]] = []

        try:
            # 1. 读取
            adapter = create_adapter(source.source_type, source.config or {})
            rows = adapter.read(limit=limit)
            total = len(rows)
            logger.info(f"[sync] source={source.id} 读取到 {total} 条")

            # 2. 去重检查
            existing_ids = self._get_existing_external_ids(source.id)

            # 收集需要批量向量化的 JD
            jds_to_embed: List[JobDescription] = []

            for idx, row in enumerate(rows):
                if row.external_id and row.external_id in existing_ids:
                    duplicate += 1
                    continue

                try:
                    if dry_run:
                        success += 1
                        continue

                    # 3. 写入 tb_jd
                    jd = self._save_jd(row)

                    # 4. 记录 batch
                    batch = JobImportBatch(
                        source_id=source.id,
                        sync_log_id=log.id,
                        user_id=self.user_id,
                        external_id=row.external_id,
                        title=row.title,
                        company=row.company,
                        location=row.location,
                        jd_id=jd.id,
                        status="success",
                    )
                    self.db.add(batch)

                    # 5. 收集待向量化 JD（批量处理在循环外）
                    jds_to_embed.append(jd)

                    success += 1
                except Exception as e:
                    fail += 1
                    err_msg = str(e)[:500]
                    detail_errors.append({"index": idx, "title": row.title, "error": err_msg})
                    logger.warning(f"[sync] 单条处理失败: {err_msg}")
                    # 失败也记录 batch
                    if not dry_run:
                        batch = JobImportBatch(
                            source_id=source.id,
                            sync_log_id=log.id,
                            user_id=self.user_id,
                            external_id=row.external_id,
                            title=row.title,
                            company=row.company,
                            location=row.location,
                            status="failed",
                            error_msg=err_msg,
                        )
                        self.db.add(batch)

            if not dry_run:
                self.db.commit()

            # 6. 批量向量化 + Chroma（将 N 次 HTTP 降为 1 次）
            if jds_to_embed and not dry_run:
                embed_ok = self._batch_embed_and_index(jds_to_embed)

            # 6. 更新数据源状态
            if not dry_run:
                source.last_sync_at = utc_now()
                source.last_sync_log_id = log.id
                source.sync_lock_at = None
                if log.status in ("success", "partial"):
                    source.fail_count = 0
                    source.last_error_msg = None
                if source.sync_interval and source.sync_interval > 0:
                    source.next_sync_at = utc_now().replace(minute=0, second=0, microsecond=0)
                    from datetime import timedelta
                    source.next_sync_at += timedelta(minutes=source.sync_interval)
                self.db.commit()

            log.status = "success" if fail == 0 else ("partial" if success > 0 else "failed")
            log.error_msg = None if fail == 0 else f"成功 {success} 条, 失败 {fail} 条"

        except Exception as e:
            logger.exception("同步过程异常")
            log.status = "failed"
            log.error_msg = str(e)[:1000]
            if not dry_run:
                source.fail_count = (source.fail_count or 0) + 1
                source.last_error_msg = log.error_msg
                source.sync_lock_at = None
                self.db.commit()

        finally:
            log.total_count = total
            log.success_count = success
            log.fail_count = fail
            log.duplicate_count = duplicate
            log.embed_count = embed_ok
            log.duration_ms = int((time.time() - started) * 1000)
            log.detail = detail_errors[:50]  # 最多保留 50 条明细
            log.finished_at = utc_now()
            self.db.commit()
            self.db.refresh(log)

            # 记录 Prometheus 指标
            duration_seconds = (time.time() - started)
            record_sync_job(
                source_type=source.source_type,
                status=log.status,
                duration_seconds=duration_seconds,
            )
            if log.status == "failed":
                record_sync_error(source_type=source.source_type, error_type="sync_failed")
            elif fail > 0:
                record_sync_error(source_type=source.source_type, error_type="partial_failure")

        return log

    def _get_existing_external_ids(self, source_id: int) -> set:
        """获取某数据源已导入的外部 ID 集合（用于去重）"""
        rows = self.db.query(JobImportBatch.external_id).filter(
            JobImportBatch.source_id == source_id,
            JobImportBatch.status == "success",
        ).all()
        return {r[0] for r in rows if r[0]}

    def _save_jd(self, row: SourceRow) -> JobDescription:
        """将 SourceRow 写入 tb_jd"""
        jd = JobDescription(
            user_id=self.user_id,
            title=row.title or "未知岗位",
            company=row.company or "",
            location=row.location or "",
            salary_range=row.salary_range or "",
            raw_text=row.raw_text or "",
            source="imported",
            industry=row.industry or "",
            external_url=row.external_url or "",
            external_id=row.external_id or "",
            education_requirement=row.education_requirement or "",
            experience_requirement=row.experience_requirement or "",
            skill_tags=row.skill_tags,
            parsed_json={
                "education": row.education_requirement,
                "experience": row.experience_requirement,
                "industry": row.industry,
                "skill_tags": row.skill_tags,
                "source_row": row.raw,
            },
            is_active=1,
        )
        self.db.add(jd)
        self.db.flush()  # 获取 jd.id
        return jd

    def _batch_embed_and_index(self, jds: List[JobDescription]) -> int:
        """批量为 JD 生成 embedding 并写入 Chroma

        将逐条调用 embed_texts([text])[0] 改为一次性批量 embedding，
        把 N 次 HTTP 请求降为 1 次（底层按 batch_size 自动分批）。
        """
        if not jds:
            return 0

        texts = []
        for jd in jds:
            text = f"{jd.title}\n{jd.company}\n{jd.raw_text}"[:800]
            texts.append(text)

        try:
            vectors = embed_texts(texts)
        except Exception as e:
            logger.warning(f"[sync] 批量向量化失败: {e}")
            return 0

        expected_dim = get_expected_embedding_dimension(self.collection)
        ok, expected_dim, actual_dim = validate_embedding_dimension(vectors, expected_dim)
        if not ok:
            logger.error(
                "[sync] Embedding 维度不匹配: expected=%s actual=%s model=%s",
                expected_dim,
                actual_dim,
                settings.EMBEDDING_MODEL,
            )
            return 0

        if expected_dim is None and vectors:
            set_expected_embedding_dimension(self.collection, actual_dim)

        ok_count = 0
        ids, embeddings, documents, metadatas = [], [], [], []
        for idx, jd in enumerate(jds):
            if idx >= len(vectors):
                break
            ids.append(f"jd-{jd.id}")
            embeddings.append(vectors[idx])
            documents.append(texts[idx])
            metadatas.append({
                "jd_id": jd.id,
                "title": jd.title,
                "company": jd.company,
                "source": "imported",
                "created_at": utc_now().isoformat(),
            })
            ok_count += 1

        try:
            # Chroma 的 add 本身支持批量，这里一次性写入
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        except Exception as e:
            logger.warning(f"[sync] 批量写入 Chroma 失败: {e}")
            # 降级：逐条写入，尽可能多成功
            ok_count = 0
            for idx, jd in enumerate(jds):
                if idx >= len(vectors):
                    break
                try:
                    self.collection.add(
                        ids=[f"jd-{jd.id}"],
                        embeddings=[vectors[idx]],
                        documents=[texts[idx]],
                        metadatas=[{
                            "jd_id": jd.id,
                            "title": jd.title,
                            "company": jd.company,
                            "source": "imported",
                            "created_at": utc_now().isoformat(),
                        }],
                    )
                    ok_count += 1
                except Exception as e2:
                    logger.warning(f"JD {jd.id} 单条写入 Chroma 失败: {e2}")

        return ok_count
