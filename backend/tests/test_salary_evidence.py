"""B2.2: every salary number names the postings it came from.

The three salary endpoints each computed quantiles their own way
(`int(n*p/100)`, `n//4`, `3*n//4`), so "p25" was a different number per page, and
none of them returned the sample — a candidate could not tell whether 中位数 25K
rested on two postings or two hundred.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.salary_insight import router as salary_router
from app.core.database import get_db
from app.core.security import hash_password
from app.models.history import JobDescription
from app.models.user import User
from app.services.salary_evidence import (
    MIN_RELIABLE_SAMPLE,
    SalarySample,
    collect_samples,
    group_by_city,
    parse_salary_range,
    percentile,
    percentile_rank,
    summarize,
)


def _sample(jd_id, mid, location="上海"):
    return SalarySample(
        jd_id=jd_id,
        title="后端工程师",
        company="示例公司",
        location=location,
        raw=f"{mid}-{mid}K",
        min_k=mid,
        max_k=mid,
        mid_k=mid,
    )


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    "text,expected",
    [
        ("15-25K", (15.0, 25.0)),
        ("15k-25k", (15.0, 25.0)),
        ("15000-25000", (15.0, 25.0)),
        ("15~25K", (15.0, 25.0)),
        ("12薪 15-25K", (15.0, 25.0)),
        ("24-36万", (20.0, 30.0)),
    ],
)
def test_salary_strings_parse_to_k_per_month(text, expected):
    assert parse_salary_range(text) == expected


@pytest.mark.parametrize("text", ["", None, "面议", "年薪30万", "25-15K", "0-5K"])
def test_ambiguous_or_reversed_salaries_are_refused_not_guessed(text):
    """`findall(r"[\\d.]+")` used to take the first two numbers it saw, so
    "12薪 15-25K" parsed as 12-15K."""
    assert parse_salary_range(text) is None


# ---------------------------------------------------------------- quantiles


def test_percentile_is_nearest_rank_on_one_implementation():
    values = [10, 20, 30, 40]

    assert percentile(values, 25) == 10
    assert percentile(values, 50) == 20
    assert percentile(values, 75) == 30
    assert percentile(values, 100) == 40
    assert percentile([], 50) is None
    assert percentile([33], 5) == 33


def test_percentile_does_not_invent_an_unposted_salary():
    """Interpolating between 20K and 30K would report 25K, a number no posting
    ever offered."""
    assert percentile([20, 30], 60) in (20, 30)


def test_percentile_rank_reports_position_in_the_sample():
    assert percentile_rank([10, 20, 30, 40], 25) == 50.0
    assert percentile_rank([], 10) is None


# ---------------------------------------------------------------- evidence


def test_no_samples_is_explicitly_no_data():
    evidence = summarize([])

    assert evidence.has_data is False
    assert evidence.p50 is None
    assert "未找到" in evidence.message
    assert evidence.to_dict()["statistics"]["avg_mid"] is None


def test_a_small_sample_is_flagged_instead_of_looking_precise():
    evidence = summarize([_sample(i, mid) for i, mid in enumerate([15, 20, 25], start=1)])

    assert evidence.has_data is True
    assert evidence.low_confidence is True
    assert "不足以支撑" in evidence.message


def test_a_reliable_sample_carries_no_warning_and_traces_its_postings():
    samples = [_sample(i, 10 + i) for i in range(1, MIN_RELIABLE_SAMPLE + 3)]

    evidence = summarize(samples)

    assert evidence.low_confidence is False
    assert evidence.message == ""
    assert evidence.sample_jd_ids == sorted(s.jd_id for s in samples)
    assert evidence.truncated_ids == 0


def test_more_than_the_trace_cap_still_reports_the_full_count():
    evidence = summarize([_sample(i, 10 + i) for i in range(1, 61)])

    assert evidence.sample_size == 60
    assert len(evidence.sample_jd_ids) == 50
    assert evidence.truncated_ids == 10


def test_city_groups_use_the_same_percentile_as_the_overview():
    samples = [
        _sample(1, 10, "上海"),
        _sample(2, 20, "上海"),
        _sample(3, 30, "上海"),
        _sample(4, 40, "上海"),
        _sample(5, 50, "北京"),
    ]

    rows = {row["city"]: row for row in group_by_city(samples)}

    assert rows["上海"]["p25"] == percentile([10, 20, 30, 40], 25)
    assert rows["上海"]["count"] == 4
    assert rows["上海"]["low_confidence"] is True
    assert rows["北京"]["sample_jd_ids"] == [5]


# ---------------------------------------------------------------- endpoints


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(salary_router, prefix="/salary")
    app.dependency_overrides[get_db] = lambda: db_session

    user = User(username="sal_user", email="sal_user@example.com", password=hash_password("StrongP@ssw0rd"))
    db_session.add(user)
    db_session.commit()
    from app.api.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as test_client:
        yield test_client


def _seed_jobs(db_session, user, rows):
    for index, (title, location, salary) in enumerate(rows, start=1):
        db_session.add(
            JobDescription(
                user_id=user.id,
                title=title,
                company=f"公司{index}",
                location=location,
                salary_range=salary,
                raw_text=title,
                is_active=1,
                parsed_json={"title": title, "required_skills": ["Python"]},
            )
        )
    db_session.commit()


def test_overview_returns_statistics_and_the_sample_behind_them(client, db_session):
    user = db_session.query(User).filter(User.username == "sal_user").one()
    _seed_jobs(
        db_session,
        user,
        [(f"后端工程师{i}", "上海", f"{15 + i}-{25 + i}K") for i in range(1, 7)],
    )

    data = client.get("/salary/overview", params={"position": "后端"}).json()["data"]

    assert data["has_data"] is True
    assert data["sample_size"] == 6
    assert data["low_confidence"] is False
    # Seeded midpoints are 21..26K; nearest-rank p50 of six values is the third.
    assert data["statistics"]["p50"] == 23.0
    assert len(data["sample_jd_ids"]) == 6
    assert data["unparsed_count"] == 0


def test_unparseable_postings_are_counted_not_silently_dropped(client, db_session):
    user = db_session.query(User).filter(User.username == "sal_user").one()
    _seed_jobs(
        db_session,
        user,
        [("后端工程师1", "上海", "15-25K"), ("后端工程师2", "上海", "面议"), ("后端工程师3", "上海", "")],
    )

    data = client.get("/salary/overview", params={"position": "后端"}).json()["data"]

    assert data["total_jds"] == 2  # the empty one never enters the query
    assert data["parsed_count"] == 1
    assert data["unparsed_count"] == 1
    assert data["low_confidence"] is True


def test_a_single_source_makes_the_two_pages_agree(client, db_session):
    user = db_session.query(User).filter(User.username == "sal_user").one()
    _seed_jobs(
        db_session,
        user,
        [(f"算法工程师{i}", "北京", f"{20 + i}-{30 + i}K") for i in range(1, 9)],
    )

    overview = client.get("/salary/overview", params={"position": "算法"}).json()["data"]
    check = client.get(
        "/salary/expectation-check",
        params={"position": "算法", "expected_min": 25, "expected_max": 28},
    ).json()["data"]

    assert check["market_stats"]["p25"] == overview["statistics"]["p25"]
    assert check["market_stats"]["p50"] == overview["statistics"]["p50"]
    assert check["sample_jd_ids"] == overview["sample_jd_ids"]


def test_expectation_check_without_market_data_says_so(client, db_session):
    data = client.get(
        "/salary/expectation-check",
        params={"position": "不存在的岗位", "expected_min": 30, "expected_max": 40},
    ).json()["data"]

    assert data["has_data"] is False
    assert data["sample_size"] == 0
    assert "市场数据不足" in data["message"]


def test_compare_filters_cities_with_the_shared_collector(client, db_session):
    user = db_session.query(User).filter(User.username == "sal_user").one()
    _seed_jobs(
        db_session,
        user,
        [("后端1", "上海", "20-30K"), ("后端2", "北京", "25-35K"), ("后端3", "深圳", "18-28K")],
    )

    data = client.get("/salary/compare", params={"cities": "上海,北京"}).json()["data"]

    assert {row["city"] for row in data["comparison"]} == {"上海", "北京"}
    assert data["sample_size"] == 2


def test_collect_samples_returns_the_matched_row_count(client, db_session):
    user = db_session.query(User).filter(User.username == "sal_user").one()
    _seed_jobs(db_session, user, [("测试岗1", "上海", "10-20K"), ("测试岗2", "上海", "面议")])

    samples, total = collect_samples(db_session, position="测试岗")

    assert total == 2
    assert len(samples) == 1
