"""
JobRecommendationEngine — 岗位推荐引擎

三阶段流水线：
  1. 向量召回（Chroma 相似度搜索）
  2. 规则打分（技能 Jaccard + 经验层级 + 薪资匹配）
  3. 混合排序（向量分 × 0.6 + 规则分 × 0.4）

使用方式：
    engine = JobRecommendationEngine(db)
    results = engine.recommend(resume_id=1, limit=5, filters={"location": "北京"})
"""

import copy
import hashlib
import json
import math
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.chroma_client import get_knowledge_collection
from app.core.tenant_context import current_tenant_id
from app.models.history import JobDescription, Resume
from app.services.embedding_service import embed_texts
from app.services.recommendation_tuning import DEFAULT_RECOMMENDATION_TUNING_CONFIG

_RECOMMEND_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_RECOMMEND_CACHE_MAX = 128
_RECOMMEND_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 86400  # 24 灏忔椂


def _visible_job_filter(owner_id: int | None, tenant_id: int | None = None):
    """岗位可见性：本人 + 平台共享，且归属当前租户或平台共享（T3-3 租户隔离）。

    tenant_id 为空时取当前租户上下文（未注入回落默认租户 1），保证单测/后台任务行为稳定。
    """
    if owner_id is None:
        base = JobDescription.user_id.is_(None)
    else:
        base = or_(JobDescription.user_id == owner_id, JobDescription.user_id.is_(None))
    tid = tenant_id if tenant_id is not None else current_tenant_id()
    tenant_cond = or_(JobDescription.tenant_id == tid, JobDescription.tenant_id.is_(None))
    return and_(base, tenant_cond)


def _normalize_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in (filters or {}).items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        normalized[key] = value

    if "exp_level" in normalized and "experience" not in normalized:
        normalized["experience"] = normalized["exp_level"]

    return normalized


def _recommend_cache_key(resume_id: int, resume_version: str, filters: dict[str, Any], tenant_id: int = None) -> str:
    payload = json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    tid = tenant_id if tenant_id is not None else current_tenant_id()
    raw = f"{resume_id}|{resume_version}|{tid}|{payload}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _prune_recommend_cache_locked(now: float, ttl: int) -> None:
    expired_keys = [key for key, entry in _RECOMMEND_CACHE.items() if now - entry["ts"] >= ttl]
    for key in expired_keys:
        _RECOMMEND_CACHE.pop(key, None)

    while len(_RECOMMEND_CACHE) > _RECOMMEND_CACHE_MAX:
        _RECOMMEND_CACHE.popitem(last=False)


def _get_cached_recommendations(cache_key: str, now: float, ttl: int) -> list[dict[str, Any]] | None:
    with _RECOMMEND_CACHE_LOCK:
        entry = _RECOMMEND_CACHE.get(cache_key)
        if entry is None:
            return None
        if now - entry["ts"] >= ttl:
            _RECOMMEND_CACHE.pop(cache_key, None)
            return None
        _RECOMMEND_CACHE.move_to_end(cache_key)
        return copy.deepcopy(entry["data"])


def _set_cached_recommendations(cache_key: str, now: float, ttl: int, data: list[dict[str, Any]]) -> None:
    with _RECOMMEND_CACHE_LOCK:
        _RECOMMEND_CACHE[cache_key] = {"ts": now, "data": copy.deepcopy(data)}
        _RECOMMEND_CACHE.move_to_end(cache_key)
        _prune_recommend_cache_locked(now, ttl)


# ==================== 缓存 ====================


# ==================== 数据结构 ====================


@dataclass
class RecommendResult:
    jd_id: int
    job_title: str
    company: str
    location: str
    salary_range: str
    industry: str
    match_score: float  # 0-100 综合分
    vector_score: float  # 0-100 向量相似度分
    rule_score: float  # 0-100 规则匹配分
    skill_overlap: list[str]  # 重合技能
    skill_gap: list[str]  # 缺失技能
    salary_match: bool  # 薪资是否匹配
    location_match: bool  # 地点是否匹配
    experience_match: bool  # 经验层级是否匹配
    match_reason: str  # 一句话匹配原因
    recommendation_type: str  # 高度推荐 / 值得一试 / 谨慎考虑
    source: str = ""

    experience_requirement: str = ""

    def to_dict(self) -> dict:
        return {
            "jd_id": self.jd_id,
            "job_title": self.job_title,
            "company": self.company,
            "location": self.location,
            "salary_range": self.salary_range,
            "industry": self.industry,
            "match_score": round(self.match_score),
            "vector_score": round(self.vector_score),
            "rule_score": round(self.rule_score),
            "skill_overlap": self.skill_overlap,
            "skill_gap": self.skill_gap,
            "salary_match": self.salary_match,
            "location_match": self.location_match,
            "experience_match": self.experience_match,
            "match_reason": self.match_reason,
            "recommendation_type": self.recommendation_type,
            "source": self.source,
        }


