# -*- coding: utf-8 -*-
"""
匹配度评分权重配置

所有权重可在初始化时覆盖，支持按岗位类型微调。
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ScoringWeights:
    """各维度权重（总和=1.0）"""
    # ── 核心维度 ──
    skill: float = 0.35        # 技能匹配（最高权重）
    project: float = 0.15      # 项目经历
    experience: float = 0.15   # 工作经验/年限
    education: float = 0.10    # 学历

    # ── 辅助维度 ──
    keyword: float = 0.15      # 关键词覆盖（JD 隐性要求）
    bonus: float = 0.10        # 加分项（nice_to_have / 额外亮点）

    # ── 扣分项 ──
    penalty_missing_required: int = 15   # 缺失必备技能扣分
    penalty_exp_mismatch: int = 10       # 经验不匹配扣分
    penalty_edu_mismatch: int = 5        # 学历不匹配扣分

    def validate(self):
        total = self.skill + self.project + self.experience + self.education + self.keyword + self.bonus
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"权重之和应为 1.0，当前为 {total}")

    def as_dict(self) -> Dict[str, float]:
        return {
            "skill": self.skill,
            "project": self.project,
            "experience": self.experience,
            "education": self.education,
            "keyword": self.keyword,
            "bonus": self.bonus,
        }


# ===== 岗位类型微调配置 =====

# 技术岗：技能权重更高
TECH_WEIGHTS = ScoringWeights(skill=0.40, project=0.15, experience=0.12, education=0.08, keyword=0.15, bonus=0.10)

# 产品/运营岗：经验+项目权重更高
PM_WEIGHTS = ScoringWeights(skill=0.25, project=0.20, experience=0.20, education=0.10, keyword=0.15, bonus=0.10)

# 校招/实习：学历+项目权重更高
GRAD_WEIGHTS = ScoringWeights(skill=0.25, project=0.25, experience=0.05, education=0.20, keyword=0.15, bonus=0.10)

# 默认配置
DEFAULT_WEIGHTS = ScoringWeights()


def get_weights_for_job(job_title: str = "", exp_years: int = 0) -> ScoringWeights:
    """根据岗位和年限自动选择权重配置"""
    title_lower = str(job_title or "").lower()
    try:
        exp_years = int(exp_years or 0)
    except (TypeError, ValueError):
        exp_years = 0

    if exp_years <= 1:
        return GRAD_WEIGHTS
    if any(kw in title_lower for kw in ["产品", "运营", "市场", "销售"]):
        return PM_WEIGHTS
    if any(kw in title_lower for kw in ["开发", "工程", "算法", "测试", "运维", "架构", "后端", "前端"]):
        return TECH_WEIGHTS
    return DEFAULT_WEIGHTS
