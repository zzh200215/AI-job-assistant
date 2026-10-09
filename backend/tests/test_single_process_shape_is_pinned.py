"""§10.3 / D127：把「一容器一进程一份 Chroma」钉成一条会红的形状。

嵌入式 Chroma persistent client 每个进程各持一份（`app/core/chroma_client.py`）。原先挂在同一行的
那半句"WebSocket 引擎状态也按进程持有、跨副本亲和未解"在 2026-10-09 的 D163 里被现量推翻了：E16
之后引擎工作态全部从落库消息推断，副本之间看不见的是容量计数器与在途 30 秒计时器（都无害），
真缺陷是逐题评分投给本进程线程池而**全树无人重扫**——那条已经由 `requeue_stale_turn_evaluations`
收掉，而且它不需要等多副本，一次发布就能触发。

现在这个守卫盯的是同一时刻剩下的两件事：**Chroma 每进程一份**，以及**调度器 7 条任务没有主选举**
（副本数 >1 就每人跑一遍：提醒重发、账单重复生成）。触发点仍是同一个——副本数或 worker 数一旦 >1。
今天没有仪器会因为那一刻而红——`backend/Dockerfile` 的 CMD 不带 `--workers`，两份 compose 里没有任何
`replicas:`。所以这条守卫不是记录现状，而是把"扩副本的那一刻必须回来拍 §10.3"钉死：谁改动这两个数
之一，就得先回答向量库与定时任务的重复触发往哪放。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = (ROOT / "docker-compose.yml", ROOT / "docker-compose.prod.yml")
BACKEND_DOCKERFILE = ROOT / "backend" / "Dockerfile"

MAX_PROCESSES_PER_CONTAINER = 1


def declared_replicas(text: str) -> dict[str, int]:
    """compose 文本 → {服务名: 声明的副本数}。没写 `replicas:` 的服务不进字典（=1）。"""
    doc = yaml.safe_load(text) or {}
    services = doc.get("services") or {}
    found: dict[str, int] = {}
    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        value = svc.get("replicas")
        if value is None:
            deploy = svc.get("deploy")
            if isinstance(deploy, dict):
                value = deploy.get("replicas")
        if value is not None:
            found[str(name)] = int(value)
    return found


def uvicorn_workers(text: str) -> int | None:
    """Dockerfile / shell 文本里 uvicorn 的 `--workers`；没写返回 None（uvicorn 默认单进程）。

    两种写法都要认：shell 形式 `--workers 4` / `--workers=4`，以及 JSON 数组形式里那个
    `"--workers", "4"`（`backend/Dockerfile:60` 用的就是数组，所以分隔符是引号与逗号，不是空格）。
    """
    hit = re.search(r"--workers[\"',\s=]*(\d+)", text)
    return int(hit.group(1)) if hit else None


def process_shape_violations(compose_texts: dict[str, str], dockerfile: str) -> list[str]:
    """把两处形状合成一句判决：返回违反"一容器一进程"的说明，空表即合格。"""
    bad: list[str] = []
    for path, text in compose_texts.items():
        for name, count in declared_replicas(text).items():
            if count > MAX_PROCESSES_PER_CONTAINER:
                bad.append(f"{path}: service '{name}' declares replicas={count}")
    workers = uvicorn_workers(dockerfile)
    if workers is not None and workers > MAX_PROCESSES_PER_CONTAINER:
        bad.append(f"{BACKEND_DOCKERFILE.name}: uvicorn started with --workers={workers}")
    return bad


def _real_texts() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in COMPOSE_FILES}


def test_the_shipped_shape_is_one_process_per_container():
    """现状：两份 compose 都不声明副本，Dockerfile 不带 --workers → 一容器一进程一份 Chroma。"""
    violations = process_shape_violations(_real_texts(), BACKEND_DOCKERFILE.read_text(encoding="utf-8"))
    assert not violations, (
        "部署形状第一次出现多进程/多副本：" + "；".join(violations) + "。"
        "这一刻 §10.3（服务端向量库）与调度器 7 条定时任务的重复触发同时从"
        "「将来才会发生」变成「正在发生」，必须先拍那两条再放行这个改动。"
    )


def test_the_rulers_are_not_counting_air():
    """防空转：解析器必须真的看得见这两个文件里的形状，否则上一条永远绿。"""
    texts = _real_texts()
    assert set(texts) == {"docker-compose.yml", "docker-compose.prod.yml"}
    for name, text in texts.items():
        services = (yaml.safe_load(text) or {}).get("services") or {}
        assert services, f"{name} 解析出来没有任何 service——这把尺子在数空气"
        assert "backend" in services, f"{name} 里没有 backend 服务：判据的锚点变了，要重取"

    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "uvicorn" in dockerfile, "backend/Dockerfile 里不再启动 uvicorn：--workers 的判据要重取"
    assert (
        uvicorn_workers(dockerfile) is None
    ), "backend/Dockerfile 已经带 --workers 了，这条守卫的「现状」半边该改写，而不是让它绿着骗人"


def test_a_second_replica_is_caught():
    """反向证据（真文件改一刀）：给 prod 的 backend 服务插入 `replicas: 2`。

    插的是服务级键而不是再开一个 `deploy:`——prod compose 的 backend 本来就已经有一个
    `deploy:` 块（资源限制），再塞一个会变成重复键，后者覆盖前者，反向证据就悄悄落不进文本。
    """
    text = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    mutated = re.sub(r"(\n  backend:\n)", r"\1    replicas: 2\n", text, count=1)
    assert mutated != text, "prod compose 里 backend 服务的锚点变了，反向证据没落进文本"
    assert declared_replicas(mutated) == {"backend": 2}
    violations = process_shape_violations(
        {"docker-compose.prod.yml": mutated}, BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    )
    assert violations == ["docker-compose.prod.yml: service 'backend' declares replicas=2"], violations


def test_a_second_worker_is_caught():
    """反向证据（真文件改一刀）：把 --workers 塞进 Dockerfile 那条 CMD。"""
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    mutated = dockerfile.replace('"--port", "8000"]', '"--port", "8000", "--workers", "4"]')
    assert mutated != dockerfile, "backend/Dockerfile 的 CMD 形状变了，反向证据没落进文本"
    assert uvicorn_workers(mutated) == 4
    assert process_shape_violations(_real_texts(), mutated) == ["Dockerfile: uvicorn started with --workers=4"]


def test_declaring_a_single_replica_stays_green():
    """不许假红：显式写 replicas: 1 是合规的，守卫只盯 >1。"""
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    mutated = re.sub(r"(\n  backend:\n)", r"\1    replicas: 1\n", text, count=1)
    assert mutated != text
    assert declared_replicas(mutated) == {"backend": 1}
    assert (
        process_shape_violations({"docker-compose.yml": mutated}, BACKEND_DOCKERFILE.read_text(encoding="utf-8")) == []
    )
