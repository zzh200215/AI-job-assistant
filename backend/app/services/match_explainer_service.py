# -*- coding: utf-8 -*-
"""
匹配度解释器 — 规则计算 + LLM 自然语言解释

流程:
  1. 规则引擎计算 6 维基础分（skill / project / experience / education / keyword / bonus）
  2. 加权汇总总分
  3. LLM 根据原始分生成每项的"解释原因" + 风险点 + 优化建议
  4. 返回完整 ExplainResult

不依赖 LLM 做评分计算，LLM 只负责生成自然语言解释。
"""
import json
import re
import logging
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

from app.models.history import Resume, JobDescription
from app.services.scoring_config import ScoringWeights, get_weights_for_job
from app.services.llm_service import chat_json

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

@dataclass
class DimensionScore:
    """单维度评分"""
    name: str
    score: float          # 0-100
    weight: float         # 权重
    weighted_score: float # score * weight
    reason: str           # LLM 生成的自然语言解释
    details: List[str] = field(default_factory=list)  # 明细项


@dataclass
class ExplainResult:
    """完整解释结果"""
    overall_score: float
    overall_reason: str
    dimensions: List[DimensionScore]
    skill_match: Dict  = field(default_factory=dict)  # 技能命中详情
    risk_points: List[str] = field(default_factory=list)
    optimization_suggestions: List[str] = field(default_factory=list)
    recommendation: str = ""  # 强烈推荐 / 可以投递 / 谨慎投递 / 不建议投递
    weights_used: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "overall_score": round(self.overall_score, 1),
            "overall_reason": self.overall_reason,
            "dimensions": [
                {
                    "name": d.name,
                    "score": round(d.score, 1),
                    "weight": d.weight,
                    "weighted_score": round(d.weighted_score, 1),
                    "reason": d.reason,
                    "details": d.details,
                }
                for d in self.dimensions
            ],
            "skill_match": self.skill_match,
            "risk_points": self.risk_points,
            "optimization_suggestions": self.optimization_suggestions,
            "recommendation": self.recommendation,
            "weights_used": self.weights_used,
        }


# ==================== 规则引擎 ====================

class MatchExplainer:
    """匹配度解释器"""

    def __init__(self, weights: Optional[ScoringWeights] = None):
        self.weights = weights or ScoringWeights()
        self.weights.validate()

    def explain(self, resume: Resume, jd: JobDescription) -> ExplainResult:
        """对外入口：接收 ORM 对象，返回完整解释"""
        resume_data = resume.parsed_json or {}
        jd_data = jd.parsed_json or {}
        job_title = jd_data.get("title") or jd.title or ""
        years_exp = resume_data.get("years_exp", 0)

        # 兼容旧记录或导入数据：parsed_json 缺字段时回退到 ORM 列
        if not isinstance(resume_data.get("skills"), list):
            resume_data["skills"] = []
        if not resume_data.get("project_experience") and resume_data.get("projects"):
            resume_data["project_experience"] = resume_data.get("projects") or []
        if not jd_data.get("required_skills") and getattr(jd, "skill_tags", None):
            jd_data["required_skills"] = jd.skill_tags or []
        if jd_data.get("nice_to_have") is None:
            jd_data["nice_to_have"] = []
        if not jd_data.get("experience_requirement") and getattr(jd, "experience_requirement", None):
            jd_data["experience_requirement"] = jd.experience_requirement
        if not jd_data.get("education_requirement") and getattr(jd, "education_requirement", None):
            jd_data["education_requirement"] = jd.education_requirement
        if not jd_data.get("title") and getattr(jd, "title", None):
            jd_data["title"] = jd.title

        # 自动选择权重
        self.weights = get_weights_for_job(job_title, years_exp)

        # 1. 规则计算各维度
        skill_score, skill_details, skill_match = self._calc_skill(resume_data, jd_data)
        project_score, project_details = self._calc_project(resume_data, jd_data)
        exp_score, exp_details = self._calc_experience(resume_data, jd_data)
        edu_score, edu_details = self._calc_education(resume_data, jd_data)
        keyword_score, keyword_details = self._calc_keyword(resume_data, jd_data)
        bonus_score, bonus_details = self._calc_bonus(resume_data, jd_data)

        # 扣分
        penalty = 0
        missing_req = skill_match.get("missing_required", [])
        if missing_req:
            penalty += self.weights.penalty_missing_required
        if exp_details and "不匹配" in " ".join(exp_details):
            penalty += self.weights.penalty_exp_mismatch
        if edu_details and "不匹配" in " ".join(edu_details):
            penalty += self.weights.penalty_edu_mismatch

        # 2. 加权汇总
        dims = [
            DimensionScore("技能匹配", skill_score, self.weights.skill, 0, "", skill_details),
            DimensionScore("项目经历", project_score, self.weights.project, 0, "", project_details),
            DimensionScore("工作经验", exp_score, self.weights.experience, 0, "", exp_details),
            DimensionScore("学历要求", edu_score, self.weights.education, 0, "", edu_details),
            DimensionScore("关键词覆盖", keyword_score, self.weights.keyword, 0, "", keyword_details),
            DimensionScore("加分项", bonus_score, self.weights.bonus, 0, "", bonus_details),
        ]
        for d in dims:
            d.weighted_score = d.score * d.weight

        raw_total = sum(d.weighted_score for d in dims)
        overall = max(0, min(100, raw_total - penalty))

        # 3. LLM 生成解释文本
        try:
            llm_explain = self._llm_explain(dims, skill_match, overall, resume_data, jd_data)
        except Exception as e:
            logger.warning(f"LLM 解释生成失败，使用规则兜底: {e}")
            llm_explain = self._fallback_explain(dims, overall)

        # 合并 LLM 结果到 dims
        for d in dims:
            d_key = {"技能匹配": "skill", "项目经历": "project", "工作经验": "experience",
                     "学历要求": "education", "关键词覆盖": "keyword", "加分项": "bonus"}.get(d.name, "")
            d.reason = llm_explain.get("reasons", {}).get(d_key, "")

        # 推荐等级
        rec = self._recommendation(overall, missing_req)

        return ExplainResult(
            overall_score=overall,
            overall_reason=llm_explain.get("overall", ""),
            dimensions=dims,
            skill_match=skill_match,
            risk_points=llm_explain.get("risk_points", []),
            optimization_suggestions=llm_explain.get("suggestions", []),
            recommendation=rec,
            weights_used=self.weights.as_dict(),
        )

    # ==================== 规则评分（6 维）====================

    def _calc_skill(self, resume: Dict, jd: Dict) -> Tuple[float, List[str], Dict]:
        """技能匹配：Jaccard 相似度 + 等级匹配"""
        r_skills = set(self._extract_str_list(resume, "skills"))
        jd_req = set(self._extract_str_list(jd, "required_skills"))
        jd_nice = set(self._extract_str_list(jd, "nice_to_have"))
        all_req = jd_req | jd_nice

        if not all_req:
            return 80, ["JD 无明确技能要求，默认中高分"], {"matched": [], "missing_required": [], "missing_nice": []}

        matched = r_skills & all_req
        missing_req = jd_req - r_skills
        missing_nice = jd_nice - r_skills

        # Jaccard 基础分
        jaccard = len(matched) / len(all_req) if all_req else 0
        base = jaccard * 70  # 基础分占比 70/100

        # 命中加分：每命中一个 required +5，nice_to_have +3
        hit_req = len(matched & jd_req)
        hit_nice = len(matched & jd_nice)
        bonus = min(30, hit_req * 5 + hit_nice * 3)

        score = min(100, base + bonus)

        details = []
        if matched:
            details.append(f"命中 {len(matched)} 项技能: {', '.join(list(matched)[:6])}")
        if missing_req:
            details.append(f"缺失 {len(missing_req)} 项核心技能: {', '.join(list(missing_req)[:5])}（-{self.weights.penalty_missing_required}分）")
        if not matched and missing_req:
            details.append("技能栈与岗位要求差距较大")

        return score, details, {
            "matched": list(matched),
            "missing_required": list(missing_req),
            "missing_nice": list(missing_nice),
            "total_required": len(jd_req),
            "total_nice": len(jd_nice),
        }

    def _calc_project(self, resume: Dict, jd: Dict) -> Tuple[float, List[str]]:
        """项目经历匹配"""
        projects = resume.get("project_experience", []) or resume.get("projects", [])
        if not projects:
            return 20, ["无项目经历"]

        jd_skills = set(self._extract_str_list(jd, "required_skills"))
        jd_resp = set(self._extract_str_list(jd, "responsibilities"))

        hit_count = 0
        total_tech = 0
        for proj in projects:
            techs = set(self._extract_str_list(proj, "tech"))
            desc = (proj.get("desc", "") or "").lower()
            total_tech += len(techs)
            hit_count += len(techs & jd_skills)
            # 职责关键词匹配
            for resp in jd_resp:
                if resp in desc:
                    hit_count += 2  # 每条职责命中+2

        if total_tech == 0:
            return 30, ["项目经历缺少技术栈描述"]

        ratio = hit_count / max(total_tech, 1)
        count_bonus = min(15, len(projects) * 5)  # 多项目加分
        score = min(100, ratio * 60 + count_bonus + 20)

        details = [f"共 {len(projects)} 个项目，技术栈命中率 {ratio:.0%}"]
        if hit_count > 0:
            details.append(f"项目技能与 JD 重合 {hit_count} 项")
        return score, details

    def _calc_experience(self, resume: Dict, jd: Dict) -> Tuple[float, List[str]]:
        """工作经验匹配"""
        resume_years = resume.get("years_exp", 0)
        exp_req = jd.get("experience_requirement", "")
        if isinstance(exp_req, dict):
            exp_req = exp_req.get("years", "")
        exp_str = str(exp_req)

        if not exp_str or exp_str == "不限":
            return 80, ["无经验要求"]

        nums = re.findall(r"\d+", exp_str)
        if not nums:
            return 70, [f"经验要求: {exp_str}"]

        if len(nums) >= 2:
            jd_min, jd_max = int(nums[0]), int(nums[1])
            jd_mid = (jd_min + jd_max) / 2
        else:
            jd_mid = float(nums[0])

        diff = abs(resume_years - jd_mid)
        if diff <= 1:
            score = 100
            detail = f"经验{resume_years}年与要求{exp_str}高度吻合"
        elif diff <= 3:
            score = 70
            detail = f"经验{resume_years}年，与要求{exp_str}接近"
        elif diff <= 5:
            score = 40
            detail = f"经验{resume_years}年，与要求{exp_str}有差距"
        else:
            score = 20
            detail = f"经验{resume_years}年，与要求{exp_str}差距较大"

        return score, [detail]

    def _calc_education(self, resume: Dict, jd: Dict) -> Tuple[float, List[str]]:
        """学历匹配"""
        resume_edu = (resume.get("education", "") or "").strip()
        jd_edu = jd.get("education_requirement", "") or ""

        if not jd_edu or jd_edu == "不限":
            return 80, ["无学历要求"]

        level = {"博士": 4, "硕士": 3, "本科": 2, "大专": 1, "高中": 0}
        r_level = level.get(resume_edu, 1)
        j_level = level.get(jd_edu, 2)

        if r_level >= j_level:
            return 100, [f"{resume_edu}满足{jd_edu}要求"]
        elif r_level == j_level - 1:
            return 60, [f"{resume_edu}略低于{jd_edu}要求"]
        else:
            return 20, [f"{resume_edu}与{jd_edu}要求不匹配"]

    def _calc_keyword(self, resume: Dict, jd: Dict) -> Tuple[float, List[str]]:
        """关键词覆盖：JD 中的隐性关键词在简历中出现的比例"""
        jd_raw = jd.get("keywords", []) or jd.get("hidden_requirements", [])
        if not jd_raw:
            return 75, ["JD 无额外关键词"]

        first_non_null = next((item for item in jd_raw if item is not None), None)
        if isinstance(first_non_null, dict):
            jd_keywords = set()
            for item in jd_raw:
                if isinstance(item, dict):
                    keyword = self._clean_text(item.get("requirement") or item.get("reason"))
                    if keyword:
                        jd_keywords.add(keyword)
        else:
            jd_keywords = {keyword for keyword in (self._clean_text(k) for k in jd_raw) if keyword}

        resume_text = json.dumps(resume, ensure_ascii=False).lower()
        hit = [kw for kw in jd_keywords if kw in resume_text]

        if not jd_keywords:
            return 75, []

        ratio = len(hit) / len(jd_keywords)
        score = min(100, ratio * 80 + 20)

        details = [f"隐性关键词覆盖 {len(hit)}/{len(jd_keywords)}"]
        if hit:
            details.append(f"命中: {', '.join(hit[:4])}")
        return score, details

    def _calc_bonus(self, resume: Dict, jd: Dict) -> Tuple[float, List[str]]:
        """加分项匹配"""
        jd_nice = set(self._extract_str_list(jd, "nice_to_have"))
        if not jd_nice:
            return 50, ["JD 无额外加分项"]

        r_skills = set(self._extract_str_list(resume, "skills"))
        matched = r_skills & jd_nice
        ratio = len(matched) / len(jd_nice) if jd_nice else 0
        score = min(100, ratio * 100)

        details = []
        if matched:
            details.append(f"满足 {len(matched)} 项加分技能: {', '.join(list(matched)[:4])}")
        else:
            details.append(f"未满足加分项: {', '.join(list(jd_nice)[:4])}")
        return score, details

    # ==================== LLM 解释生成 ====================

    _EXPLAIN_PROMPT = """你是一名招聘专家。请根据候选人的简历各维度评分，生成匹配度解释。

## 综合评分
{overall_score}

## 各维度得分
{dimensions_text}

## 技能匹配详情
{skill_match_text}

## 任务
输出 JSON，只输出 JSON：
{{
  "overall": "50-80字的综合解释",
  "reasons": {{
    "skill": "技能匹配解释(30-50字)",
    "project": "项目经历解释(30-50字)",
    "experience": "工作经验解释(20-40字)",
    "education": "学历匹配解释(20-40字)",
    "keyword": "关键词覆盖解释(20-40字)",
    "bonus": "加分项解释(20-40字)"
  }},
  "risk_points": ["风险点1(15字内)", "风险点2"],
  "suggestions": ["改进建议1(20字内)", "建议2", "建议3"]
}}
"""

    def _llm_explain(self, dims: List[DimensionScore], skill_match: Dict,
                     overall: float, resume: Dict, jd: Dict) -> Dict:
        dims_text = "\n".join([
            f"- {d.name}: {d.score:.0f}分 (权重{d.weight:.2f})"
            + (f" {'; '.join(d.details[:2])}" if d.details else "")
            for d in dims
        ])
        skill_text = json.dumps({
            "matched": skill_match.get("matched", [])[:8],
            "missing_required": skill_match.get("missing_required", [])[:5],
        }, ensure_ascii=False)

        prompt = self._EXPLAIN_PROMPT.format(
            overall_score=f"{overall:.0f}/100",
            dimensions_text=dims_text,
            skill_match_text=skill_text,
        )
        return chat_json(prompt)

    def _fallback_explain(self, dims: List[DimensionScore], overall: float) -> Dict:
        """LLM 失败时的纯规则兜底"""
        reasons = {}
        for d in dims:
            if d.score >= 80:
                reasons[{"技能匹配": "skill", "项目经历": "project", "工作经验": "experience",
                         "学历要求": "education", "关键词覆盖": "keyword", "加分项": "bonus"}.get(d.name, "")] = f"{d.name}表现良好"
            elif d.score >= 60:
                reasons[{"技能匹配": "skill", "项目经历": "project", "工作经验": "experience",
                         "学历要求": "education", "关键词覆盖": "keyword", "加分项": "bonus"}.get(d.name, "")] = f"{d.name}基本达标"
            else:
                reasons[{"技能匹配": "skill", "项目经历": "project", "工作经验": "experience",
                         "学历要求": "education", "关键词覆盖": "keyword", "加分项": "bonus"}.get(d.name, "")] = f"{d.name}需提升"

        return {
            "overall": f"综合匹配度 {overall:.0f}分",
            "reasons": reasons,
            "risk_points": ["详细分析请重新请求"],
            "suggestions": ["完善技能栈", "优化项目描述", "补充量化成果"],
        }

    # ==================== 推荐等级 ====================

    def _recommendation(self, score: float, missing_req: List) -> str:
        if score >= 85 and not missing_req:
            return "强烈推荐"
        elif score >= 70:
            return "可以投递"
        elif score >= 50:
            return "谨慎投递"
        else:
            return "不建议投递"

    # ==================== 工具 ====================

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).lower().strip()
        return text

    @staticmethod
    def _extract_str_list(data: Dict, key: str) -> List[str]:
        """从 dict 中提取字符串列表（兼容字符串列表和对象列表）"""
        items = data.get(key, [])
        if not isinstance(items, list):
            return []
        result = []
        for item in items:
            if isinstance(item, str):
                value = MatchExplainer._clean_text(item)
                if value:
                    result.append(value)
            elif isinstance(item, dict):
                # 支持 {"skill": "Python", "level": "精通"} 格式
                for k in ["skill", "name", "requirement", "responsibility"]:
                    value = MatchExplainer._clean_text(item.get(k))
                    if value:
                        result.append(value)
                        break
        return result
