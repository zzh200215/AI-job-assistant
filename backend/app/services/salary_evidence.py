"""B2.2: salary numbers that name the postings behind them.

Three endpoints each did their own parsing and quantile math, using three
different formulas — `int(n*p/100)`, `len//4` and `3*len//4` — so the same "p25"
printed a different number depending on which page asked. None of them returned
the sample, so a candidate looking at "中位数 25K" could not tell whether it came
from 2 postings or 200.

One implementation lives here. It reports the sample size and the posting ids it
was computed from, and flags a sample too small to carry the precision it looks
like.

The corpus is the whole JD table, deliberately: a career-planning product wants
the market, not one account's import history. The tenant/job-visibility filters
used by recommendations do not apply here, and that is a decision rather than an
oversight.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription

# Below this the spread is noise; p10/p90 on four postings is not a market.
MIN_RELIABLE_SAMPLE = 5
MAX_TRACED_JD_IDS = 50

_NUMBER_PAIR = re.compile(r"([\d.]+)\s*(?:k|万|w|元)?\s*[-~—至到]\s*([\d.]+)", re.IGNORECASE)


@dataclass
class SalarySample:
    jd_id: int | None
    title: str
    company: str
    location: str
    raw: str
    min_k: float
    max_k: float
    mid_k: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SalaryEvidence:
    """Quantiles plus the evidence that produced them."""

    sample_size: int = 0
    parsed_count: int = 0
    total_jds: int = 0
    has_data: bool = False
    low_confidence: bool = False
    avg_min: float | None = None
    avg_max: float | None = None
    avg_mid: float | None = None
    p10: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    p90: float | None = None
    distribution: dict[str, int] = field(default_factory=dict)
    sample_jd_ids: list[int] = field(default_factory=list)
    truncated_ids: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_data": self.has_data,
            "total_jds": self.total_jds,
            "parsed_count": self.parsed_count,
            "unparsed_count": max(self.total_jds - self.parsed_count, 0),
            "sample_size": self.sample_size,
            "low_confidence": self.low_confidence,
            "statistics": {
                "avg_min": self.avg_min,
                "avg_max": self.avg_max,
                "avg_mid": self.avg_mid,
                "p10": self.p10,
                "p25": self.p25,
                "p50": self.p50,
                "p75": self.p75,
                "p90": self.p90,
            },
            "distribution": dict(self.distribution),
            "sample_jd_ids": list(self.sample_jd_ids),
            "truncated_ids": self.truncated_ids,
            "message": self.message,
        }


def parse_salary_range(text: Any) -> tuple[float, float] | None:
    """Salary text -> (min_k, max_k) in 千/月, or None when it cannot be read.

    Units are inferred from the string, not from data: "万"/"w" is treated as an
    annual package and converted, bare numbers >= 1000 as 元/月. Ambiguous input
    returns None rather than a guess — a wrong salary is worse than none.
    """
    if not text:
        return None
    raw = str(text)
    match = _NUMBER_PAIR.search(raw)
    if not match:
        return None
    try:
        low, high = float(match.group(1)), float(match.group(2))
    except ValueError:
        return None
    if low <= 0 or high <= 0 or high < low:
        return None

    lowered = raw.lower()
    if "w" in lowered or "万" in raw:
        return (round(low * 10 / 12, 1), round(high * 10 / 12, 1))
    if "k" in lowered:
        return (low, high)
    if low >= 1000:
        return (round(low / 1000, 1), round(high / 1000, 1))
    return (low, high)


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile on an unsorted input.

    Single implementation on purpose: nearest-rank (index `ceil(p*n)-1`) is what
    "the value at or below p% of the sample" means, and it returns an actual
    observed number instead of interpolating a salary nobody posted.
    """
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    index = max(0, min(n - 1, math.ceil((p / 100.0) * n) - 1))
    return ordered[index]


def percentile_rank(values: list[float], x: float) -> float | None:
    """Share of the sample at or below x. None when there is nothing to rank."""
    if not values:
        return None
    return round(sum(1 for value in values if value <= x) / len(values) * 100, 1)


