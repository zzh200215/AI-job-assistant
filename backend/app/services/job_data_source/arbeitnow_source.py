# -*- coding: utf-8 -*-
"""Arbeitnow job board adapter.

Free public API documented at:
https://www.arbeitnow.com/api/job-board-api
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any, Dict, List, Tuple

import requests

from .adapter import JobDataSourceAdapter, SourceRow

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = "SmartRecruit-DataSync/1.0 (+https://github.com/smart-recruit/platform)"


class ArbeitnowJobSource(JobDataSourceAdapter):
    """Arbeitnow free public job board API."""

    BASE_URL = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

    def connect(self) -> bool:
        try:
            items, _ = self._fetch_page(page=self._page_start)
            return isinstance(items, list)
        except Exception as exc:
            logger.warning("Arbeitnow 数据源连接测试失败: %s", exc)
            return False

    def read(self, limit: int = 0) -> List[SourceRow]:
        rows: List[SourceRow] = []
        target = limit if limit and limit > 0 else None
        page = self._page_start
        max_pages = max(1, self._max_pages)

        for _ in range(max_pages):
            try:
                items, has_more = self._fetch_page(page=page)
            except Exception as exc:
                logger.error("Arbeitnow 数据源读取失败: %s", exc)
                break

            for raw in items:
                if target is not None and len(rows) >= target:
                    return rows
                if not isinstance(raw, dict):
                    continue
                mapped = self._map_fields(raw)
                rows.append(
                    SourceRow(
                        external_id=self._extract_external_id(raw) or self._build_external_id(raw, page, len(rows)),
                        title=self._clean_text(mapped.get("title", "")),
                        company=self._clean_text(mapped.get("company", "")),
                        location=self._clean_text(mapped.get("location", "")),
                        salary_range=self._clean_text(mapped.get("salary_range", "")),
                        experience_requirement=self._clean_text(mapped.get("experience_requirement", "")),
                        education_requirement=self._clean_text(mapped.get("education_requirement", "")),
                        raw_text=self._clean_text(mapped.get("raw_text", "")),
                        skill_tags=self._parse_tags(mapped.get("skill_tags", "")),
                        industry=self._clean_text(mapped.get("industry", "")),
                        external_url=self._clean_text(mapped.get("external_url", "")),
                        raw=dict(raw),
                    )
                )

            if not has_more:
                break
            page += 1

        return rows

    @property
    def _page_start(self) -> int:
        return int(self.config.get("page_start") or 1)

    @property
    def _max_pages(self) -> int:
        return int(self.config.get("max_pages") or 5)

    def _fetch_page(self, *, page: int) -> Tuple[List[Dict[str, Any]], bool]:
        search = str(self.config.get("search_query") or "").strip()
        params = {"page": page}
        if search:
            params["search"] = search

        last_error: Exception | None = None
        max_attempts = max(1, int(self.config.get("retry_max_attempts") or 3))
        backoff_ms = max(0, int(self.config.get("retry_backoff_ms") or 500))
        timeout = max(5, int(self.config.get("timeout_seconds") or 20))

        for attempt in range(max_attempts):
            try:
                resp = requests.get(
                    self.BASE_URL,
                    params=params,
                    timeout=timeout,
                    headers={"User-Agent": _DEFAULT_USER_AGENT},
                )
                status_code = getattr(resp, "status_code", None)
                if status_code == 429:
                    raise RuntimeError(f"Arbeitnow 数据源被限流(HTTP {status_code})")
                if isinstance(status_code, int) and 500 <= status_code < 600:
                    raise RuntimeError(f"Arbeitnow 数据源服务端错误(HTTP {status_code})")
                resp.raise_for_status()
                payload = resp.json() or {}
                items = payload.get("data") or []
                if not isinstance(items, list):
                    items = []
                links = payload.get("links") or {}
                has_more = bool(links.get("next"))
                return [item for item in items if isinstance(item, dict)], has_more
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts - 1:
                    break
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code not in {429} and not (isinstance(status_code, int) and 500 <= status_code < 600):
                    break
                wait = (backoff_ms / 1000.0) * (2 ** attempt) if backoff_ms else 0.0
                logger.warning("Arbeitnow 请求失败，将在 %.1fs 后重试(%d/%d): %s", wait, attempt + 1, max_attempts - 1, exc)
                if wait > 0:
                    time.sleep(wait)

        raise RuntimeError(f"Arbeitnow 数据源请求失败: {last_error}")

    def _build_external_id(self, raw: Dict[str, Any], page: int, index: int) -> str:
        slug = str(raw.get("slug") or "").strip()
        if slug:
            return slug
        url = str(raw.get("url") or "").strip()
        if url:
            return url
        title = str(raw.get("title") or "").strip().lower()
        company = str(raw.get("company_name") or "").strip().lower()
        location = str(raw.get("location") or "").strip().lower()
        return f"arbeitnow-{page}-{index}-{hash((title, company, location))}"

    def _map_fields(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        mapped = super()._map_fields(raw)
        if not mapped:
            mapped = {}
        mapped.setdefault("title", raw.get("title", ""))
        mapped.setdefault("company", raw.get("company_name", ""))
        mapped.setdefault("location", raw.get("location", ""))
        mapped.setdefault("raw_text", self._build_raw_text(raw))
        mapped.setdefault("skill_tags", raw.get("tags", []))
        mapped.setdefault("industry", ", ".join(raw.get("job_types") or []))
        mapped.setdefault("external_url", raw.get("url", ""))
        return mapped

    def _build_raw_text(self, raw: Dict[str, Any]) -> str:
        description = self._html_to_text(raw.get("description", ""))
        parts = [
            f"岗位: {raw.get('title', '')}",
            f"公司: {raw.get('company_name', '')}",
            f"地点: {raw.get('location', '')}",
            f"远程: {'是' if raw.get('remote') else '否'}",
            f"标签: {', '.join(raw.get('tags') or [])}",
        ]
        if description:
            parts.append(f"描述: {description}")
        return "\n".join(part for part in parts if part)

    def _html_to_text(self, value: Any) -> str:
        text = html.unescape(str(value or ""))
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _parse_tags(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []
