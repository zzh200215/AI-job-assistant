#!/usr/bin/env python3
"""能力 API Python 示例客户端（M6 / T6-3）。

用法：
    python python_client.py --key sk-xxxx --base-url https://<api-domain>/api/v1/external
    python python_client.py --key sk-xxxx --base-url http://localhost:8000/api/v1/external
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys

import urllib.request
import urllib.error


def _request(base_url: str, key: str, path: str, payload: dict) -> dict:
    url = f"{base_url}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[HTTP {exc.code}] {body}", file=sys.stderr)
        sys.exit(1)


def verify_webhook(secret: str, raw_body: bytes, signature: str) -> bool:
    """订阅方校验 Webhook 签名（HMAC-SHA256）。"""
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def main() -> int:
    parser = argparse.ArgumentParser(description="能力 API 示例客户端")
    parser.add_argument("--key", required=True, help="X-API-Key")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1/external")
    args = parser.parse_args()

    # 1. 简历解析
    parsed = _request(
        args.base_url,
        args.key,
        "/resume/parse",
        {
            "content": "张三，5 年后端开发经验，精通 Python / Django / MySQL，主导过电商订单系统重构",
            "request_id": "py-demo-1",
        },
    )
    print("[resume/parse]", json.dumps(parsed, ensure_ascii=False)[:200])

    resume = parsed.get("data") or {"skills": ["Python"]}

    # 2. 匹配评估
    match = _request(
        args.base_url,
        args.key,
        "/match/evaluate",
        {
            "resume": resume,
            "jd": {"title": "资深后端工程师", "required_skills": ["Python", "Django", "Redis"]},
            "request_id": "py-demo-2",
        },
    )
    print("[match/evaluate] score =", match.get("data", {}).get("match_score"))

    # 3. 模拟面试（逐题评分）
    interview = _request(
        args.base_url,
        args.key,
        "/interview/simulate",
        {
            "resume": resume,
            "jd": {"title": "后端工程师"},
            "answers": [
                {"question": "请简述 Python 中 GIL 的作用", "answer": "GIL 使同一时刻仅一个线程执行字节码"}
            ],
            "request_id": "py-demo-3",
        },
    )
    print("[interview/simulate] evaluations =", len(interview.get("data", {}).get("evaluations", [])))

    print("\n全部能力 API 调用成功。Webhook 验签函数见 verify_webhook()。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
