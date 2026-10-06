"""评估脚本的 provider 闸：默认只许 mock，跑真 provider 必须显式 `--allow-real`。

为什么要有这道闸（2026-10-06，D133）：本机 `backend/.env` 写的是 `LLM_PROVIDER=qwen` /
`EMBEDDING_PROVIDER=qwen`，而 `eval_rag.py` 不像 pytest 那样有 conftest 把 provider 钉成 mock——
我把那扇门连着跑了 4 次，实际打的是真 API：今天 `prompt_trace` 多出 350 行、
133,427 prompt + 63,366 completion tokens（`cost_cents` 恒 0 只因价目表里没有这两个模型，
不等于没花钱），而账上明写"真 provider 下全量 50 条 RAG 评估未批，别擅自跑"。
第二个理由同样是尺子：真 rewrite 让融合臂 run-to-run 抖 ±0.05（同一棵树三次 0.847/0.813/0.800），
所以它不能当删前删后的对照。

CI 不受影响：工作流在 env 里就是 `LLM_PROVIDER: mock` / `EMBEDDING_PROVIDER: mock`，
`config.py:39/100` 的默认值也是 mock。
"""

from __future__ import annotations

import sys

from app.core.config import settings

MOCK = "mock"


def non_mock_providers() -> dict[str, str]:
    """当前不是 mock 的 provider 名与值（值只回显 provider 字段，不含密钥）。"""
    current = {
        "LLM_PROVIDER": (settings.LLM_PROVIDER or MOCK).strip().lower(),
        "EMBEDDING_PROVIDER": (settings.EMBEDDING_PROVIDER or MOCK).strip().lower(),
    }
    return {k: v for k, v in current.items() if v != MOCK}


def require_mock(script: str, allow_real: bool = False) -> str:
    """mock 就直接过；不是 mock 又没显式允许 -> 退出码 2 并说清怎么跑才对。"""
    real = non_mock_providers()
    if not real:
        return MOCK
    if allow_real:
        print(f"[provider 闸] {script}: 显式允许真 provider（{real}）；结果 run-to-run 会抖，别拿它当基线。")
        return "real"
    env = " ".join(f"{k}={MOCK}" for k in real)
    # SystemExit(字符串) 会把退出码变成 1；这里要的是可判读的 2（"被闸拦住"与"脚本自己崩了"要分得开）
    print(
        f"[provider 闸] {script} 拒绝运行：当前 provider 是 {real}，不是 {MOCK}。\n"
        f"  为什么有这道闸：见 scripts/provider_guard.py 的模块注释（一次未批的调用花掉 350 条 trace）。\n"
        f"  要 mock 跑（CI 口径）：{env} python scripts/{script}\n"
        f"  确实要跑真 provider（花钱，且融合臂不可复现）：加 --allow-real。",
        file=sys.stderr,
    )
    raise SystemExit(2)
