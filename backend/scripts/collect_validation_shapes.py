"""导出"422 能长成哪些形状"到前端守卫用的夹具：`frontend/tests/fixtures/validationShapes.json`。

为什么要有这个文件：前端的 `VALIDATION_COPY`（`src/utils/requestTracing.js`，§10.29/D116）是一张
**按 Pydantic `type` 组中文句子**的表。表少了会怎样？屏幕退成那句通用中文——不会崩，但没人会注意到
"新增了一个带 max_length 的字段之后，候选人看到的是一句没有主语的『请求参数有误』"。
所以这里把"后端实际能发出来的形状"导出成夹具，前端守卫逐条比对，backend 那边再有一条反向守卫盯着
夹具本身没有过期（同 D107 那份密码用例表的两条腿）。

跑法（在 `backend/` 下）：`./.venv/Scripts/python.exe scripts/collect_validation_shapes.py`
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError

from app.main import app as live_app

OUT = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "validationShapes.json"


def request_models(app: FastAPI) -> dict[str, type[BaseModel]]:
    """只收**真被路由当请求体用的**模型。

    第一版按"BaseModel 的子类"扫整包，把 `Settings` 与所有 `*Resp` 响应模型都算了进来，
    于是 type 分布读起来只有 6 种（响应模型永远不会产出 422，而超长/正则/区间那一族恰好全在请求体上）。
    """
    found: dict[str, type[BaseModel]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for param in inspect.signature(route.endpoint).parameters.values():
            ann = param.annotation
            if inspect.isclass(ann) and issubclass(ann, BaseModel) and ann is not BaseModel:
                found[ann.__name__] = ann
    return found


def probes(model: type[BaseModel]) -> list[dict]:
    """每格给几种**可达**的坏形状：缺失 / 类型不对 / 空串 / 超长 / 太短 / 越界 / 内容不合规。"""
    out: list[dict] = [{}, {"__junk__": 1}]
    for fname, finfo in model.model_fields.items():
        ann = str(finfo.annotation)
        lower = fname.lower()
        if "int" in ann:
            out += [{fname: "abc"}, {fname: 10**12}, {fname: -1}, {fname: 0}, {fname: 1}]
        elif "bool" in ann:
            out += [{fname: "not-a-bool"}]
        elif "list" in ann or "List" in ann or "[" in ann:
            out += [{fname: "not-a-list"}, {fname: []}]
        elif "dict" in ann or "Mapping" in ann:
            out += [{fname: "not-a-dict"}]
        elif "EmailStr" in ann:
            out += [{fname: "not-an-email"}, {fname: "a@b.co"}]
        else:
            out += [{fname: 123}, {fname: ""}, {fname: "x" * 400}, {fname: "中"}, {fname: "中文值"}]
        if "password" in lower:
            out += [{fname: "abcd1234"}, {fname: "P@ssW0rd"}]
        if lower in ("username", "account", "name", "title"):
            out += [{fname: "a"}, {fname: "占位"}]
    return out


def collect() -> dict:
    by_type: dict[str, dict] = {}
    tails: set[str] = set()
    english_msgs: set[str] = set()
    models = request_models(live_app)

    for name, model in sorted(models.items()):
        for payload in probes(model):
            try:
                model.model_validate(payload)
            except ValidationError as exc:
                for err in exc.errors(include_context=True):
                    msg = str(err.get("msg") or "")
                    key = str(err.get("type"))
                    tail = ".".join(str(p) for p in err.get("loc", ())).split(".")[-1]
                    tails.add(tail)
                    entry = by_type.setdefault(
                        key,
                        {"type": key, "ctx_keys": set(), "sample_msg": msg, "models": set()},
                    )
                    entry["ctx_keys"] |= set((err.get("ctx") or {}).keys())
                    entry["models"].add(name)
                    if not any("\u4e00" <= ch <= "\u9fff" for ch in msg):
                        english_msgs.add(msg)
            except Exception:
                pass

    shapes = []
    for key in sorted(by_type):
        entry = by_type[key]
        shapes.append(
            {
                "type": key,
                "ctx_keys": sorted(entry["ctx_keys"]),
                "sample_msg": entry["sample_msg"],
                "hit_count": len(entry["models"]),
            }
        )
    return {
        "_note": "由 backend/scripts/collect_validation_shapes.py 从真路由的请求体模型实测导出；不要手改。",
        "model_total": len(models),
        "loc_tails": sorted(t for t in tails if t),
        "english_msgs": sorted(english_msgs),
        "shapes": shapes,
    }


def main() -> None:
    data = collect()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"写入 {OUT}：模型 {data['model_total']} 个，type {len(data['shapes'])} 种，英文模板 {len(data['english_msgs'])} 条"
    )


if __name__ == "__main__":
    main()