def collect_samples(
    db: Session,
    *,
    position: str = "",
    city: str = "",
    cities: list[str] | None = None,
    industry: str = "",
) -> tuple[list[SalarySample], int]:
    """Parse the postings matching the filters. Returns (samples, matched_jd_count)."""
    query = db.query(JobDescription).filter(
        JobDescription.salary_range.isnot(None),
        JobDescription.salary_range != "",
    )
    if position:
        query = query.filter(JobDescription.title.contains(position))
    if city:
        query = query.filter(JobDescription.location.contains(city))
    if industry:
        query = query.filter(JobDescription.industry.contains(industry))

    wanted = [c.strip() for c in (cities or []) if c.strip()]
    rows = query.all()
    samples: list[SalarySample] = []
    for jd in rows:
        if wanted and not any(token in (jd.location or "") for token in wanted):
            continue
        parsed = parse_salary_range(jd.salary_range)
        if not parsed:
            continue
        low, high = parsed
        samples.append(
            SalarySample(
                jd_id=jd.id,
                title=jd.title or "",
                company=jd.company or "",
                location=jd.location or "",
                raw=str(jd.salary_range),
                min_k=low,
                max_k=high,
                mid_k=round((low + high) / 2, 1),
            )
        )
    return samples, len(rows)


def summarize(samples: list[SalarySample], total_jds: int | None = None) -> SalaryEvidence:
    """Quantiles + traceable sample, or an explicit no-data result."""
    matched = len(samples) if total_jds is None else total_jds
    if not samples:
        return SalaryEvidence(
            has_data=False,
            total_jds=matched,
            parsed_count=0,
            message="未找到可解析的薪资数据，请先导入更多包含薪资信息的JD",
        )

    mids = [sample.mid_k for sample in samples]
    ids = sorted({sample.jd_id for sample in samples if sample.jd_id is not None})
    distribution: dict[str, int] = {}
    for mid in mids:
        bucket = int(mid // 5) * 5
        distribution[f"{bucket}-{bucket + 5}K"] = distribution.get(f"{bucket}-{bucket + 5}K", 0) + 1

    evidence = SalaryEvidence(
        sample_size=len(samples),
        parsed_count=len(samples),
        total_jds=matched,
        has_data=True,
        low_confidence=len(samples) < MIN_RELIABLE_SAMPLE,
        avg_min=round(sum(s.min_k for s in samples) / len(samples), 1),
        avg_max=round(sum(s.max_k for s in samples) / len(samples), 1),
        avg_mid=round(sum(mids) / len(mids), 1),
        p10=percentile(mids, 10),
        p25=percentile(mids, 25),
        p50=percentile(mids, 50),
        p75=percentile(mids, 75),
        p90=percentile(mids, 90),
        distribution={label: distribution[label] for label in sorted(distribution, key=lambda k: int(k.split("-")[0]))},
        sample_jd_ids=ids[:MAX_TRACED_JD_IDS],
        truncated_ids=max(len(ids) - MAX_TRACED_JD_IDS, 0),
    )
    if evidence.low_confidence:
        evidence.message = f"仅 {len(samples)} 条可解析样本，分位数不足以支撑精确结论"
    return evidence


def group_by_city(samples: list[SalarySample]) -> list[dict[str, Any]]:
    """Per-city summary, largest sample first, same percentile function throughout."""
    buckets: dict[str, list[SalarySample]] = {}
    for sample in samples:
        buckets.setdefault(sample.location or "未知", []).append(sample)

    out = []
    for city, items in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        mids = [item.mid_k for item in items]
        out.append(
            {
                "city": city,
                "count": len(items),
                "avg_min": round(sum(item.min_k for item in items) / len(items), 1),
                "avg_max": round(sum(item.max_k for item in items) / len(items), 1),
                "avg_mid": round(sum(mids) / len(mids), 1),
                "p25": percentile(mids, 25),
                "p50": percentile(mids, 50),
                "p75": percentile(mids, 75),
                "low_confidence": len(items) < MIN_RELIABLE_SAMPLE,
                "sample_jd_ids": sorted({i.jd_id for i in items if i.jd_id is not None})[:MAX_TRACED_JD_IDS],
            }
        )
    return out
