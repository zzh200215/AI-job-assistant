"""报告形状必须扛得住"模型自己决定怎么填"。

`/resume/{id}/diagnose` 这一段历史上翻过三次车：把整个维度 dict 当分数交给前端（五条维度条
显示成 JSON 文本 + 0 宽进度条）、`improvement_roadmap` 是 dict 时被 `isinstance(list)` 判断丢弃、
模型放在 `keyword_density` 里的 `missing_keywords` 从未被读取（缺 5 个关键词的简历被告知"覆盖良好"）。
见 `dfee148`。

这一族打的是**模型返回层**（`chat_json`），所以下面每一条都走完整的服务与路由，
不是只在纯函数里自证。七维口径本身由 `test_resume_report_rubric.py` 钉，
自报总分不上屏由 `test_resume_report_overview.py` 钉。
"""

from __future__ import annotations

import pytest

from app.api import resume as resume_api
from app.core.security import hash_password
from app.models.user import User
from app.services import resume_analysis_service as service

SEVEN = {
    "metric_ownership": {"score": 12, "note": "指标只有绝对值"},
    "interview_hooks": {"score": 5, "note": "只有数字型钩子"},
    "role_fit": {"score": 16, "note": "方向标签要读完整份才判得出", "missing_keywords": ["RAG", "LangGraph"]},
    "transferability": {"score": 10, "note": "选型依据没写"},
    "project_depth": {"score": 13, "note": "约束与代价一处都没有"},
    "expression_structure": {"score": 6, "note": "全篇职责句没有结果句"},
    "advantage_section": {"score": 3, "note": "没有方法论标签"},
}
SEVEN_SUM = sum(row["score"] for row in SEVEN.values())


def _user(db, tag: str):
    user = User(
        username=f"shape_{tag}",
        email=f"shape_{tag}@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _diagnose(db, model_payload, monkeypatch, tag="owner"):
    user = _user(db, tag)
    rid = _make_resume(db, user)
    monkeypatch.setattr(service, "chat_json", lambda prompt, **kw: model_payload)
    body = resume_api.diagnose_resume(rid, {"target_position": ""}, db=db, current_user=user)
    assert body["code"] == 0, body
    return user, body["data"]


def _make_resume(db, user) -> int:
    from app.models.history import Resume

    obj = Resume(
        name="测试用户",
        file_name="resume.pdf",
        file_path="uploads/resume.pdf",
        file_type="pdf",
        file_size=1024,
        user_id=user.id,
        parsed_json={"name": "测试用户", "self_evaluation": "3 年后端", "work_experience": [{"t": "x"}]},
    )
    db.add(obj)
    db.commit()
    return obj.id


def test_a_schema_conforming_response_yields_seven_rows_and_a_sum(db_session, monkeypatch):
    payload = {"overall_score": 72, "dimensions": SEVEN, "verdict": {"direction": "RAG 应用"}, "competition": {}}

    _user_row, data = _diagnose(db_session, payload, monkeypatch, "sum")

    assert [row["key"] for row in data["dimensions"]] == list(SEVEN)
    assert [row["score"] for row in data["dimensions"]] == [12, 5, 16, 10, 13, 6, 3]
    assert [row["full"] for row in data["dimensions"]] == [20, 10, 20, 15, 20, 10, 5]
    assert data["total_score"] == SEVEN_SUM
    assert data["grade"] == "C"
    assert "D 0–64" in data["grade_scale"]
    # 姓名由服务端从 `tb_resume.name` 注入，不是模型给的（报告标题与下载文件名都读这一位）。
    assert data["verdict"] == {"direction": "RAG 应用", "candidate_name": "测试用户"}
    # 待优化点是模型写给这份简历的那句话，服务端不掺任何通用建议。
    assert data["dimensions"][0]["note"] == "指标只有绝对值"


def test_a_bare_number_per_dimension_still_reads(db_session, monkeypatch):
    """早期模型直接给分数而不是对象；两种形状都得读，这条与 `dfee148` 同源。"""
    flat = {key: row["score"] for key, row in SEVEN.items()}

    _user_row, data = _diagnose(db_session, {"dimensions": flat}, monkeypatch, "flat")

    assert data["total_score"] == SEVEN_SUM
    assert all(row["note"] == "" for row in data["dimensions"])


def test_two_missing_dimensions_make_the_total_unknown_not_lower(db_session, monkeypatch):
    partial = dict(SEVEN)
    partial.pop("interview_hooks")
    partial.pop("advantage_section")

    _user_row, data = _diagnose(db_session, {"dimensions": partial}, monkeypatch, "partial")

    assert [row["score"] for row in data["dimensions"]] == [12, None, 16, 10, 13, 6, None]
    assert data["total_score"] is None, "少两维不是扣两维的分，是这份报告还不知道"
    assert data["grade"] is None


@pytest.mark.parametrize(
    "raw",
    [True, "12", 120, -3, None],
)
def test_a_number_that_cannot_be_a_score_is_left_unknown(db_session, monkeypatch, raw):
    payload = dict(SEVEN)
    payload["role_fit"] = {"score": raw, "note": "x"}

    _user_row, data = _diagnose(db_session, {"dimensions": payload}, monkeypatch, f"bad{raw}")

    assert data["dimensions"][2]["score"] is None
    assert data["total_score"] is None


def test_a_note_the_model_wrote_as_an_object_is_not_printed_as_python(db_session, monkeypatch):
    payload = dict(SEVEN)
    payload["project_depth"] = {"score": 13, "note": {"问题": "没写代价"}}

    _user_row, data = _diagnose(db_session, {"dimensions": payload}, monkeypatch, "dictnote")

    assert data["dimensions"][4]["note"] == ""
    assert "问题" not in str(data["dimensions"][4])


def test_keywords_the_model_split_across_dimensions_are_collected_once(db_session, monkeypatch):
    payload = {
        "dimensions": {
            **SEVEN,
            "role_fit": {"score": 16, "note": "n", "missing_keywords": ["RAG", "评测集", "RAG"]},
            "transferability": {"score": 10, "note": "n", "missing_keywords": ["评测集", "RRF"]},
        }
    }

    _user_row, data = _diagnose(db_session, payload, monkeypatch, "kw")

    assert data["missing_keywords"] == ["RAG", "评测集", "RRF"], "缺口分散在维度里就没汇总过一次的老账"


def test_competition_lists_survive_a_model_that_wrote_them_as_prose(db_session, monkeypatch):
    payload = {
        "dimensions": SEVEN,
        "to_next_grade": "补两处基线",
        "competition": {"cards": "就一张牌", "gaps": ["年限", 7, "  "], "positioning_badge": {"档": "B"}},
    }

    _user_row, data = _diagnose(db_session, payload, monkeypatch, "comp")

    assert data["to_next_grade"] == []
    assert data["competition"]["cards"] == []
    assert data["competition"]["gaps"] == ["年限", "7"]
    assert data["competition"]["positioning_badge"] == ""
