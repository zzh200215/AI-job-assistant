"""后端这一侧的腿：前端那张 422 映射表比对的夹具**不能过期**（§10.29 / D116）。

`frontend/tests/fixtures/validationShapes.json` 是从真路由的请求体模型导出的。
前端守卫（`frontend/tests/validationCopy.test.mjs`）钉的是"表与夹具双向相等"，
所以夹具一漂，红会发生在前端——而制造漂移的人改的是后端，他的门里不该只有"测试没跑"这一句。
这条就是让**后端**在有人新增一个带 `max_length` 的字段、或 Pydantic 升级换出一种新 type 时，
直接在自己家门口点名。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.collect_validation_shapes import collect

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "validationShapes.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_covers_every_type_the_backend_can_emit() -> None:
    live = collect()
    stored = _fixture()

    live_types = {s["type"] for s in live["shapes"]}
    stored_types = {s["type"] for s in stored["shapes"]}
    assert live_types == stored_types, (
        f"422 的 type 集合变了：新增 {sorted(live_types - stored_types)}，"
        f"消失 {sorted(stored_types - live_types)}；重跑 scripts/collect_validation_shapes.py 再补前端映射"
    )

    live_ctx = {s["type"]: set(s["ctx_keys"]) for s in live["shapes"]}
    stored_ctx = {s["type"]: set(s["ctx_keys"]) for s in stored["shapes"]}
    assert live_ctx == stored_ctx, "ctx 键漂了：插值用的数字来源变了"


def test_fixture_lists_every_english_template_still_reachable() -> None:
    live = collect()
    stored = _fixture()
    assert set(live["english_msgs"]) == set(stored["english_msgs"]), (
        "后端能发出的英文模板集合变了——这些串就是候选人今天在屏幕上看到的，" "少一条或多一条都意味着前端映射表要跟着动"
    )


def test_the_probe_reaches_the_models_that_can_actually_422() -> None:
    """防空转：夹具里点名 24 个请求体模型，且必须包含注册/登录那两条候选人天天走的路。"""
    stored = _fixture()
    assert stored["model_total"] >= 20
    tails = set(stored["loc_tails"])
    assert {"password", "email", "account", "username"} <= tails
    # 反向证据：如果探测器其实什么都没探到，上面几条会全部相等地通过——所以这里钉住数量本身
    assert len(stored["shapes"]) >= 10, "type 集合小得不像话，多半是探测挂了"
