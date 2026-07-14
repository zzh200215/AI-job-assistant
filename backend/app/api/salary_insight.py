"""薪资洞察 API — 基于 JD 库的薪资分析与对比"""

import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import JobDescription
from app.models.user import User
from app.utils.response import ok

router = APIRouter()


def _parse_salary_range(salary_str: str) -> tuple | None:
    """解析薪资范围字符串，返回 (min_k, max_k) 千/月"""
    if not salary_str:
        return None
    # 匹配数字模式：如 "15-25K", "15000-25000", "15k-25k", "1.5w-2.5w"
    nums = re.findall(r"[\d.]+", salary_str)
    if len(nums) < 2:
        return None

    try:
        low, high = float(nums[0]), float(nums[1])
    except (ValueError, IndexError):
        return None

    # 判断单位
    s_lower = salary_str.lower()
    if "w" in s_lower or "万" in salary_str:
        # 万/年 → 千/月
        return (round(low * 10 / 12, 1), round(high * 10 / 12, 1))
    elif "k" in s_lower or "K" in salary_str:
        return (low, high)
    else:
        # 纯数字，>= 1000 认为是元/月 → 千/月
        if low >= 1000:
            return (round(low / 1000, 1), round(high / 1000, 1))
        # < 100 认为是 K
        return (low, high)


