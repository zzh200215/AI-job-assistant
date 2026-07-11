# -*- coding: utf-8 -*-
"""HTTP API 岗位数据源适配器."""

from __future__ import annotations

import logging
import time
from copy import deepcopy
from typing import Any, Dict, List, Tuple

import requests

from .adapter import JobDataSourceAdapter, SourceRow

logger = logging.getLogger(__name__)


_DEFAULT_USER_AGENT = "SmartRecruit-DataSync/1.0 (+https://github.com/smart-recruit/platform)"


class ApiJobSource(JobDataSourceAdapter):
    """通用 HTTP API 数据源。

    支持：
    - GET / POST
    - Bearer / API Key 鉴权
    - Query / Body 参数
    - 嵌套 JSON 路径提取
    - Page 分页
    - 简单限流（请求间 sleep）
    - 连接池、默认 User-Agent、可配置超时/重试/退避
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

    def connect(self) -> bool:
        url = str(self.config.get("api_url") or "").strip()
        if not url:
            return False
        try:
            items, _ = self._fetch_page(page=self._page_start, page_size=self._page_size)
            return isinstance(items, list)
        except Exception as exc:
            logger.warning("API 数据源连接测试失败: %s", exc)
            return False

    def read(self, limit: int = 0) -> List[SourceRow]:
        rows: List[SourceRow] = []
        target = limit if limit and limit > 0 else None
        page = self._page_start
        page_count = 0
        max_pages = self._max_pages if self._pagination_enabled else 1

        while page_count < max_pages:
            try:
                items, has_more = self._fetch_page(page=page, page_size=self._page_size)
            except Exception as exc:
                logger.error("API 数据源读取失败: %s", exc)
                break

            for raw in items:
                if target is not None and len(rows) >= target:
                    return rows
                if not isinstance(raw, dict):
                    continue
                mapped = self._map_fields(raw)
                rows.append(
                    SourceRow(
                        external_id=self._extract_external_id(raw) or f"api-{page}-{len(rows)}",
                        title=self._clean_text(mapped.get("title", "")),
                        company=self._clean_text(mapped.get("company", "")),
                        location=self._clean_text(mapped.get("location", "")),
                        salary_range=self._clean_text(mapped.get("salary_range", "")),
                        experience_requirement=self._clean_text(mapped.get("experience_requirement", "")),
                        education_requirement=self._clean_text(mapped.get("education_requirement", "")),
                        raw_text=self._clean_text(mapped.get("raw_text", "")),
                        skill_tags=self._parse_skills(mapped.get("skill_tags", "")),
                        industry=self._clean_text(mapped.get("industry", "")),
                        external_url=self._clean_text(mapped.get("external_url", "")),
                        raw=dict(raw),
                    )
                )

            page_count += 1
            if not self._pagination_enabled or not has_more:
                break
            page += 1
            self._sleep_rate_limit()

        return rows

    @property
    def _pagination_enabled(self) -> bool:
        return bool(self.config.get("pagination_enabled"))

    @property
    def _page_start(self) -> int:
        return int(self.config.get("page_start") or 1)

    @property
    def _page_size(self) -> int:
        return int(self.config.get("page_size") or 20)

    @property
    def _max_pages(self) -> int:
        return int(self.config.get("max_pages") or 5)

    def _fetch_page(self, *, page: int, page_size: int) -> Tuple[List[Dict[str, Any]], bool]:
        url = str(self.config.get("api_url") or "").strip()
        method = str(self.config.get("api_method") or "GET").upper()
        headers = deepcopy(self.config.get("api_headers") or {})
        params = deepcopy(self.config.get("api_query") or {})
        body = deepcopy(self.config.get("api_body") or {})

        if self._pagination_enabled:
            page_param = str(self.config.get("page_param") or "page")
            page_size_param = str(self.config.get("page_size_param") or "page_size")
            params[page_param] = page
            params[page_size_param] = page_size

        last_error: Exception | None = None
        max_attempts = max(1, int(self.config.get("retry_max_attempts") or 3))
        backoff_ms = max(0, int(self.config.get("retry_backoff_ms") or 500))
        refreshed = False

        for attempt in range(max_attempts):
            current_headers = deepcopy(headers)
            current_params = deepcopy(params)
            current_body = deepcopy(body)
            self._apply_auth(current_headers, current_params)
            attempt_status_code: int | None = None
            try:
                resp = self._send_request(
                    method=method,
                    url=url,
                    headers=current_headers,
                    params=current_params,
                    body=current_body,
                )
                status_code = getattr(resp, "status_code", None)
                attempt_status_code = status_code if isinstance(status_code, int) else None
                if status_code in {401, 403} and not refreshed:
                    if self._refresh_auth_token():
                        refreshed = True
                        continue
                if status_code == 429:
                    raise RuntimeError(f"API 数据源被限流(HTTP {status_code})")
                if isinstance(status_code, int) and 500 <= status_code < 600:
                    raise RuntimeError(f"API 数据源服务端错误(HTTP {status_code})")
                resp.raise_for_status()
                data = resp.json()
                items = self._extract_items(data)
                has_more = self._infer_has_more(data, items, page_size)
                return items, has_more
            except Exception as exc:
                last_error = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code is None:
                    status_code = attempt_status_code
                if attempt >= max_attempts - 1:
                    break
                if status_code not in {401, 403, 429} and not (500 <= int(status_code or 0) < 600):
                    break
                wait = (backoff_ms / 1000.0) * (2 ** attempt) if backoff_ms else 0.0
                logger.warning("API 数据源请求失败，将在 %.1fs 后重试(%d/%d): %s", wait, attempt + 1, max_attempts - 1, exc)
                if wait > 0:
                    time.sleep(wait)

        raise RuntimeError(f"API 数据源请求失败: {last_error}")

    def _send_request(self, *, method: str, url: str, headers: Dict[str, Any],
                      params: Dict[str, Any], body: Dict[str, Any]):
        timeout = max(5, int(self.config.get("timeout_seconds") or 30))
        headers.setdefault("User-Agent", _DEFAULT_USER_AGENT)
        if method == "GET":
            return requests.get(url, headers=headers, params=params, timeout=timeout)
        return requests.post(url, headers=headers, params=params, json=body, timeout=timeout)

    def _apply_auth(self, headers: Dict[str, str], params: Dict[str, Any]) -> None:
        auth_type = str(self.config.get("auth_type") or "none")
        if auth_type == "bearer":
            token = str(self.config.get("auth_token") or "").strip()
            if token:
                headers.setdefault("Authorization", f"Bearer {token}")
        elif auth_type == "api_key":
            key_name = str(self.config.get("auth_key_name") or "").strip()
            key_value = self.config.get("auth_key_value")
            auth_in = str(self.config.get("auth_in") or "header")
            if key_name and key_value is not None:
                if auth_in == "query":
                    params[key_name] = key_value
                else:
                    headers[key_name] = str(key_value)

    def _refresh_auth_token(self) -> bool:
        refresh_url = str(self.config.get("auth_refresh_url") or "").strip()
        if not refresh_url:
            return False

        headers = deepcopy(self.config.get("auth_refresh_headers") or {})
        params = deepcopy(self.config.get("auth_refresh_query") or {})
        body = deepcopy(self.config.get("auth_refresh_body") or {})
        method = str(self.config.get("auth_refresh_method") or "POST").upper()
        token_path = str(self.config.get("auth_refresh_token_path") or "access_token").strip()

        try:
            resp = self._send_request(
                method=method,
                url=refresh_url,
                headers=headers,
                params=params,
                body=body,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            logger.warning("API 数据源刷新 token 失败: %s", exc)
            return False

        new_token = self._get_by_path(payload, token_path) if token_path else payload
        if not new_token:
            logger.warning("API 数据源刷新 token 失败: 响应中未找到 token")
            return False

        self.config["auth_token"] = str(new_token)
        return True

    def _extract_items(self, data: Any) -> List[Dict[str, Any]]:
        items = data
        json_path = str(self.config.get("json_path") or "").strip()
        if json_path:
            items = self._get_by_path(data, json_path)
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    def _infer_has_more(self, data: Any, items: List[Dict[str, Any]], page_size: int) -> bool:
        if not self._pagination_enabled:
            return False
        has_more_path = str(self.config.get("has_more_path") or "").strip()
        if has_more_path:
            value = self._get_by_path(data, has_more_path)
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                return value.lower() in {"1", "true", "yes", "y"}
        return len(items) >= page_size

    def _get_by_path(self, payload: Any, path: str) -> Any:
        current = payload
        for key in path.split("."):
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    def _sleep_rate_limit(self) -> None:
        delay_ms = int(self.config.get("rate_limit_ms") or 0)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

    def _parse_skills(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []
