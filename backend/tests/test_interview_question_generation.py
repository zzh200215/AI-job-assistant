"""Regression coverage for the non-blocking interview question bootstrap."""

from app.api.interview_rest import _fallback_questions, _normalize_generated_questions


def test_fallback_question_set_is_ready_to_start():
    questions = _fallback_questions("后端工程师", ["Python", "FastAPI", "MySQL"], "tech")

    assert len(questions) == 10
    assert [item["id"] for item in questions] == list(range(1, 11))
    assert all(item["question"] for item in questions)
    assert all(item["source"] == "starter" for item in questions)


def test_partial_model_result_keeps_a_complete_question_set():
    fallback = _fallback_questions("后端工程师", ["Python"], "tech")
    result = _normalize_generated_questions(
        {
            "tech": [
                {
                    "q": "请解释 FastAPI 中依赖注入的生命周期。",
                    "intent": "框架理解",
                    "ref_answer": "说明 Depends、作用域与资源释放。",
                }
            ]
        },
        fallback,
    )

    assert len(result) == 10
    assert result[0]["source"] == "personalized"
    assert result[0]["question"] == "请解释 FastAPI 中依赖注入的生命周期。"
    assert result[-1]["source"] == "starter"
