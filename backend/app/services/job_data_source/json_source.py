# -*- coding: utf-8 -*-
"""JSON 岗位数据源适配器"""
import json
import os
from typing import List, Any
from .adapter import JobDataSourceAdapter, SourceRow


class JsonJobSource(JobDataSourceAdapter):
    """JSON 文件数据源"""

    def connect(self) -> bool:
        path = self.config.get("file_path", "")
        return os.path.isfile(path) and os.access(path, os.R_OK)

    def read(self, limit: int = 0) -> List[SourceRow]:
        path = self.config.get("file_path", "")
        encoding = self.config.get("file_encoding", "utf-8")
        json_path = self.config.get("json_path", "")  # 如 "data.jobs"

        with open(path, "r", encoding=encoding) as f:
            data = json.load(f)

        # 支持从嵌套路径提取列表
        items = data
        if json_path:
            for key in json_path.split("."):
                items = items.get(key, {}) if isinstance(items, dict) else []
                if not isinstance(items, (list, dict)):
                    items = []
                    break
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []

        rows: List[SourceRow] = []
        for idx, raw in enumerate(items):
            if limit > 0 and idx >= limit:
                break
            if not isinstance(raw, dict):
                continue
            mapped = self._map_fields(raw)
            rows.append(SourceRow(
                external_id=self._extract_external_id(raw) or f"json-{idx}",
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
            ))
        return rows

    def _parse_skills(self, val: Any) -> List[str]:
        if isinstance(val, list):
            return [str(v).strip() for v in val if v]
        if isinstance(val, str):
            return [s.strip() for s in val.split(",") if s.strip()]
        return []
