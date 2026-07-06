# -*- coding: utf-8 -*-
"""岗位数据源适配器接口"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class SourceRow:
    """标准化岗位数据行"""
    external_id: str = ""           # 外部唯一标识（用于去重）
    title: str = ""                 # 岗位名称
    company: str = ""               # 公司名
    location: str = ""              # 地点
    salary_range: str = ""          # 薪资
    experience_requirement: str = "" # 经验要求
    education_requirement: str = ""  # 学历要求
    raw_text: str = ""              # 完整 JD 文本
    skill_tags: List[str] = field(default_factory=list)
    industry: str = ""
    external_url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)  # 原始数据保留


class JobDataSourceAdapter(ABC):
    """岗位数据源适配器抽象基类

    所有数据源（CSV/JSON/API/Mock）必须实现此接口。
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._field_mapping = config.get("field_mapping", {})

    @abstractmethod
    def connect(self) -> bool:
        """测试连接是否可用"""
        ...

    @abstractmethod
    def read(self, limit: int = 0) -> List[SourceRow]:
        """读取岗位数据
        :param limit: 限制条数, 0=不限制
        :return: 标准化后的岗位列表
        """
        ...

    def _map_fields(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """根据 field_mapping 将原始字段映射为标准字段"""
        result = {}
        for std_key, raw_key in self._field_mapping.items():
            val = raw.get(raw_key)
            if val is not None:
                result[std_key] = val
        return result

    def _extract_external_id(self, raw: Dict[str, Any]) -> str:
        """尝试从原始数据中提取唯一标识"""
        for key in ["id", "job_id", "external_id", "uuid", "url"]:
            if key in raw and raw[key]:
                return str(raw[key])
        return ""

    def _clean_text(self, text: Any) -> str:
        if text is None:
            return ""
        import re
        return re.sub(r"\s+", " ", str(text)).strip()
