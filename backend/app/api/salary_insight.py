"""薪资洞察 API — 基于 JD 库的薪资分析与对比

计算全部在 app/services/salary_evidence.py：这里只做查询条件与响应组装。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.salary_evidence import (
    collect_samples,
    group_by_city,
    percentile_rank,
    summarize,
)
from app.utils.response import ok

router = APIRouter()


@router.get("/overview", summary="薪资总览")
async def salary_overview(
    position: str = Query("", description="岗位关键词"),
    city: str = Query("", description="城市"),
    industry: str = Query("", description="行业"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基于 JD 库的薪资概览统计。样本量与支撑岗位 id 一并返回。"""
    samples, total_jds = collect_samples(db, position=position, city=city, industry=industry)
    evidence = summarize(samples, total_jds=total_jds)
    payload = evidence.to_dict()
    payload["filters"] = {"position": position, "city": city, "industry": industry}
    return ok(payload)


@router.get("/compare", summary="薪资对比")
async def salary_compare(
    position: str = Query("", description="岗位关键词"),
    cities: str = Query("", description="城市列表，逗号分隔"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """不同城市的薪资对比，分位数与总览用同一套算法。"""
    samples, _ = collect_samples(db, position=position, cities=cities.split(","))
    comparison = group_by_city(samples)
    return ok(
        {
            "position": position or "全部",
            "city_count": len(comparison),
            "comparison": comparison,
            "sample_size": len(samples),
            "low_confidence": len(samples) < 5,
        }
    )


@router.get("/expectation-check", summary="期望薪资合理性评估")
async def salary_expectation_check(
    position: str = Query(..., description="目标岗位"),
    city: str = Query("", description="目标城市"),
    expected_min: float = Query(..., description="期望最低薪资(K/月)"),
    expected_max: float = Query(..., description="期望最高薪资(K/月)"),
    experience_years: int = Query(0, description="工作年限"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据市场数据评估用户期望薪资的合理性"""
    samples, _ = collect_samples(db, position=position, city=city)
    evidence = summarize(samples)
    expected_range = f"{expected_min}-{expected_max}K"

    if not evidence.has_data:
        return ok(
            {
                "has_data": False,
                "expected_range": expected_range,
                "sample_size": 0,
                "sample_jd_ids": [],
                "message": "市场数据不足，无法评估。建议先导入更多该岗位的JD",
            }
        )

    mids = [sample.mid_k for sample in samples]
    p25, p50, p75 = evidence.p25, evidence.p50, evidence.p75
    expected_mid = (expected_min + expected_max) / 2

    if expected_max <= p25:
        level = "保守"
        suggestion = f"你的期望薪资低于市场 25 分位（{p25}K），可能有较大谈薪空间"
    elif expected_min >= p75:
        level = "偏高"
        suggestion = f"你的期望薪资高于市场 75 分位（{p75}K），需突出核心竞争力来支撑"
    elif expected_mid >= p50:
        level = "合理偏上"
        suggestion = f"你的期望薪资在市场中位数（{p50}K）附近偏上，合理且有议价空间"
    else:
        level = "合理"
        suggestion = "你的期望薪资在市场合理范围内，有一定谈薪空间"

    exp_note = ""
    if experience_years <= 2 and expected_mid > p75:
        exp_note = "考虑到经验较少，建议适当降低期望或突出项目成果"
    elif experience_years >= 8 and expected_mid < p50:
        exp_note = "以你的经验年限，薪资期望可能偏低，建议适当提高"

    return ok(
        {
            "has_data": True,
            "expected_range": expected_range,
            "sample_size": evidence.sample_size,
            "low_confidence": evidence.low_confidence,
            "sample_jd_ids": evidence.sample_jd_ids,
            "market_stats": {
                "avg": evidence.avg_mid,
                "p25": p25,
                "p50": p50,
                "p75": p75,
            },
            "assessment": {
                "level": level,
                "suggestion": suggestion,
                "experience_note": exp_note,
            },
            "percentile_rank": percentile_rank(mids, expected_mid),
        }
    )
