"""回流③的开场倾斜：只重排提到本场必考弱项的题，没命中就原序。"""

from __future__ import annotations

from app.services.interview_profile_service import tilt_questions_by_profile


def _q(text: str, index: int = 0) -> dict:
    return {"id": index, "question": text, "category": "tech"}


def _profile(skill: str, canonical: str | None = None) -> dict:
    row = {"skill": skill, "avg_score": 55}
    if canonical is not None:
        row["canonical"] = canonical
    return {"skill_weaknesses": [row]}


def test_weak_skill_questions_lead_and_the_rest_keep_their_order():
    questions = [
        _q("请介绍一下你最有成就感的项目", 0),
        _q("围绕 Kafka 和 Redis，你遇到过什么技术难点？", 1),
        _q("容量规划你会怎么做？", 2),
    ]

    ordered = tilt_questions_by_profile(questions, ["Kafka", "Redis", "容量规划"], _profile("Kafka", "kafka"))

    assert [row["question"] for row in ordered] == [
        questions[1]["question"],
        questions[0]["question"],
        questions[2]["question"],
    ]


def test_no_profile_no_overlap_or_no_questions_keeps_the_original_order():
    questions = [_q("介绍项目", 0), _q("Kafka 怎么用", 1)]

    assert tilt_questions_by_profile(questions, ["Kafka"], None) == questions
    assert tilt_questions_by_profile(questions, ["Redis"], _profile("Kafka")) == questions
    assert tilt_questions_by_profile([], ["Kafka"], _profile("Kafka")) == []


def test_aliases_match_but_short_ascii_names_respect_word_boundaries():
    questions = [_q("介绍一下项目", 0), _q("Kubernetes 的调度器怎么工作？", 1), _q("Google 的检索链路", 2)]

    kubernetes = tilt_questions_by_profile(questions, ["K8s"], _profile("Kubernetes"))
    go = tilt_questions_by_profile(questions, ["Go"], _profile("Go"))

    assert kubernetes[0]["question"] == questions[1]["question"]
    assert go == questions, "Go 不许在 Google 里命中"


def test_a_weakness_outside_the_jd_does_not_tilt():
    questions = [_q("介绍项目", 0), _q("Kubernetes 的调度器怎么工作？", 1)]

    ordered = tilt_questions_by_profile(questions, ["Kafka"], _profile("Kubernetes"))

    assert ordered == questions
