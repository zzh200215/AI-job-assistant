"""量"真 provider 下主链跑成什么样"：耗时 / 谁答的 / 花多少 token / 有没有落库。

为什么单独一个脚本：这三件事平时分散在三个地方——HTTP 端到端在客户端、`response_source` 与 token 在
`prompt_trace` 表、而"记录有没有落地"要看接口返回。2026-11-14 那次实测（`docs/真provider实测.md`）
就是靠把这三样对起来，才发现"前两步成功了、第三步 429，整发 500，产出全丢"。

**这条会花钱**，所以和其它评估脚本同一道闸：默认只许 mock，要真打必须显式 `--allow-real`
（`scripts/provider_guard.py` 的模块注释里写着一次未批调用花掉 350 条 trace 的旧账）。

用法（先起后端）：

    python scripts/measure_real_chain.py --allow-real
    python scripts/measure_real_chain.py --allow-real --base http://127.0.0.1:8001/api --account demo

它只读不写业务数据（除了编排器自己会建任务/会话），并且**不会**去跑那几套全量评估。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.provider_guard import require_mock  # noqa: E402


def http(method: str, url: str, token: str | None = None, body: dict | None = None, timeout: int = 900):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "ignore")
        status = exc.code
    except Exception as exc:  # noqa: BLE001 - 量测脚本要把"连不上"也记成一条读数
        return {"status": None, "elapsed": round(time.perf_counter() - started, 2), "error": str(exc)[:200]}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"raw": raw[:400]}
    return {"status": status, "elapsed": round(time.perf_counter() - started, 2), "payload": payload}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-real", action="store_true", help="显式允许打真 provider（会花钱）")
    parser.add_argument("--base", default="http://127.0.0.1:8001/api")
    parser.add_argument("--account", default="demo")
    parser.add_argument("--password", default="Demo@12345")
    parser.add_argument("--jd-id", type=int, default=None)
    parser.add_argument("--poll-seconds", type=int, default=180, help="后台任务最多跟多久")
    args = parser.parse_args()

    mode = require_mock("measure_real_chain.py", allow_real=args.allow_real)
    print(f"[mode] {mode}")

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models.prompt_trace import PromptTrace

    print(
        f"[config] llm={settings.LLM_PROVIDER}/{settings.LLM_MODEL} "
        f"fallback={settings.LLM_FALLBACK_MODEL} embedding={settings.EMBEDDING_PROVIDER}/{settings.EMBEDDING_MODEL}"
    )

    db = SessionLocal()
    try:
        start_id = (db.query(PromptTrace.id).order_by(PromptTrace.id.desc()).first() or [0])[0]
    finally:
        db.close()
    print(f"[trace] start_id={start_id}")

    login = http("POST", f"{args.base}/auth/login", body={"account": args.account, "password": args.password})
    token = (login.get("payload") or {}).get("data", {}).get("access_token")
    if not token:
        print("登录失败，先确认后端起来了、账号存在：", login)
        return 1

    resumes = http("GET", f"{args.base}/resume/list?page_size=10", token=token)["payload"]["data"]["items"]
    if not resumes:
        print("这个账号没有简历：先用 create_demo_user.py 或 /demo/seed 灌一份")
        return 1
    resume_id = resumes[0]["id"]
    if args.jd_id:
        jd_id = args.jd_id
    else:
        items = http("GET", f"{args.base}/jd/list?page_size=10", token=token)["payload"]["data"]["items"]
        if not items:
            print("这个账号没有岗位：先 /demo/seed")
            return 1
        jd_id = items[0]["id"]
    print(f"[subject] resume={resume_id} jd={jd_id}")

    report: dict = {"mode": mode, "subject": {"resume_id": resume_id, "jd_id": jd_id}, "steps": []}

    # ① 前端真正打的那一发：编排器（后台任务）
    print("\n① POST /analysis/full（编排器，前端 SmartAnalysis 打的就是它）", flush=True)
    started = http("POST", f"{args.base}/analysis/full", token=token, body={"resume_id": resume_id, "jd_id": jd_id})
    task_id = (started.get("payload") or {}).get("data", {}).get("task_id")
    print(f"   status={started['status']} {started['elapsed']}s task_id={task_id}")
    task_timeline = []
    if task_id:
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < args.poll_seconds:
            got = http("GET", f"{args.base}/agent/task/{task_id}", token=token)
            data = (got.get("payload") or {}).get("data") or {}
            progress = data.get("progress") or {}
            snap = {
                "at": round(time.perf_counter() - t0, 1),
                "status": data.get("status"),
                "percent": progress.get("progress_percent"),
                "total_steps": progress.get("total_steps"),
                "current_step": progress.get("current_step"),
            }
            if (
                not task_timeline
                or task_timeline[-1]["status"] != snap["status"]
                or task_timeline[-1]["percent"] != snap["percent"]
            ):
                task_timeline.append(snap)
                print(
                    f"   t+{snap['at']:>6}s status={snap['status']} pct={snap['percent']} steps={snap['total_steps']}"
                )
            if snap["status"] not in {"pending", "running"}:
                break
            time.sleep(5)
    report["steps"].append({"step": "analysis/full", "accept": started, "timeline": task_timeline})

    # ② 推荐（会走 embedding）
    print("\n② GET /jobs/recommend", flush=True)
    rec = http("GET", f"{args.base}/jobs/recommend?resume_id={resume_id}&limit=5", token=token)
    rec_data = (rec.get("payload") or {}).get("data") or {}
    recs = rec_data.get("recommendations") or []
    print(f"   status={rec['status']} {rec['elapsed']}s scores={[r.get('match_score') for r in recs]}")
    report["steps"].append(
        {
            "step": "jobs/recommend",
            "status": rec["status"],
            "elapsed": rec["elapsed"],
            "scores": [r.get("match_score") for r in recs],
        }
    )

    # ③ 面试建会话（题目在后台生成）
    print("\n③ POST /interview/sessions", flush=True)
    iv = http(
        "POST",
        f"{args.base}/interview/sessions",
        token=token,
        body={"resume_id": resume_id, "jd_id": jd_id, "interview_type": "tech"},
    )
    iv_data = (iv.get("payload") or {}).get("data") or {}
    print(
        f"   status={iv['status']} {iv['elapsed']}s session={iv_data.get('id')} questions={iv_data.get('total_questions')}"
    )
    report["steps"].append(
        {
            "step": "interview/sessions",
            "status": iv["status"],
            "elapsed": iv["elapsed"],
            "questions": iv_data.get("total_questions"),
        }
    )

    time.sleep(20)  # 后台出题/后置写入留一点时间

    db = SessionLocal()
    try:
        rows = db.query(PromptTrace).filter(PromptTrace.id > start_id).order_by(PromptTrace.id.asc()).all()
        traces = [
            {
                "id": r.id,
                "family": r.prompt_family,
                "name": r.prompt_name,
                "source": (r.source or "")[:40],
                "response_source": r.response_source,
                "degraded": r.degraded,
                "status": r.status,
                "cache_hit": r.cache_hit,
                "duration_ms": r.duration_ms,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "error": (r.error_message or "")[:160],
            }
            for r in rows
        ]
    finally:
        db.close()

    report["traces"] = traces
    print(f"\n[traces] 新增 {len(traces)} 条")
    for t in traces:
        flag = "" if t["status"] == "success" else "  ← 失败"
        print(
            f"  #{t['id']} {t['family']}/{t['name']} src={t['response_source']} deg={t['degraded']} "
            f"{t['duration_ms']}ms tok={t['prompt_tokens']}/{t['completion_tokens']}{flag}"
            + (f"\n      {t['error']}" if t["error"] else "")
        )
    print(
        f"\n[summary] 真实(real) {sum(1 for t in traces if t['response_source'] == 'real')} 条 · "
        f"兜底 {sum(1 for t in traces if t['response_source'] == 'fallback_model')} 条 · "
        f"失败 {sum(1 for t in traces if t['status'] != 'success')} 条 · "
        f"prompt/completion tokens {sum(t['prompt_tokens'] or 0 for t in traces)}/{sum(t['completion_tokens'] or 0 for t in traces)}"
    )
    print("\n[提醒] 分数分布只有在 embedding 通道正常时才说明模型效果；见 docs/真provider实测.md §2.4")

    out = Path("reports/measure_real_chain.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[out] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