@router.get("/overview", summary="薪资总览")
async def salary_overview(
    position: str = Query("", description="岗位关键词"),
    city: str = Query("", description="城市"),
    industry: str = Query("", description="行业"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基于 JD 库的薪资概览统计"""
    q = db.query(JobDescription).filter(
        JobDescription.salary_range.isnot(None),
        JobDescription.salary_range != "",
    )

    if position:
        q = q.filter(JobDescription.title.contains(position))
    if city:
        q = q.filter(JobDescription.location.contains(city))
    if industry:
        q = q.filter(JobDescription.industry.contains(industry))

    jds = q.all()

    # 解析薪资
    salary_data = []
    for jd in jds:
        parsed = _parse_salary_range(jd.salary_range or "")
        if parsed:
            salary_data.append(
                {
                    "id": jd.id,
                    "title": jd.title,
                    "company": jd.company,
                    "location": jd.location,
                    "salary_range": jd.salary_range,
                    "salary_min_k": parsed[0],
                    "salary_max_k": parsed[1],
                    "salary_mid_k": round((parsed[0] + parsed[1]) / 2, 1),
                }
            )

    if not salary_data:
        return ok(
            {
                "has_data": False,
                "total_jds": len(jds),
                "parsed_count": 0,
                "message": "未找到可解析的薪资数据，请先导入更多包含薪资信息的JD",
            }
        )

    # 统计
    min_vals = [d["salary_min_k"] for d in salary_data]
    max_vals = [d["salary_max_k"] for d in salary_data]
    mid_vals = [d["salary_mid_k"] for d in salary_data]

    # 分位数
    sorted_mid = sorted(mid_vals)
    n = len(sorted_mid)

    def percentile(arr, p):
        idx = max(0, min(n - 1, int(n * p / 100)))
        return arr[idx]

    # 薪资分布（按区间统计）
    distribution = {}
    for mid in mid_vals:
        bucket = int(mid // 5) * 5  # 5K一档
        label = f"{bucket}-{bucket + 5}K"
        distribution[label] = distribution.get(label, 0) + 1

    return ok(
        {
            "has_data": True,
            "total_jds": len(jds),
            "parsed_count": len(salary_data),
            "statistics": {
                "avg_min": round(sum(min_vals) / len(min_vals), 1),
                "avg_max": round(sum(max_vals) / len(max_vals), 1),
                "avg_mid": round(sum(mid_vals) / len(mid_vals), 1),
                "p10": percentile(sorted_mid, 10),
                "p25": percentile(sorted_mid, 25),
                "p50": percentile(sorted_mid, 50),
                "p75": percentile(sorted_mid, 75),
                "p90": percentile(sorted_mid, 90),
            },
            "distribution": dict(sorted(distribution.items(), key=lambda x: int(x[0].split("-")[0]))),
            "filters": {
                "position": position,
                "city": city,
                "industry": industry,
            },
        }
    )


@router.get("/compare", summary="薪资对比")
async def salary_compare(
    position: str = Query("", description="岗位关键词"),
    cities: str = Query("", description="城市列表，逗号分隔"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """不同城市/岗位的薪资对比"""
    q = db.query(JobDescription).filter(
        JobDescription.salary_range.isnot(None),
        JobDescription.salary_range != "",
    )

    if position:
        q = q.filter(JobDescription.title.contains(position))

    city_list = [c.strip() for c in cities.split(",") if c.strip()] if cities else []
    jds = q.all()

    # 按城市分组
    city_data = {}
    for jd in jds:
        loc = jd.location or "未知"
        # 如果指定了城市列表，只保留匹配的
        if city_list and not any(c in loc for c in city_list):
            continue

        parsed = _parse_salary_range(jd.salary_range or "")
        if not parsed:
            continue

        if loc not in city_data:
            city_data[loc] = []
        city_data[loc].append(
            {
                "min_k": parsed[0],
                "max_k": parsed[1],
                "mid_k": round((parsed[0] + parsed[1]) / 2, 1),
            }
        )

    # 计算每个城市的统计
    comparison = []
    for city, items in sorted(city_data.items(), key=lambda x: -len(x[1])):
        mids = [i["mid_k"] for i in items]
        comparison.append(
            {
                "city": city,
                "count": len(items),
                "avg_min": round(sum(i["min_k"] for i in items) / len(items), 1),
                "avg_max": round(sum(i["max_k"] for i in items) / len(items), 1),
                "avg_mid": round(sum(mids) / len(mids), 1),
                "p25": sorted(mids)[max(0, len(mids) // 4)],
                "p50": sorted(mids)[len(mids) // 2],
                "p75": sorted(mids)[min(len(mids) - 1, 3 * len(mids) // 4)],
            }
        )

    return ok(
        {
            "position": position or "全部",
            "city_count": len(comparison),
            "comparison": comparison,
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
    q = db.query(JobDescription).filter(
        JobDescription.salary_range.isnot(None),
        JobDescription.salary_range != "",
        JobDescription.title.contains(position),
    )
    if city:
        q = q.filter(JobDescription.location.contains(city))

    jds = q.all()

    mid_vals = []
    for jd in jds:
        parsed = _parse_salary_range(jd.salary_range or "")
        if parsed:
            mid_vals.append(round((parsed[0] + parsed[1]) / 2, 1))

    if not mid_vals:
        return ok(
            {
                "has_data": False,
                "expected_range": f"{expected_min}-{expected_max}K",
                "message": "市场数据不足，无法评估。建议先导入更多该岗位的JD",
            }
        )

    sorted_mids = sorted(mid_vals)
    n = len(sorted_mids)
    avg = round(sum(mid_vals) / n, 1)
    p25 = sorted_mids[n // 4]
    p50 = sorted_mids[n // 2]
    p75 = sorted_mids[min(n - 1, 3 * n // 4)]

    expected_mid = (expected_min + expected_max) / 2

    # 合理性评估
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

    # 经验调整建议
    exp_note = ""
    if experience_years <= 2 and expected_mid > p75:
        exp_note = "考虑到经验较少，建议适当降低期望或突出项目成果"
    elif experience_years >= 8 and expected_mid < p50:
        exp_note = "以你的经验年限，薪资期望可能偏低，建议适当提高"

    return ok(
        {
            "has_data": True,
            "sample_size": n,
            "expected_range": f"{expected_min}-{expected_max}K",
            "market_stats": {
                "avg": avg,
                "p25": p25,
                "p50": p50,
                "p75": p75,
            },
            "assessment": {
                "level": level,
                "suggestion": suggestion,
                "experience_note": exp_note,
            },
            "percentile_rank": round(sum(1 for m in mid_vals if m <= expected_mid) / n * 100, 1),
        }
    )
