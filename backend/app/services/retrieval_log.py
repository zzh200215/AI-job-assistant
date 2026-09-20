"""节点内知识库读取的收集器：一次节点执行 = 若干条 `retrieval_log` 行。

套路和 `llm_service` 的用量累加器一样：节点入口安装收集器 → 检索函数往里记 →
节点落库时一次性写行。没有收集器时是空操作，所以知识库页自己的搜索、外部 API 的
检索都不会被记成某次编排的取证。

为什么写端住在这里而不是各个 agent 里：检索发生在 `rag_service` / `multi_recall`
内部，agent 只知道"拿到一段上下文"。让真正做查询的函数记，才不会漏掉
"查了但什么也没查到"这一类——那恰恰是最需要看见的。
"""

from contextvars import ContextVar
from typing import Any

# 一次节点最多留几条：面试题/优化类节点会按 doc_type 循环查询（5–8 条），
# 再多就是日志在替语料库占盘子。
MAX_TRACKED_PER_NODE = 12
# 每条命中在日志里保留的文本摘要长度（完整 chunk 文本还在知识库里，按 chunk_id 可取回）
RESULT_TEXT_CHARS = 160

_ACTIVE: ContextVar[list[dict[str, Any]] | None] = ContextVar("retrieval_calls", default=None)


def begin() -> None:
    """安装收集器；节点每次尝试都重新安装。"""
    _ACTIVE.set([])


def record(
    *,
    query: str,
    doc_type: str | None,
    top_k: int,
    results: list[dict[str, Any]],
    duration_ms: int,
) -> None:
    """记一次知识库读取。没有节点收集器时装作没发生。"""
    sink = _ACTIVE.get()
    if sink is None:
        return
    if len(sink) >= MAX_TRACKED_PER_NODE:
        return
    sink.append(
        {
            "query_text": (query or "")[:500],
            "doc_type_filter": doc_type,
            "top_k": int(top_k or 0),
            "result_count": len(results or []),
            "results": [_compact(item) for item in (results or [])[: top_k or 10]],
            "duration_ms": int(duration_ms),
        }
    )


def finish() -> list[dict[str, Any]]:
    """取走并卸载本轮收集结果。"""
    sink = _ACTIVE.get()
    _ACTIVE.set(None)
    return list(sink or [])


def _compact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": item.get("chunk_id"),
        "doc_id": item.get("doc_id"),
        "doc_title": item.get("doc_title", ""),
        "doc_type": item.get("doc_type", ""),
        "score": item.get("score", item.get("final_score")),
        "recalled_by": item.get("recalled_by"),
        "text": str(item.get("text") or "")[:RESULT_TEXT_CHARS],
    }