# ==================== 引擎 ====================


class JobRecommendationEngine:
    """岗位推荐引擎（一次实例化可多次调用 recommend）"""

    # 权重
    WEIGHT_VECTOR = 0.6
    WEIGHT_RULE = 0.4

    # 经验层级映射
    EXP_LEVELS = {
        "实习": (0, 1),
        "初级": (1, 3),
        "中级": (3, 5),
        "高级": (5, 8),
        "资深": (8, 15),
        "专家": (15, 99),
    }

    def __init__(self, db: Session, tuning_config: dict[str, Any] | None = None):
        self.db = db
        self._collection = get_knowledge_collection()
        self.tuning_config = copy.deepcopy(tuning_config or DEFAULT_RECOMMENDATION_TUNING_CONFIG)

    # ==================== 对外接口 ====================

    def recommend(
        self,
        resume_id: int,
        limit: int = 5,
        filters: dict | None = None,
        bypass_cache: bool = False,
    ) -> list[dict]:
        """
        主入口：为指定简历推荐岗位

        参数:
            resume_id: 简历 ID
            limit: 返回条数
            filters: 筛选条件 {location, salary_min, salary_max, industry, experience}
            bypass_cache: 是否跳过缓存

        返回:
            [RecommendResult.to_dict(), ...]
        """
        resume = self.db.get(Resume, resume_id)
        if not resume or not resume.parsed_json:
            return []

        # --- 缓存键 ---
        normalized_filters = _normalize_filters(filters)
        resume_version = (
            (resume.update_time or resume.create_time or "").isoformat()
            if (resume.update_time or resume.create_time)
            else "unknown"
        )
        cache_key = _recommend_cache_key(resume_id, resume_version, normalized_filters, tenant_id=current_tenant_id())
        now = time.time()
        if not bypass_cache:
            cached = _get_cached_recommendations(cache_key, now, _CACHE_TTL)
            if cached is not None:
                return cached[:limit]

        # --- 1) 取所有活跃 JD ---
        jd_query = (
            self.db.query(JobDescription)
            .filter(
                JobDescription.is_active == 1,
                _visible_job_filter(resume.user_id),
            )
            .all()
        )

        if not jd_query:
            return []

        # --- 2) 向量 + 规则 双通道评分 ---
        resume_data = resume.parsed_json
        results: list[RecommendResult] = []

        # 简历文本在整个循环中是固定的，只需 embedding 一次；
        # 所有 JD 文本一次性批量 embedding（内部按 10 条/批自动分批），
        # 避免旧实现里"每个 JD 都重新嵌入一遍简历"的 O(N) 重复调用。
        resume_text = self._build_vector_text(resume_data)
        jd_texts = [(jd.raw_text or self._build_vector_text(jd.parsed_json or {})) for jd in jd_query]
        try:
            all_embs = embed_texts([resume_text] + jd_texts)
            resume_emb, jd_embs = all_embs[0], all_embs[1:]
        except Exception:
            resume_emb, jd_embs = None, [None] * len(jd_query)

        for idx, jd in enumerate(jd_query):
            jd_data = jd.parsed_json or {}

            vector_score = self._vector_score(resume_emb, jd_embs[idx])
            rule_score = self._rule_score(resume_data, jd, jd_data)
            combined = vector_score * self._vector_weight + rule_score * self._rule_weight

            # 技能分析
            resume_skills = self._extract_skills(resume_data)
            jd_skills = self._extract_skills(jd_data)
            overlap = list(set(resume_skills) & set(jd_skills))
            gap = list(set(jd_skills) - set(resume_skills))

            # 薪资 / 地点匹配
            resume_salary = self._parse_salary(resume_data.get("expected_salary", ""))
            jd_salary = self._parse_salary(jd.salary_range or "")
            salary_ok = self._salary_match(resume_salary, jd_salary) if resume_salary else True

            resume_location = resume_data.get("location", resume_data.get("city", ""))
            location_ok = self._location_match(resume_location, jd.location or "") if resume_location else True

            exp_ok = self._experience_match(resume_data.get("years_exp", 0), jd_data)

            result = RecommendResult(
                jd_id=jd.id,
                job_title=jd.title,
                company=jd.company or "",
                location=jd.location or "",
                salary_range=jd.salary_range or "",
                industry=jd.industry or jd_data.get("industry", ""),
                match_score=combined,
                vector_score=vector_score,
                rule_score=rule_score,
                skill_overlap=overlap[:8],
                skill_gap=gap[:8],
                salary_match=salary_ok,
                location_match=location_ok,
                experience_match=exp_ok,
                match_reason=self._generate_reason(combined, overlap, gap, salary_ok, location_ok),
                recommendation_type=self._recommend_type(combined),
                source=jd.source or "",
                experience_requirement=(jd_data.get("experience_requirement") or jd.experience_requirement or ""),
            )
            results.append(result)

        # --- 3) 排序 ---
        results.sort(key=lambda r: r.match_score, reverse=True)

        # --- 4) 应用筛选 ---
        results = self._apply_filters(results, normalized_filters)

        # --- 5) 截断 + 缓存 ---
        output = [r.to_dict() for r in results]
        _set_cached_recommendations(cache_key, now, _CACHE_TTL, output)
        return output[:limit]

    # ==================== 向量相似度（通道1）====================

    def _vector_score(self, resume_emb: list[float] | None, jd_emb: list[float] | None) -> float:
        """基于预计算好的简历 / JD 向量算余弦相似度 → 0-100。

        向量在 recommend() 中已对简历（1 次）和全部 JD（批量）统一算好，
        这里只做纯计算，不再触发任何 embedding 调用。
        embedding 缺失（如网络失败）时降级返回中等分 50。
        """
        if not resume_emb or not jd_emb:
            return 50.0
        cos_sim = self._cosine_similarity(resume_emb, jd_emb)
        return max(0, min(100, cos_sim * 100))

    # ==================== 规则评分（通道2）====================

    def _rule_score(self, resume_data: dict, jd: JobDescription, jd_data: dict) -> float:
        """多维度规则匹配 → 0-100"""
        scores = []
        weights = []

        rule_weights = self._rule_component_weights

        # --- 技能 Jaccard 相似度 ---
        resume_skills = set(self._extract_skills(resume_data))
        jd_skills = set(self._extract_skills(jd_data))
        if resume_skills and jd_skills:
            jaccard = len(resume_skills & jd_skills) / len(resume_skills | jd_skills)
            scores.append(jaccard * 100)
            weights.append(rule_weights["skill"])

        # --- 经验层级匹配 ---
        resume_years = resume_data.get("years_exp", 0) or 0
        exp_score = self._experience_score(resume_years, jd_data)
        scores.append(exp_score)
        weights.append(rule_weights["experience"])

        # --- 薪资匹配 ---
        resume_salary = self._parse_salary(resume_data.get("expected_salary", "") or "")
        jd_salary = self._parse_salary(jd.salary_range or "")
        if resume_salary[0] is not None and jd_salary[0] is not None:
            salary_score = self._salary_score(resume_salary, jd_salary)
            scores.append(salary_score)
            weights.append(rule_weights["salary"])

        # --- 地点匹配 ---
        resume_location = resume_data.get("location", resume_data.get("city", ""))
        jd_location = jd.location or ""
        if resume_location and jd_location:
            loc_score = 100 if self._location_match(resume_location, jd_location) else 30
            scores.append(loc_score)
            weights.append(rule_weights["location"])

        if not scores:
            return 50

        return sum(s * w for s, w in zip(scores, weights, strict=False)) / sum(weights)

    # ==================== 技能提取 ====================

    def _extract_skills(self, data: dict) -> list[str]:
        """从 parsed_json 中提取技能列表"""
        skills = []
        raw = data.get("skills", data.get("required_skills", data.get("nice_to_have", [])))
        if isinstance(raw, list):
            for s in raw:
                if isinstance(s, str):
                    skills.append(s.strip().lower())
                elif isinstance(s, dict):
                    skills.append(s.get("skill", "").strip().lower())
        return [s for s in skills if s]

    def _build_vector_text(self, data: dict) -> str:
        """构建用于向量化的文本"""
        parts = []
        # 标题+公司
        parts.append(data.get("title", ""))
        parts.append(data.get("company", ""))
        # 技能
        skills = data.get("skills", data.get("required_skills", []))
        if isinstance(skills, list):
            parts.extend([s if isinstance(s, str) else s.get("skill", "") for s in skills])
        # 职责
        resp = data.get("responsibilities", data.get("work_experience", []))
        if isinstance(resp, list):
            for r in resp:
                if isinstance(r, str):
                    parts.append(r)
                elif isinstance(r, dict):
                    parts.append(r.get("desc", r.get("responsibility", "")))
        # 项目经验
        for proj in data.get("project_experience", data.get("projects", [])):
            if isinstance(proj, dict):
                parts.append(proj.get("desc", ""))
                parts.extend(proj.get("tech", []))
        return " ".join([p for p in parts if p])

    # ==================== 薪资/地点/经验 工具 ====================

    def _parse_salary(self, salary_str: str) -> tuple[float | None, float | None]:
        """解析薪资字符串 → (min, max) 单位:万/年"""
        if not salary_str:
            return None, None
        s = salary_str.replace(" ", "").replace("K", "k").replace("k", "")
        # 匹配 "20k-35k" / "20-35k" / "20万-35万" / "20w-35w" / "20-30"
        patterns = [
            r"(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)\s*万",
            r"(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)\s*[wW]",
            r"(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)\s*[kK]",
            r"(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)",
        ]
        for pat in patterns:
            m = re.search(pat, s)
            if m:
                a, b = float(m.group(1)), float(m.group(2))
                if "k" in pat or "K" in pat:
                    a, b = a * 1000, b * 1000
                # 统一转成年薪（万）
                if a > 100:  # 月薪k → 年薪万
                    a, b = a * 12 / 10000, b * 12 / 10000
                return round(min(a, b), 1), round(max(a, b), 1)
        return None, None

    def _salary_match(self, resume_sal: tuple, jd_sal: tuple) -> bool:
        """薪资是否重合"""
        r_min, r_max = resume_sal
        j_min, j_max = jd_sal
        if r_min is None or j_min is None:
            return True
        # 用户期望上限 < JD 下限 → 低
        # 用户期望下限 > JD 上限 → 高
        # 中间有重合 → 匹配
        return not (r_max < j_min * 0.8 or r_min > j_max * 1.2)

    def _salary_score(self, resume_sal: tuple, jd_sal: tuple) -> float:
        """薪资匹配分数 0-100"""
        if not self._salary_match(resume_sal, jd_sal):
            return 20
        r_min, r_max = resume_sal
        j_min, j_max = jd_sal
        if r_min is None or r_max is None or j_min is None or j_max is None:
            return 50
        # 期望中位 vs JD 中位 的接近程度
        r_mid = (r_min + r_max) / 2
        j_mid = (j_min + j_max) / 2
        if j_mid == 0:
            return 50
        ratio = r_mid / j_mid
        if 0.8 <= ratio <= 1.2:
            return 100
        elif 0.6 <= ratio <= 1.5:
            return 70
        else:
            return 40

    def _location_match(self, resume_loc: str, jd_loc: str) -> bool:
        """地点模糊匹配"""
        r = resume_loc.strip().lower()
        j = jd_loc.strip().lower()
        if not r or not j:
            return True
        return r in j or j in r or r[:2] == j[:2]  # 前两个字（城市名）

    def _experience_match(self, resume_years: int, jd_data: dict) -> bool:
        """经验层级是否匹配"""
        return self._experience_score(resume_years, jd_data) >= 50

    def _experience_score(self, resume_years: int, jd_data: dict) -> float:
        """经验匹配分数 0-100"""
        if resume_years is None:
            return 80
        exp_req = jd_data.get("experience_requirement", "")
        if isinstance(exp_req, dict):
            exp_req = exp_req.get("years", "")

        if not exp_req:
            return 80  # 无要求默认高分

        jd_years = self._parse_experience_years(str(exp_req))
        if jd_years <= 0:
            return 80

        diff = abs(resume_years - jd_years)
        if diff <= 1:
            return 100
        elif diff <= 3:
            return 70
        elif diff <= 5:
            return 40
        else:
            return 20

    def _parse_experience_years(self, exp_str: str) -> int:
        """从经验要求提取所需年数"""
        # "3-5年" → 4 或 "3年以上" → 3
        m = re.search(r"(\d+)", exp_str)
        if m:
            nums = [float(x) for x in re.findall(r"\d+\.?\d*", exp_str)]
            if len(nums) >= 2:
                return int(sum(nums) / len(nums))
            return int(nums[0])
        return 0

    # ==================== 工具 ====================

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """余弦相似度"""
        if not a or not b or len(a) != len(b):
            return 0
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na * nb == 0:
            return 0
        return dot / (na * nb)

    def _generate_reason(
        self, score: float, overlap: list[str], gap: list[str], salary_ok: bool, location_ok: bool
    ) -> str:
        """生成一句话匹配原因"""
        parts = []
        if overlap:
            parts.append(f"技能重合: {'/'.join(overlap[:4])}")
        if not gap:
            parts.append("无技能短板")
        if salary_ok:
            parts.append("薪资匹配")
        if location_ok:
            parts.append("地点匹配")
        if not parts:
            parts.append("基础条件吻合")
        return "; ".join(parts[:3])

    def _recommend_type(self, score: float) -> str:
        """推荐类型"""
        if score >= self.THRESHOLD_HIGH:
            return "高度推荐"
        elif score >= self.THRESHOLD_MEDIUM:
            return "值得一试"
        else:
            return "谨慎考虑"

    @property
    def _vector_weight(self) -> float:
        return float(self.tuning_config.get("vector_weight", self.WEIGHT_VECTOR))

    @property
    def _rule_weight(self) -> float:
        return float(self.tuning_config.get("rule_weight", self.WEIGHT_RULE))

    @property
    def _rule_component_weights(self) -> dict[str, float]:
        raw = self.tuning_config.get("rule_components") or {}
        return {
            "skill": float(raw.get("skill", 0.5)),
            "experience": float(raw.get("experience", 0.2)),
            "salary": float(raw.get("salary", 0.15)),
            "location": float(raw.get("location", 0.15)),
        }

    @property
    def THRESHOLD_HIGH(self) -> int:  # noqa: N802 - keep compatibility with existing naming
        thresholds = self.tuning_config.get("thresholds") or {}
        return int(thresholds.get("high", 80))

    @property
    def THRESHOLD_MEDIUM(self) -> int:  # noqa: N802 - keep compatibility with existing naming
        thresholds = self.tuning_config.get("thresholds") or {}
        return int(thresholds.get("medium", 60))

    # ==================== 筛选 ====================

    def _apply_filters(self, results: list[RecommendResult], filters: dict) -> list[RecommendResult]:
        """应用筛选条件"""
        location = (filters.get("location") or "").strip().lower()
        industry = (filters.get("industry") or "").strip().lower()
        salary_min = filters.get("salary_min")
        salary_max = filters.get("salary_max")
        experience = (filters.get("experience") or filters.get("exp_level") or "").strip().lower()
        expected_years = self._parse_experience_filter(experience) if experience else None

        filtered = []
        for r in results:
            # 地点
            if location and location not in r.location.lower() and location not in r.location.lower()[:2]:
                continue
            # 行业
            if industry and industry not in r.industry.lower():
                continue
            # 薪资下限
            if salary_min is not None:
                jd_sal_min, _ = self._parse_salary(r.salary_range)
                if jd_sal_min and jd_sal_min < float(salary_min) * 0.7:
                    continue
            # 薪资上限
            if salary_max is not None:
                _, jd_sal_max = self._parse_salary(r.salary_range)
                if jd_sal_max and jd_sal_max > float(salary_max) * 1.3:
                    continue
            # 经验（"初级" → exp_level=2）
            if experience:
                self._parse_experience_years(experience)
                # 不精确过滤，仅关键词
                pass
            if expected_years is not None:
                jd_exp_years = self._parse_experience_years(r.experience_requirement)
                # 缺少明确经验要求时不应误杀岗位，只过滤已知明显不匹配的结果。
                if jd_exp_years > 0 and abs(jd_exp_years - expected_years) > 2:
                    continue
            filtered.append(r)

        return filtered

    # ==================== 缓存控制 ====================

    def _parse_experience_filter(self, experience: str) -> int | None:
        """将经验筛选条件统一转换为目标年限。"""
        if not experience:
            return None

        mapping = {
            "intern": 0,
            "junior": 2,
            "mid": 4,
            "senior": 7,
        }
        if experience in mapping:
            return mapping[experience]

        years = self._parse_experience_years(experience)
        return years if years > 0 else None

    @staticmethod
    def clear_cache():
        with _RECOMMEND_CACHE_LOCK:
            _RECOMMEND_CACHE.clear()


