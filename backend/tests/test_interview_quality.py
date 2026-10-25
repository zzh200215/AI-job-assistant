from scripts.interview_quality import extract_followups


def test_extract_followups_groups_by_tier_and_round_and_joins_duplicates():
    report = {
        "runs": {
            "mid": {
                "dynamic": {
                    "transcript": [
                        {"round": 1, "is_follow_up": True, "content": "追问A"},
                        {"round": 1, "is_follow_up": True, "content": "追问B"},
                        {"round": 2, "is_follow_up": False, "content": "不是追问"},
                        {"round": 2, "is_follow_up": True, "content": "追问C"},
                    ]
                }
            }
        }
    }

    assert extract_followups(report) == {("mid", 1): "追问A / 追问B", ("mid", 2): "追问C"}


def test_extract_followups_skips_blank_and_missing_round():
    report = {
        "runs": {
            "good": {
                "dynamic": {
                    "transcript": [
                        {"round": 0, "is_follow_up": True, "content": "没有题号"},
                        {"round": 1, "is_follow_up": True, "content": "  "},
                    ]
                }
            }
        }
    }

    assert extract_followups(report) == {}


def test_extract_followups_can_mark_who_composed_each_followup():
    report = {
        "runs": {
            "mid": {
                "dynamic": {
                    "transcript": [
                        {
                            "round": 1,
                            "is_follow_up": True,
                            "content": "追问A",
                            "decision": {"source": "llm", "degraded": False},
                        },
                        {
                            "round": 1,
                            "is_follow_up": True,
                            "content": "追问B",
                            "decision": {"source": "heuristic", "degraded": True},
                        },
                    ]
                }
            }
        }
    }

    assert extract_followups(report) == {("mid", 1): "追问A / 追问B"}
    assert extract_followups(report, with_source=True) == {("mid", 1): "追问A（LLM） / 追问B（模板/降级）"}
