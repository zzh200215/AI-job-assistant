"""P3 第一项（D173）：`thread` 后端的两条边界，都被钉成会红的形状。

现量的事实（2026-10-09，开发库 + 两份 compose）：

* 进树的默认值都是 `thread`（`app/core/config.py:51`、`backend/.env.example:57`、`.env.production.example:69`、
  `docker-compose.prod.yml:45` 四处一致）；`docker-compose.yml` **根本不声明这个键**，于是落在 config.py 那一份上。
  本机 `backend/.env`（不进树）写的是 `redis_queue`，靠手工起 `scripts/run_orchestration_worker.py` 消费——
  这条不在门的射程里，门钉的是"签进树的默认值 + 签进树的编排"。
* **两份 compose 里都没有任何 worker 服务**（grep `worker|run_orchestration` 零命中），
  `scripts/run_orchestration_worker.py` 只活在 README 的常用命令表里。
* `ThreadOrchestrationBackend.shutdown()` 用的是 `cancel_futures=False`
  （`orchestration_backend.py:96`）：优雅退出时**排队里的任务不会被取消**，解释器 atexit 会等线程池把
  它们跑完。所以"thread 后端会在关闭时丢任务"这句常见说法只对**硬杀**（SIGKILL / OOM / 容器被删）成立。

下面两条把这两件事分别钉住：① 优雅关闭不丢排队任务（改成 `cancel_futures=True` 立刻红）；
② 谁哪天把默认值翻成 `redis_queue` 而 compose 里没有消费它的 worker 服务，就得先被这条拦住——
那种部署下任务是**入队即永远不跑**，30 分钟后才被 `mark_stale_running_tasks_failed` 标成 failed，
候选人看到的是"分析失败"而队列里那条元素还躺着。
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import yaml

from app.services.orchestration_backend import ThreadOrchestrationBackend
from app.services.orchestration_runner import TaskPayload

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = (ROOT / "docker-compose.yml", ROOT / "docker-compose.prod.yml")
BACKEND_DEFAULT_RE = re.compile(r"ORCHESTRATION_BACKEND[\"']?\s*[:=]\s*[^A-Za-z0-9]*([a-z_]+)")
CONFIG_DEFAULT_RE = re.compile(r'ORCHESTRATION_BACKEND:\s*str\s*=\s*"([a-z_]+)"')
CONFIG_PATH = ROOT / "backend" / "app" / "core" / "config.py"


# ---------------------------------------------------------------- ① 优雅关闭不丢排队任务


def test_graceful_shutdown_still_runs_every_queued_task():
    """`cancel_futures=False` 是刻意的：改了它就会在每次发布时吞掉候选人已经点下去的分析。

    4 个 worker、提交 8 个任务 → 必然有 4 个在队列里等着；`shutdown()` 之后 atexit 会把它们跑完。
    这里不走 atexit（测不了），只验证 `shutdown()` **没有**把等待中的 future 取消掉：
    让每个任务自己 set 一个事件，最后数总数。
    """
    backend = ThreadOrchestrationBackend()
    done = []
    lock = threading.Lock()
    started = threading.Event()

    def runner(payload: TaskPayload) -> None:
        with lock:
            done.append(payload.task_id)
            if len(done) == 1:
                started.set()
        time.sleep(0.02)  # 让后面的任务真的落在队列里而不是被同一批 worker 顺手拿走

    for i in range(8):
        backend.submit(TaskPayload(strategy_name="linear", task_id=i, resume_id=1, jd_id=1, user_id=1), runner)

    backend.shutdown()  # 不 wait：等价于发布时 uvicorn 关停里那一步

    deadline = time.time() + 10.0
    while len(done) < 8 and time.time() < deadline:
        time.sleep(0.02)

    assert started.is_set()
    assert sorted(done) == list(range(8)), f"优雅关闭吞掉了 {8 - len(done)} 个还在排队的任务：{sorted(done)}"


# ---------------------------------------------------------------- ② 默认值与 worker 服务的耦合


def defaults_in_text(text: str) -> list[str]:
    """compose 文本里出现过的 `ORCHESTRATION_BACKEND` 默认值（x-锚点块与 environment 都算）。"""
    return BACKEND_DEFAULT_RE.findall(text)


def config_default() -> str:
    """`config.py` 里那个进程内默认值——没有声明这个键的 compose 用的就是它。"""
    found = CONFIG_DEFAULT_RE.findall(CONFIG_PATH.read_text(encoding="utf-8"))
    assert len(found) == 1, f"config.py 里的 ORCHESTRATION_BACKEND 默认值读到了 {len(found)} 个：{found}"
    return found[0]


def services_running_the_worker(path: Path) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    found = []
    for name, svc in (doc.get("services") or {}).items():
        blob = " ".join(str(part) for part in ((svc or {}).get("command"), (svc or {}).get("entrypoint")))
        if "run_orchestration_worker" in blob:
            found.append(str(name))
    return found


def _violations(texts: dict[str, str], *, inherited_default: str | None = None) -> list[str]:
    """把两条判据合成一句判决（正向测试与反向证据共用它，避免两套逻辑漂移）。

    没声明这个键的文件**不是"没事"**：它落在 `config.py` 的进程内默认值上，所以这里按继承算，
    反向证据里翻 config 默认值能连带把 `docker-compose.yml` 一起拦下来。
    """
    base = config_default() if inherited_default is None else inherited_default
    bad: list[str] = []
    for name, text in texts.items():
        effective = defaults_in_text(text) or [base]
        if "redis_queue" in effective and not services_running_the_worker(ROOT / name):
            bad.append(f"{name}: 默认 backend=redis_queue，但没有任何服务跑 run_orchestration_worker")
    return bad


def test_redis_queue_default_would_need_a_worker_service():
    """今天的形状：prod compose 显式 `thread`、开发 compose 不声明（⇒ 继承 config.py 的 `thread`）、
    两份都没有 worker 服务 ⇒ 合规。谁把默认值翻成 `redis_queue`，这条就拦住谁。"""
    texts = {path.name: path.read_text(encoding="utf-8") for path in COMPOSE_FILES}

    assert _violations(texts) == []

    # 防空转：判据看到的必须是现量那份事实，键多了/值变了/正则不匹配了都会在这里红。
    observed = {name: defaults_in_text(text) for name, text in texts.items()}
    assert observed == {
        "docker-compose.yml": [],  # 不声明 ⇒ 走 config.py 的默认值，这本身就是要被钉住的一条
        "docker-compose.prod.yml": ["thread"],
    }, f"compose 里 ORCHESTRATION_BACKEND 的声明形状变了，本条的前提要重写：{observed}"
    assert config_default() == "thread", "config.py 的默认值已经不是 thread，下面的反向证据射程要重算"

    # 消费者为零是这一整条腿的承重事实，单独钉住：哪天 compose 里真的起了 worker，
    # 要重算的是"反向证据还该不该期望违规"，而不是让它在一个没标注的断言上莫名红。
    workers = {path.name: services_running_the_worker(path) for path in COMPOSE_FILES}
    assert workers == {
        "docker-compose.yml": [],
        "docker-compose.prod.yml": [],
    }, f"compose 里出现了 worker 服务，redis_queue 从此可以是合法的，本条的判据要重新谈：{workers}"

    # 反证一（打在副本上，不动工作树）：把 prod compose 的默认值翻成 redis_queue，必须被认出来。
    prod = texts["docker-compose.prod.yml"]
    mutated = prod.replace(
        "ORCHESTRATION_BACKEND: ${ORCHESTRATION_BACKEND:-thread}",
        "ORCHESTRATION_BACKEND: redis_queue",
        1,
    )
    assert mutated != prod, "prod compose 的锚点变了，反向证据没落进文本"
    assert defaults_in_text(mutated) == ["redis_queue"], "翻完默认值这条探针没认出来——判据在数空气"
    assert _violations({"docker-compose.prod.yml": mutated}) == [
        "docker-compose.prod.yml: 默认 backend=redis_queue，但没有任何服务跑 run_orchestration_worker"
    ]

    # 反证二：只翻 config.py 的默认值、compose 一行不动。不声明这个键的开发 compose 会跟着掉进
    # redis_queue，而树里没有任何 worker 服务消费它——这条也要拦住，否则"没声明"就是判据的盲区。
    assert _violations(texts, inherited_default="redis_queue") == [
        "docker-compose.yml: 默认 backend=redis_queue，但没有任何服务跑 run_orchestration_worker"
    ]