# ==================== 独立工具函数 ====================


def batch_import_jobs(
    db: Session,
    jobs: list[dict],
    source: str = "imported",
    tenant_id: int | None = None,
    user_id: int | None = None,
) -> list[int]:
    """
    批量导入岗位

    参数:
        jobs: [{"title", "company", "location", "salary_range",
                "raw_text", "industry", ...}, ...]
        source: manual / imported / api
        tenant_id: 归属租户；None=平台共享岗位（对所有租户可见）（T3-3）
        user_id: 归属用户；None=非个人岗位

    返回:
        新增的 jd_id 列表
    """
    ids = []
    for j in jobs:
        jd = JobDescription(
            title=j.get("title", ""),
            company=j.get("company", ""),
            location=j.get("location", ""),
            salary_range=j.get("salary_range", ""),
            raw_text=j.get("raw_text", j.get("description", "")),
            parsed_json=j.get("parsed_json", {}),
            source=source,
            industry=j.get("industry", ""),
            is_active=1,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        db.add(jd)
        db.flush()
        ids.append(jd.id)
    db.commit()
    JobRecommendationEngine.clear_cache()
    return ids


def record_feedback(
    db: Session, user_id: int, resume_id: int, jd_id: int, feedback_type: str, match_score: float = None
) -> dict:
    """记录用户反馈"""
    from app.models.job_recommend import JobRecommendationFeedback

    fb = JobRecommendationFeedback(
        user_id=user_id,
        resume_id=resume_id,
        jd_id=jd_id,
        feedback_type=feedback_type,
        match_score=match_score,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb.to_dict()


# ==================== 模拟岗位数据 ====================

MOCK_JOBS = [
    {
        "title": "高级前端开发工程师",
        "company": "字节跳动",
        "location": "北京",
        "salary_range": "30k-60k",
        "industry": "互联网/科技",
        "raw_text": "负责抖音电商前台核心场景开发，参与前端基础设施建设，推动前端工程化落地。要求精通Vue3/React、TypeScript、Webpack/Vite性能优化。",
        "parsed_json": {
            "required_skills": ["Vue3", "React", "TypeScript", "Webpack", "Vite", "Node.js"],
            "experience_requirement": "3-5年",
            "education_requirement": "本科及以上",
            "responsibilities": ["电商前台开发", "前端基建", "工程化落地"],
        },
    },
    {
        "title": "Python 后端开发工程师",
        "company": "阿里巴巴",
        "location": "杭州",
        "salary_range": "25k-50k",
        "industry": "互联网/电商",
        "raw_text": "负责电商中台服务设计与开发，高性能API开发，数据库优化。要求精通Python、FastAPI/Django、MySQL、Redis、Kafka。",
        "parsed_json": {
            "required_skills": ["Python", "FastAPI", "Django", "MySQL", "Redis", "Kafka", "Docker"],
            "experience_requirement": "3-5年",
            "education_requirement": "本科及以上",
            "responsibilities": ["中台服务开发", "高性能API", "数据库优化"],
        },
    },
    {
        "title": "AI 算法工程师（NLP方向）",
        "company": "腾讯",
        "location": "深圳",
        "salary_range": "35k-70k",
        "industry": "互联网/AI",
        "raw_text": "从事大模型/NLP应用研究，负责文本理解、对话系统、RAG系统开发。要求精通Transformer、LangChain、PyTorch。",
        "parsed_json": {
            "required_skills": ["Python", "PyTorch", "LangChain", "Transformer", "RAG", "NLP"],
            "experience_requirement": "3-5年",
            "education_requirement": "硕士及以上",
            "responsibilities": ["NLP应用研究", "对话系统开发", "RAG系统构建"],
        },
    },
    {
        "title": "Java 后端开发工程师",
        "company": "美团",
        "location": "北京",
        "salary_range": "25k-45k",
        "industry": "互联网/本地生活",
        "raw_text": "负责交易核心链路服务开发，高并发系统设计与优化。要求精通Java、Spring Boot、MySQL、Redis、微服务架构。",
        "parsed_json": {
            "required_skills": ["Java", "Spring Boot", "MySQL", "Redis", "微服务", "Kafka"],
            "experience_requirement": "3-5年",
            "education_requirement": "本科及以上",
            "responsibilities": ["交易链路开发", "高并发优化", "微服务设计"],
        },
    },
    {
        "title": "全栈开发工程师",
        "company": "小红书",
        "location": "上海",
        "salary_range": "28k-55k",
        "industry": "互联网/社交",
        "raw_text": "负责社区产品全栈开发，从原型到交付全流程。要求精通Vue3/React、Python/Go、PostgreSQL，有全栈项目经验。",
        "parsed_json": {
            "required_skills": ["Vue3", "React", "Python", "Go", "PostgreSQL", "Redis"],
            "experience_requirement": "3-5年",
            "education_requirement": "本科及以上",
            "responsibilities": ["全栈开发", "产品迭代", "技术方案设计"],
        },
    },
    {
        "title": "DevOps/SRE 工程师",
        "company": "华为云",
        "location": "深圳",
        "salary_range": "25k-50k",
        "industry": "云计算/科技",
        "raw_text": "负责云原生基础设施运维，CI/CD流水线建设，K8s集群管理。要求精通Docker、Kubernetes、Terraform、CI/CD工具链。",
        "parsed_json": {
            "required_skills": ["Docker", "Kubernetes", "Terraform", "Jenkins", "Ansible", "Linux"],
            "experience_requirement": "3-5年",
            "education_requirement": "本科及以上",
            "responsibilities": ["基础设施运维", "CI/CD建设", "K8s管理"],
        },
    },
    {
        "title": "初级前端开发",
        "company": "网易",
        "location": "广州",
        "salary_range": "15k-25k",
        "industry": "互联网/游戏",
        "raw_text": "负责官网和运营活动页面开发。要求熟悉HTML/CSS/JavaScript，了解Vue或React框架，有良好的学习能力。",
        "parsed_json": {
            "required_skills": ["HTML", "CSS", "JavaScript", "Vue", "React"],
            "experience_requirement": "1-3年",
            "education_requirement": "本科及以上",
            "responsibilities": ["前端页面开发", "运营活动开发"],
        },
    },
    {
        "title": "资深数据工程师",
        "company": "百度",
        "location": "北京",
        "salary_range": "35k-65k",
        "industry": "互联网/AI",
        "raw_text": "负责大数据平台建设，离线/实时数仓开发，数据治理。要求精通Spark/Flink、Hadoop、SQL、数据建模。",
        "parsed_json": {
            "required_skills": ["Spark", "Flink", "Hadoop", "SQL", "Hive", "Kafka", "Python"],
            "experience_requirement": "5-10年",
            "education_requirement": "本科及以上",
            "responsibilities": ["大数据平台建设", "数仓开发", "数据治理"],
        },
    },
    {
        "title": "产品经理（AI方向）",
        "company": "商汤科技",
        "location": "上海",
        "salary_range": "30k-55k",
        "industry": "AI/科技",
        "raw_text": "负责AI产品规划和落地，需求分析，跨团队协作。要求2年以上AI产品经验，了解机器学习基础，有ToB产品经验优先。",
        "parsed_json": {
            "required_skills": ["产品规划", "需求分析", "项目管理", "AI", "数据分析"],
            "experience_requirement": "3-5年",
            "education_requirement": "本科及以上",
            "responsibilities": ["AI产品规划", "需求分析", "跨团队协作"],
        },
    },
    {
        "title": "测试开发工程师",
        "company": "快手",
        "location": "北京",
        "salary_range": "25k-45k",
        "industry": "互联网/短视频",
        "raw_text": "负责质量保障体系建设，自动化测试框架开发，性能测试。要求精通Python/Java、测试框架、CI/CD集成。",
        "parsed_json": {
            "required_skills": ["Python", "Java", "Selenium", "pytest", "JMeter", "CI/CD"],
            "experience_requirement": "3-5年",
            "education_requirement": "本科及以上",
            "responsibilities": ["质量保障", "自动化测试", "性能测试"],
        },
    },
]
