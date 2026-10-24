import json
from pathlib import Path

GOLD = Path(__file__).parent / "eval" / "human_gold_TO_FILL.json"


def _rows():
    data = json.loads(GOLD.read_text(encoding="utf-8"))
    return {row["id"]: row for row in data["rows"]}


def test_project_names_take_the_title_body_not_the_parenthetical():
    rows = _rows()
    assert [p["name"] for p in rows["real02"]["project_experience"]] == [
        "智能招聘与职业规划平台",
        "DeepSearch 对话式多智能体研究系统",
        "基于 Qt 的即时通讯系统",
    ]
    assert all("（" not in p["name"] for row in rows.values() for p in row["project_experience"])


def test_project_stack_technologies_count_as_skills():
    assert {"BGE", "CrossEncoder", "JWT"} <= set(_rows()["real01"]["skills"])


def test_c_cpp_is_split_everywhere():
    rows = _rows()
    for rid, row in rows.items():
        assert "C/C++" not in row["skills"], rid
    for rid in ("real01", "real02", "real04"):
        assert {"C", "C++"} <= set(rows[rid]["skills"]), rid


def test_real04_uses_atomic_enumeration_not_umbrella_terms():
    skills = set(_rows()["real04"]["skills"])
    assert {"链表", "队列", "栈", "二叉树", "查找算法", "排序算法"} <= skills
    assert {"文件I/O", "信号", "多进程", "Qt网络编程", "管道"} <= skills
    assert "数据结构" not in skills
    assert "算法" not in skills
