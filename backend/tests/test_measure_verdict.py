"""`measure_verdict` 的判据自己的测试。

要钉住的是**"看起来像模像样、其实不能用"的那一次**：2026-11-14 实测里推荐分数是 57/40/33，
排序也对，但 `vector_score` 全空——分数只来自规则臂。当时没有任何东西会红，所以这次补一个。
"""

from __future__ import annotations

from scripts.measure_verdict import classify_run, format_verdict


def _report(**overrides) -> dict:
    """一份"理想读数"：跑通了、记录落了库、分数带向量分、trace 全成功。"""
    base = {
        "steps": [
            {
                "step": "analysis/full",
                "timeline": [
                    {"status": "completed", "total_steps": 7},
                ],
            },
            {
                "step": "jobs/recommend",
                "recommendations": [
                    {"match_score": 72, "vector_score": 0.83, "match_score_method": "hybrid"},
                    {"match_score": 61, "vector_score": 0.71, "match_score_method": "hybrid"},
                ],
            },
        ],
        "step_counts": {"total": 7, "completed": 7, "failed": 0},
        "analysis_record_id": 85,
        "traces": [
            {"status": "success", "response_source": "real", "error_message": ""},
            {"status": "success", "response_source": "real", "error_message": ""},
        ],
    }
    base.update(overrides)
    return base


def test_clean_run_is_usable():
    result = classify_run(_report())
    assert result["blockers"] == []
    assert result["record_landed"] is True
    assert "链路跑通" in result["verdict"]
    assert "可用于模型质量结论" in result["verdict"]


def test_rule_only_scores_are_a_blocker_even_though_they_look_fine():
    """反证的核心：分数非空、排序正常，但一条向量分都没有。"""
    result = classify_run(
        _report(
            steps=[
                {"step": "analysis/full", "timeline": [{"status": "partial", "total_steps": 7}]},
                {
                    "step": "jobs/recommend",
                    "recommendations": [
                        {"match_score": 57, "vector_score": None, "match_score_method": "rubric_6dim_v2"},
                        {"match_score": 40, "vector_score": None, "match_score_method": "rubric_6dim_v2"},
                        {"match_score": 33, "vector_score": None, "match_score_method": "rubric_6dim_v2"},
                    ],
                },
            ],
            step_counts={"total": 7, "completed": 6, "failed": 1},
            traces=[
                {
                    "status": "failed",
                    "response_source": "fallback_model",
                    "error_message": "Arrearage: embedding quota",
                },
                {"status": "success", "response_source": "real", "error_message": ""},
            ],
        )
    )
    assert any("规则臂" in blocker for blocker in result["blockers"])
    assert any("欠费" in blocker for blocker in result["blockers"])
    assert "不能用于模型质量结论" in result["verdict"]
    assert result["trace_mix"]["failed"] == 1
    assert result["steps_done"] == 6 and result["steps_failed"] == 1


def test_missing_record_is_called_out():
    result = classify_run(_report(analysis_record_id=None))
    assert result["record_landed"] is False
    assert "没落库" in format_verdict(result)


def test_failed_task_without_record_says_so():
    result = classify_run(
        _report(
            steps=[{"step": "analysis/full", "timeline": [{"status": "failed", "total_steps": 7}]}],
            analysis_record_id=None,
        )
    )
    assert "没跑完" in result["verdict"]


def test_verdict_reads_the_data_not_a_constant():
    """反空转：同一份输入只改"有没有向量分"，结论必须跟着翻面。"""
    with_vector = classify_run(_report())
    without = classify_run(
        _report(
            steps=[
                {"step": "analysis/full", "timeline": [{"status": "completed", "total_steps": 7}]},
                {
                    "step": "jobs/recommend",
                    "recommendations": [
                        {"match_score": 57, "vector_score": None, "match_score_method": "rubric_6dim_v2"},
                    ],
                },
            ]
        )
    )
    assert with_vector["verdict"] != without["verdict"]
    assert "可用于" in with_vector["verdict"] and "不能用于" in without["verdict"]


def test_empty_report_does_not_crash():
    result = classify_run({})
    assert result["blockers"] == []
    assert "0/0" in format_verdict(result)


def test_poll_window_that_ends_early_is_not_a_final_reading():
    """彩排里真撞到的：链要跑 4 分 37 秒，而当时的轮询窗口是 180 秒。

    那一版会把 `running` 当成终态写进结论，读者看到的是一个"已跑完"的假读数。
    """
    result = classify_run(
        _report(
            steps=[{"step": "analysis/full", "timeline": [{"status": "running", "total_steps": 7}]}],
            polled_to_terminal=False,
        )
    )
    assert result["incomplete"] is True
    assert any("没跟到终态" in blocker for blocker in result["blockers"])
    assert "不完整" in result["verdict"]
