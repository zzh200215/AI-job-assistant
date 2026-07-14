"""Export delivery-facing docs from the current FastAPI app.

Outputs:
- docs/generated/openapi.json
- docs/generated/api-reference.md
- docs/generated/deployment-guide.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402


def _normalize_methods(path_item: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for method, operation in path_item.items():
        if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
            continue
        items.append((method.upper(), operation))
    return items


def _group_operations(schema: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in _normalize_methods(path_item):
            tags = operation.get("tags") or ["misc"]
            summary = operation.get("summary") or operation.get("operationId") or ""
            for tag in tags:
                grouped[tag].append(
                    {
                        "method": method,
                        "path": path,
                        "summary": summary,
                    }
                )
    for tag in grouped:
        grouped[tag].sort(key=lambda item: (item["path"], item["method"]))
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _build_api_reference(schema: dict[str, Any], generated_at: str) -> str:
    grouped = _group_operations(schema)
    counts = Counter()
    for ops in grouped.values():
        for op in ops:
            counts[op["method"]] += 1

    lines = [
        "# 接口参考",
        "",
        f"- 生成时间: {generated_at}",
        "- API 文档: `docs/generated/openapi.json`",
        f"- 路由数量: {sum(counts.values())}",
        "",
        "## 方法统计",
        "",
        "| 方法 | 数量 |",
        "| --- | ---: |",
    ]
    for method in ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]:
        if counts.get(method):
            lines.append(f"| `{method}` | {counts[method]} |")

    for tag, ops in grouped.items():
        lines.extend(
            [
                "",
                f"## {tag}",
                "",
                "| Method | Path | Summary |",
                "| --- | --- | --- |",
            ]
        )
        for op in ops:
            lines.append(f"| `{op['method']}` | `{op['path']}` | {op['summary']} |")

    return "\n".join(lines).rstrip() + "\n"


def _build_deployment_guide(generated_at: str) -> str:
    return f"""# 部署指南

- 生成时间: {generated_at}
- 当前后端编排后端: `{settings.ORCHESTRATION_BACKEND}`
- 当前编排策略: `{settings.ORCHESTRATION_STRATEGY}`

## 环境前置

- Python 3.10+
- Node.js 18+
- MySQL 8.0+
- 可选 Redis（当 `ORCHESTRATION_BACKEND=redis_queue` 时启用）

## 启动步骤

```bash
cd backend
copy .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

## 交付验证

- 后端测试: `cd backend && pytest`
- 全量验证: `scripts/verify.ps1`
- 评测产物: `scripts/eval-quality.ps1`
- 接口文档导出: `cd backend && python scripts/export_delivery_docs.py`

## 关键配置

- `APP_ENV`
- `APP_DEBUG`
- `MYSQL_PASSWORD`
- `JWT_SECRET`
- `LLM_PROVIDER`
- `EMBEDDING_PROVIDER`
- `ORCHESTRATION_STRATEGY`
- `ORCHESTRATION_ENGINE`
- `ORCHESTRATION_BACKEND`
- `REDIS_URL`
- `RAG_TOP_K`
- `RAG_USE_PLANNER`
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Export delivery docs from the current app")
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "docs" / "generated"),
        help="Output directory for generated docs",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    schema = app.openapi()
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    (output_dir / "openapi.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "api-reference.md").write_text(
        _build_api_reference(schema, generated_at),
        encoding="utf-8",
    )
    (output_dir / "deployment-guide.md").write_text(
        _build_deployment_guide(generated_at),
        encoding="utf-8",
    )

    print(f"Generated docs in: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
