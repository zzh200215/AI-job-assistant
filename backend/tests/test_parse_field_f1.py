import json

from scripts.eval_parse import (
    check_thresholds,
    load_human_gold,
    merge_human_gold,
    score_entities,
    score_list,
    semantic_arm,
)


def _payload(**overrides):
    data = {
        "name": "周思远",
        "phone": "13800138001",
        "email": "resume01@example.com",
        "years_exp": 1,
        "education": "本科",
        "major": "计算机科学与技术",
        "current_company": "Acme",
        "current_title": "后端工程师",
        "skills": ["Python", "FastAPI"],
        "work_experience": [{"company": "Acme", "title": "Backend", "start": None, "end": None, "desc": "负责接口"}],
        "project_experience": [
            {"name": "项目A", "role": None, "start": None, "end": None, "desc": None, "tech": ["Python"]}
        ],
        "self_evaluation": "有责任心",
    }
    data.update(overrides)
    return data


def _real_row():
    return {
        "kind": "real",
        "id": "real01",
        "source_file": "real_5843c1de.txt",
        "raw_text": "周思远 13800138001 resume01@example.com",
        "gold": {"name": "周思远", "phone": "13800138001", "email": "resume01@example.com"},
    }


def test_entity_keys_match_by_company_title_and_project_name():
    work_got = [
        {"company": "Acme", "title": "Backend"},
        {"company": "Other", "title": "Ops"},
    ]
    work_want = [{"title": "Backend", "company": "Acme"}]
    assert score_entities("work_experience", work_got, work_want) == (1, 2, 1)

    project_got = [{"name": "项目A"}]
    project_want = [{"name": "项目A"}, {"name": "项目B"}]
    assert score_entities("project_experience", project_got, project_want) == (1, 1, 2)


def test_human_gold_only_merges_done_rows(tmp_path):
    path = tmp_path / "human_gold.json"
    path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "id": "real01",
                        "_状态": "done",
                        "skills": ["Python"],
                        "work_experience": [{"company": "Acme", "title": "Backend"}],
                        "project_experience": [],
                    },
                    {"id": "real02", "_状态": "todo", "skills": ["不该并入"]},
                    {"id": "real03", "_状态": "done", "skills": [], "work_experience": [], "project_experience": []},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    human = load_human_gold(path)
    assert human["total"] == 3
    assert human["done"] == 1
    assert set(human["rows"]) == {"real01"}

    rows = [_real_row(), {**_real_row(), "id": "real02"}]
    assert merge_human_gold(rows, human) == 1
    assert rows[0]["gold"]["skills"] == ["Python"]
    assert "skills" not in rows[1]["gold"]


def test_semantic_arm_scores_human_gold_lists():
    row = _real_row()
    human = {
        "rows": {
            "real01": {
                "skills": ["Python", "FastAPI"],
                "work_experience": [{"company": "Acme", "title": "Backend"}],
                "project_experience": [{"name": "项目A"}],
            }
        }
    }
    merge_human_gold([row], human)

    sem = semantic_arm([row], lambda prompt: _payload())

    assert sem["llm_calls"] == 1
    assert sem["lists"]["skills"]["f1"] == 1.0
    assert sem["lists"]["work_experience"]["f1"] == 1.0
    assert sem["lists"]["project_experience"]["f1"] == 1.0


def test_min_field_f1_applies_to_list_f1():
    det = {"errors": [], "tail_keep_rate": None}
    sem = {
        "errors": [],
        "first_pass_rate": 1.0,
        "scalar": {},
        "lists": {"work_experience": {"f1": 0.5, "want": 2}},
    }

    bad = check_thresholds(
        det,
        sem,
        mock=False,
        max_errors=0,
        min_tail_keep=None,
        min_structure_rate=None,
        min_field_f1=0.8,
    )

    assert any("列表字段 work_experience" in item for item in bad)


def test_skill_set_ignores_internal_whitespace_but_not_punctuation():
    """`Agent 编排` 与 `Agent编排` 是同一项；`C/C++` 与 `C++` 不是。

    真臂复核对出来的：gold 照原文写 `Agent 编排`，模型写 `Agent编排`，旧打分器
    只 strip/lower，内部空格把同一项判成两个，系统性压低 F1。
    """
    assert score_list("skills", ["Agent编排", "PromptEngineering"], ["Agent 编排", "Prompt Engineering"]) == (
        2,
        2,
        2,
    )
    assert score_list("skills", ["C++"], ["C/C++"]) == (0, 1, 1)


def test_min_field_f1_does_not_gate_scalars_against_the_regex_baseline():
    """标量不进这道门：正则直取在 name/phone/email 上就是 1.0，LLM 再准也只能打平。

    2026-10-23 他拍的口径：`--min-field-f1` 只门列表 F1。此前实现把“与基线打平”算红，
    结果是任何门槛值都必然红三条，门根本不可用。
    """
    det = {"errors": [], "tail_keep_rate": None}
    sem = {
        "errors": [],
        "first_pass_rate": 1.0,
        "scalar": {
            "name": {"want": 4, "hit": 4, "recall": 1.0, "regex_baseline_recall": 1.0},
            "phone": {"want": 4, "hit": 4, "recall": 1.0, "regex_baseline_recall": 1.0},
            "email": {"want": 4, "hit": 4, "recall": 1.0, "regex_baseline_recall": 1.0},
        },
        "lists": {"skills": {"f1": 0.9, "want": 10}},
    }

    bad = check_thresholds(
        det,
        sem,
        mock=False,
        max_errors=0,
        min_tail_keep=None,
        min_structure_rate=None,
        min_field_f1=0.75,
    )

    assert bad == []
