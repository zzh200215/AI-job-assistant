"""RAG 检索质量评估脚本

用法（在 backend/ 目录下运行）：
    python scripts/eval_rag.py                     # 默认加载 tests/eval/rag_eval.jsonl
    python scripts/eval_rag.py --top-k 5           # 指定 recall@K 的 K
    python scripts/eval_rag.py --sample 10          # 只跑前 10 条
    python scripts/eval_rag.py --output report.json # 输出 JSON 报告

    CI（一次性语料 + mock provider，见 scripts/seed_rag_corpus.py）：
    python scripts/eval_rag.py --min-lexical-recall 0.7 --min-lexical-keyword-hit 0.7 --max-empty-results 0
    该语料实测：词法 recall@5 0.813 / keyword 0.88，随机基线 recall 0.479 / keyword 0.411。

两组指标，别混着看：
  - 融合路 recall@K / mrr / keyword_hit : 走完向量 + BM25 + 改写 + RRF + rerank 的最终结果
  - 词法路 lexical_*                    : 只走 BM25 那一路（不碰向量、不碰改写）
在 EMBEDDING_PROVIDER=mock 的环境里向量路没有语义（"随机取 5 个切片"和它的 recall 只差
0.16 上下），所以那里**只能门词法路和"管道没断"**，语义召回分照旧报出但不设门槛。

输出指标：
  - recall@K   : 期望 doc_type 在 top-K 结果中出现的比例
  - mrr        : Mean Reciprocal Rank（期望 doc_type 首次出现的倒数排名均值）
  - keyword_hit: 期望关键词在检索结果文本中命中的比例
  - per_doc_type_recall : 每个 doc_type 的独立召回率
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保项目根目录在 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("eval_rag")


# ===================== 加载评估集 =====================


def load_eval_set(path: str) -> list[dict]:
    """加载 JSONL 格式的评估集。"""
    items = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning("跳过无效行 %d: %s", line_no, e)
    return items


# ===================== 指标计算 =====================


def recall_at_k(retrieved_types: list[str], expected_types: list[str]) -> float:
    """期望 doc_type 在检索结果中出现的比例。"""
    if not expected_types:
        return 1.0
    hit = sum(1 for t in expected_types if t in retrieved_types)
    return hit / len(expected_types)


def reciprocal_rank(retrieved_types: list[str], expected_types: list[str]) -> float:
    """期望 doc_type 在检索结果中首次出现的倒数排名。"""
    for i, t in enumerate(retrieved_types):
        if t in expected_types:
            return 1.0 / (i + 1)
    return 0.0


def keyword_hit_rate(texts: list[str], expected_keywords: list[str]) -> float:
    """期望关键词在检索结果文本中命中的比例。"""
    if not expected_keywords:
        return 1.0
    combined = " ".join(texts).lower()
    hit = sum(1 for kw in expected_keywords if kw.lower() in combined)
    return hit / len(expected_keywords)


def _per_type_recall(rows: list[tuple[list[str], list[str]]]) -> dict[str, float]:
    """(检索到的 doc_type, 期望 doc_type) 列表 -> 每个 doc_type 的独立召回率。"""
    hit: dict[str, int] = {}
    total: dict[str, int] = {}
    for retrieved_types, expected_types in rows:
        for t in expected_types:
            total[t] = total.get(t, 0) + 1
            if t in retrieved_types:
                hit[t] = hit.get(t, 0) + 1
    return {t: round(hit.get(t, 0) / total[t], 3) for t in sorted(total)}


# ===================== 主评估循环 =====================


def run_eval(eval_set: list[dict], top_k: int = 5, *, db=None, user_id: int | None = None) -> dict:
    """逐条评估并汇总指标。

    `db` 必传：`multi_recall` 在没有会话时会 fail-closed 直接返回空
    （没有会话就没法做租户/用户可见性过滤）。以前这个脚本不带 db 就调它，于是
    每一条都拿到空结果、recall 恒为 0.0——这道门从来没有量过检索质量。

    检索抛异常的 query **不参与指标计算**，单独计数：以前它们被记成"召回 0"，
    于是"库连不上/没权限"和"检索到了但不相关"在报告里长得一模一样。
    全部 query 都异常时指标是 None（没测出）而不是 0.0（测了，很差）。

    返回:
        {
          "total": int,
          "retrieved": int,             # 真正拿到检索结果的条数
          "retrieval_errors": int,      # 抛异常的条数
          "empty_results": int,         # 没抛异常但一条都没召回
          "error_samples": [str],
          "recall@K": float | None,
          "mrr": float | None,
          "keyword_hit_rate": float | None,
          "per_doc_type_recall": {doc_type: float},
          "details": [...]
        }
    """
    # 延迟 import，避免在无 DB/Chroma 环境崩溃
    from app.services.multi_recall import multi_recall

    recalls = []
    rrs = []
    khits = []
    errors: list[tuple[str, str]] = []
    empty_results = 0
    per_type_rows: list[tuple[list[str], list[str]]] = []
    details = []

    for idx, item in enumerate(eval_set):
        query = item["query"]
        expected_types = item.get("expected_doc_types", [])
        expected_keywords = item.get("expected_keywords", [])

        error = None
        try:
            results = multi_recall(query, db=db, user_id=user_id, top_k=top_k)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:160]}"
            errors.append((query, error))
            logger.warning("query=%r 检索失败: %s", query, exc)
            results = []

        retrieved_types = list(dict.fromkeys(r.get("doc_type", "") for r in results if r.get("doc_type")))
        texts = [r.get("text", "") for r in results]

        if error is None and not results:
            empty_results += 1

        r = recall_at_k(retrieved_types, expected_types)
        rr = reciprocal_rank(retrieved_types, expected_types)
        kh = keyword_hit_rate(texts, expected_keywords)

        if error is None:
            recalls.append(r)
            rrs.append(rr)
            khits.append(kh)
            per_type_rows.append((retrieved_types, expected_types))

        details.append(
            {
                "query": query,
                "error": error,
                "recall": round(r, 3) if error is None else None,
                "rr": round(rr, 3) if error is None else None,
                "keyword_hit": round(kh, 3) if error is None else None,
                "retrieved_types": retrieved_types,
                "expected_types": expected_types,
            }
        )

        if (idx + 1) % 10 == 0:
            logger.info("已评估 %d/%d ...", idx + 1, len(eval_set))

    per_type = _per_type_recall(per_type_rows)

    scored = len(recalls)
    report = {
        "total": len(eval_set),
        "retrieved": scored,
        "retrieval_errors": len(errors),
        "empty_results": empty_results,
        "error_samples": [f"{query}: {error}" for query, error in errors][:3],
        f"recall@{top_k}": round(sum(recalls) / scored, 3) if scored else None,
        "mrr": round(sum(rrs) / scored, 3) if scored else None,
        "keyword_hit_rate": round(sum(khits) / scored, 3) if scored else None,
        "per_doc_type_recall": per_type,
        "details": details,
    }
    return report


# ===================== 词法（BM25）单独一路 + 随机基线 =====================


def _lexical_hits(query: str, top_k: int, visible_doc_ids: set[str] | None) -> tuple[list[str], list[str]]:
    """词法那一路的 top-K：BM25 排序 → 回 Chroma 取类型/文本 → 按可见集合裁剪。

    `_bm25_score` 只给 chunk_id，类型和文本要补水——和 `_rrf_fuse` 里"给只有词法命中的
    切片补水"是同一件事，只不过这里不需要融合。
    """
    from app.core.chroma_client import get_knowledge_collection
    from app.services.multi_recall import _bm25_score

    chunk_ids = [cid for cid, _score in _bm25_score(query, top_k=top_k)]
    if not chunk_ids:
        return [], []

    data = get_knowledge_collection().get(ids=chunk_ids, include=["documents", "metadatas"])
    ids = data.get("ids") or []
    documents = data.get("documents") or []
    metadatas = data.get("metadatas") or []
    # Chroma 的 get(ids=...) 按它自己的顺序返回，不是请求顺序；必须按 id 回查，
    # 否则词法排名会被打乱，recall/mrr 量的就不是 BM25 而是 collection 的存储顺序。
    by_cid: dict[str, tuple[str, str]] = {}
    for i, cid in enumerate(ids):
        meta = metadatas[i] if i < len(metadatas) else {}
        by_cid[cid] = (
            str((meta or {}).get("doc_id", "")),
            ((meta or {}).get("doc_type", ""), documents[i] if i < len(documents) else ""),
        )

    types: list[str] = []
    texts: list[str] = []
    for cid in chunk_ids:  # 保持 BM25 排名顺序
        entry = by_cid.get(cid)
        if entry is None:
            continue
        doc_id, (doc_type, text) = entry
        # 与融合路同一条底线：不可见的文档连类型都不该漏出去
        if visible_doc_ids is not None and doc_id not in visible_doc_ids:
            continue
        types.append(doc_type)
        texts.append(text)
        if len(types) >= top_k:
            break
    return types, texts


def run_lexical_eval(eval_set: list[dict], *, db, user_id: int | None = None, top_k: int = 5) -> dict:
    """只量词法召回，不碰向量、不碰改写。

    为什么单列而不是只看融合结果：CI 里 EMBEDDING_PROVIDER=mock，向量路是按文本 hash 出的
    伪向量——可复现，但没有语义。在这样的环境里融合分数被无语义的候选搅动，语义门槛既测不出
    好坏也随时会被无关改动碰翻。词法那一路不受 provider 真假影响，是这份一次性语料上唯一
    能真的门住语义的数。
    """
    from app.services.multi_recall import _BM25Index
    from app.utils.knowledge_access import get_visible_knowledge_doc_ids

    visible = get_visible_knowledge_doc_ids(db, user_id=user_id)

    recalls, rrs, khits = [], [], []
    errors: list[tuple[str, str]] = []
    per_type_rows: list[tuple[list[str], list[str]]] = []
    empty_results = 0

    for item in eval_set:
        query = item["query"]
        expected_types = item.get("expected_doc_types", [])
        expected_keywords = item.get("expected_keywords", [])

        error = None
        try:
            types, texts = _lexical_hits(query, top_k, visible)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:160]}"
            errors.append((query, error))
            logger.warning("query=%r 词法检索失败: %s", query, exc)
            types, texts = [], []

        if error is None:
            if not types:
                empty_results += 1
            recalls.append(recall_at_k(types, expected_types))
            rrs.append(reciprocal_rank(types, expected_types))
            khits.append(keyword_hit_rate(texts, expected_keywords))
            per_type_rows.append((types, expected_types))

    scored = len(recalls)
    index = _BM25Index.get()
    return {
        "total": len(eval_set),
        "retrieved": scored,
        "retrieval_errors": len(errors),
        "empty_results": empty_results,
        "error_samples": [f"{query}: {error}" for query, error in errors][:3],
        f"recall@{top_k}": round(sum(recalls) / scored, 3) if scored else None,
        "mrr": round(sum(rrs) / scored, 3) if scored else None,
        "keyword_hit_rate": round(sum(khits) / scored, 3) if scored else None,
        "per_doc_type_recall": _per_type_recall(per_type_rows),
        # 门失败时先分清"索引压根没建起来"还是"建起来了但召不准"
        "bm25_corpus_chunks": index._corpus_count,
        "bm25_build_failed": index.build_failed,
    }


def random_metric_baselines(
    eval_set: list[dict], *, top_k: int, draws: int = 200, seed: int = 20260920
) -> dict[str, float] | None:
    """在这份语料上"随机抓 top_k 个切片"能拿到的 recall@K / mrr / keyword_hit。

    门槛只有明显高于对应指标的基线才有意义。实测（CI 的 91 切片 / 8 种 doc_type 种子语料）：
    随机 recall@5 = 0.487、keyword_hit = 0.413，而 ci.yml 里那句 "min recall >= 0.5" 从写下
    起就没和这个数比过——随机检索也能"过"。语料读不到时返回 None（没有基线可比，不编一个数）。
    """
    import random

    from app.core.chroma_client import get_knowledge_collection

    if not eval_set:
        return None
    try:
        data = get_knowledge_collection().get(include=["documents", "metadatas"])
    except Exception as exc:
        logger.warning("读语料失败，随机基线无从计算: %s", exc)
        return None

    pairs = [
        ((m or {}).get("doc_type", ""), (t or ""))
        for m, t in zip(data.get("metadatas") or [], data.get("documents") or [], strict=False)
    ]
    if not pairs:
        return None

    rng = random.Random(seed)
    totals = {"recall": 0.0, "mrr": 0.0, "keyword_hit": 0.0}
    for _ in range(draws):
        for item in eval_set:
            expected_types = item.get("expected_doc_types", [])
            expected_keywords = item.get("expected_keywords", [])
            types, texts = [], []
            for t, text in rng.sample(pairs, min(top_k, len(pairs))):
                types.append(t)
                texts.append(text)
            totals["recall"] += recall_at_k(types, expected_types)
            totals["mrr"] += reciprocal_rank(types, expected_types)
            totals["keyword_hit"] += keyword_hit_rate(texts, expected_keywords)

    n = draws * len(eval_set)
    return {
        "recall": round(totals["recall"] / n, 3),
        "mrr": round(totals["mrr"] / n, 3),
        "keyword_hit": round(totals["keyword_hit"] / n, 3),
    }


def check_thresholds(
    report: dict,
    *,
    top_k: int,
    min_recall: float | None = None,
    min_mrr: float | None = None,
    min_keyword_hit: float | None = None,
    max_retrieval_errors: int | None = 0,
    min_lexical_recall: float | None = None,
    min_lexical_keyword_hit: float | None = None,
    max_empty_results: int | None = None,
    embedding_provider: str | None = None,
    random_baselines: dict[str, float] | None = None,
) -> list[str]:
    """Return human-readable failure reasons for a completed RAG report.

    `max_retrieval_errors` 默认 0：只要有任何一条 query 是"检索直接抛异常"，
    这份报告就不能算测过——先报这条，再谈阈值。

    融合路的三个门槛（recall/mrr/keyword_hit）在 `embedding_provider=mock` 下直接判失败：
    那里的向量没有语义，过与不过都说明不了检索质量。要门语义，门词法路那两个。
    `random_baselines` 是同一份语料上"随机抓 K 个切片"的各指标值：门槛不高于自己的基线
    就等于没门槛，所以这里也一起检查。
    """
    failed = []
    errors = report.get("retrieval_errors", 0)
    if max_retrieval_errors is not None and errors > max_retrieval_errors:
        samples = "; ".join(report.get("error_samples", []))
        failed.append(
            f"retrieval_errors {errors} > {max_retrieval_errors}（{report['total']} 条里 {errors} 条检索直接抛异常，"
            f"指标不算测出。样例：{samples or '无'}）"
        )

    if max_empty_results is not None:
        empty = report.get("empty_results", 0)
        if empty > max_empty_results:
            failed.append(
                f"empty_results {empty} > {max_empty_results}（{report['total']} 条里 {empty} 条融合检索一条都没召回，"
                f"该查链路/可见性而不是查相关性）"
            )

    recall_key = f"recall@{top_k}"
    fused_floors = ((recall_key, min_recall), ("mrr", min_mrr), ("keyword_hit_rate", min_keyword_hit))
    floors_set = [key for key, floor in fused_floors if floor is not None]
    if floors_set and (embedding_provider or "").strip().lower() == "mock":
        failed.append(
            f"融合路门槛（{', '.join(floors_set)}）在 EMBEDDING_PROVIDER=mock 下不成立："
            f"向量路是文本 hash 出的伪向量，这个数只反映语料里 doc_type 的密度"
            f"（随机基线 recall={random_baselines.get('recall') if random_baselines else '未算出'}）。"
            "要门语义请用 --min-lexical-recall / --min-lexical-keyword-hit，要看真召回请换真 embedding provider。"
        )
    else:
        for key, floor in fused_floors:
            if floor is None:
                continue
            value = report.get(key)
            if value is None:
                failed.append(f"{key} 未测出（没有一条 query 拿到可用检索结果），门槛 {floor} 无从比较")
            elif value < floor:
                failed.append(f"{key} {value} < {floor}")

    lexical = report.get("lexical") or {}
    for key, floor, label in (
        (recall_key, min_lexical_recall, "词法"),
        ("keyword_hit_rate", min_lexical_keyword_hit, "词法"),
    ):
        if floor is None:
            continue
        value = lexical.get(key)
        context = (
            f"（{lexical.get('retrieved', 0)}/{lexical.get('total', 0)} 条测出，其中空结果 "
            f"{lexical.get('empty_results', 0)} 条、异常 {lexical.get('retrieval_errors', 0)} 条，"
            f"BM25 覆盖 {lexical.get('bm25_corpus_chunks', '未建')} 切片"
            f"{'，且索引构建失败' if lexical.get('bm25_build_failed') else ''}）"
        )
        if value is None:
            failed.append(f"{label} {key} 未测出{context}，门槛 {floor} 无从比较")
        elif value < floor:
            failed.append(f"{label} {key} {value} < {floor}{context}")

    if random_baselines:
        for label, key, floor in (
            (recall_key, "recall", min_recall),
            ("mrr", "mrr", min_mrr),
            ("keyword_hit_rate", "keyword_hit", min_keyword_hit),
            (f"词法 {recall_key}", "recall", min_lexical_recall),
            ("词法 keyword_hit_rate", "keyword_hit", min_lexical_keyword_hit),
        ):
            base = random_baselines.get(key)
            if floor is not None and base is not None and floor <= base:
                failed.append(f"{label} 门槛 {floor} ≤ 随机基线 {base}：这道门分不出好坏，抬门槛或换语料")

    return failed


# ===================== CLI =====================


def resolve_eval_user(db, requested: int | None) -> tuple[int | None, str]:
    """评估按哪个身份的可见范围检索；返回 (user_id, 说明)。

    找不到身份就返回 (None, 原因)——绝不能退回"不带 db 调用"，那条路会被
    `multi_recall` fail-closed 成空结果，看起来像 recall=0 的质量问题。
    管理员优先（全量可见）；没有管理员时挑一个真的看得到知识文档的用户，并把这个
    口径写进报告，免得"评估用的是谁的权限"变成隐变量。
    """
    from sqlalchemy.exc import SQLAlchemyError

    from app.core.config import settings
    from app.core.user_roles import ADMIN_ROLE
    from app.models.user import User
    from app.utils.knowledge_access import get_visible_knowledge_doc_ids

    def describe(user, visible) -> str:
        scope = "全量可见" if visible is None else f"可见 {len(visible)} 篇知识文档"
        return f"{user.username}(id={user.id}) 的可见范围：{scope}"

    try:
        if requested is not None:
            user = db.get(User, requested)
            if user is None:
                return None, f"--user-id {requested} 在库里不存在"
            visible = get_visible_knowledge_doc_ids(db, user_id=user.id)
            if visible is not None and not visible:
                return None, f"{user.username}(id={user.id}) 看不到任何知识文档，评估会恒为 0"
            return user.id, describe(user, visible)

        candidates = []
        for username in settings.admin_usernames_list:
            user = db.query(User).filter(User.username == username).first()
            if user is not None:
                candidates.append(user)
        candidates.extend(
            db.query(User).filter(User.role == ADMIN_ROLE, User.id.notin_([u.id for u in candidates])).all()
        )
        # 没有管理员就退而求其次：按 id 顺序找一个看得到文档的普通用户
        candidates.extend(db.query(User).order_by(User.id).limit(20).all())

        seen: set[int] = set()
        ordered: list[User] = []
        for user in candidates:
            if user.id not in seen:
                seen.add(user.id)
                ordered.append(user)

        for user in ordered:
            visible = get_visible_knowledge_doc_ids(db, user_id=user.id)
            if visible is None or visible:
                return user.id, describe(user, visible)
        return None, f"查了 {len(ordered)} 个用户，没有一个能看到知识文档（知识库为空？），评估无法进行"
    except SQLAlchemyError as exc:
        return None, f"读取用户失败（数据库不可用？）：{type(exc).__name__}: {str(exc)[:160]}"


def main():
    parser = argparse.ArgumentParser(description="RAG 检索质量评估")
    parser.add_argument(
        "--eval-set", default=str(_PROJECT_ROOT / "tests" / "eval" / "rag_eval.jsonl"), help="评估集 JSONL 路径"
    )
    parser.add_argument("--top-k", type=int, default=5, help="recall@K 的 K 值")
    parser.add_argument("--sample", type=int, default=None, help="只跑前 N 条")
    parser.add_argument("--output", default=None, help="输出 JSON 报告路径")
    parser.add_argument("--min-recall", type=float, default=None, help="Fail if recall@K is below this threshold")
    parser.add_argument("--min-mrr", type=float, default=None, help="Fail if MRR is below this threshold")
    parser.add_argument(
        "--min-keyword-hit", type=float, default=None, help="Fail if keyword hit rate is below this threshold"
    )
    parser.add_argument(
        "--max-retrieval-errors",
        type=int,
        default=0,
        help="允许多少条 query 在检索阶段直接抛异常（默认 0：一条都不允许，指标才算测出）",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="以哪个用户的可见范围检索；默认取 ADMIN_USERNAMES 里的管理员（全量可见）",
    )
    parser.add_argument(
        "--min-lexical-recall",
        type=float,
        default=None,
        help="Fail if BM25-only recall@K is below this threshold（不受 embedding provider 真假影响）",
    )
    parser.add_argument(
        "--min-lexical-keyword-hit",
        type=float,
        default=None,
        help="Fail if BM25-only keyword hit rate is below this threshold（词法路里区分度最高的一个数）",
    )
    parser.add_argument(
        "--max-empty-results",
        type=int,
        default=None,
        help="允许多少条 query 的融合检索返回空（CI 传 0：空结果说明链路或可见性断了，不是相关性差）",
    )
    args = parser.parse_args()

    eval_set = load_eval_set(args.eval_set)
    logger.info("加载评估集 %d 条 from %s", len(eval_set), args.eval_set)

    if args.sample:
        eval_set = eval_set[: args.sample]
        logger.info("截取前 %d 条", args.sample)

    from app.core.config import settings
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        user_id, identity = resolve_eval_user(db, args.user_id)
        if user_id is None:
            print(f"[FAIL] 无法确定评估身份：{identity}")
            return 2
        logger.info("检索可见范围按 %s (user_id=%s)", identity, user_id)
        report = run_eval(eval_set, top_k=args.top_k, db=db, user_id=user_id)
        lexical = run_lexical_eval(eval_set, db=db, user_id=user_id, top_k=args.top_k)
        baselines = random_metric_baselines(eval_set, top_k=args.top_k)
    finally:
        db.close()

    provider = (settings.EMBEDDING_PROVIDER or "mock").strip().lower()
    report["lexical"] = lexical
    report["report_type"] = "rag"
    report["run_meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_set": str(Path(args.eval_set).resolve()),
        "top_k": args.top_k,
        "sample": args.sample,
        "retrieval_identity": identity,
        "embedding_provider": provider,
        "random_metric_baselines": baselines,
        "thresholds": {
            "min_recall": args.min_recall,
            "min_mrr": args.min_mrr,
            "min_keyword_hit": args.min_keyword_hit,
            "max_retrieval_errors": args.max_retrieval_errors,
            "min_lexical_recall": args.min_lexical_recall,
            "min_lexical_keyword_hit": args.min_lexical_keyword_hit,
            "max_empty_results": args.max_empty_results,
        },
    }

    recall_key = f"recall@{args.top_k}"

    # 打印摘要
    print("\n" + "=" * 58)
    print(f"RAG 评估报告  (共 {report['total']} 条, recall@{args.top_k}, 口径 {identity})")
    print("=" * 58)
    print(f"  embedding provider : {provider}")
    if provider == "mock":
        print("                        ← 伪向量无语义，融合路只报数不门语义；语义看词法那一路")
    if baselines:
        print(
            f"  随机基线（同语料随机抓 {args.top_k} 个切片）: "
            f"recall={baselines['recall']}  mrr={baselines['mrr']}  keyword={baselines['keyword_hit']}"
            "（门槛不高于对应基线就等于没门槛）"
        )
    else:
        print("  随机基线             : 未算出（语料读不到？门槛无从校验）")
    print(
        f"  融合路             : {report['retrieved']} 条成功"
        f"（异常 {report['retrieval_errors']}，空结果 {report['empty_results']}）"
        f"  {recall_key}={report[recall_key]}  mrr={report['mrr']}  keyword={report['keyword_hit_rate']}"
    )
    print(
        f"  词法路 BM25        : {lexical['retrieved']} 条成功"
        f"（异常 {lexical['retrieval_errors']}，空结果 {lexical['empty_results']}，"
        f"索引覆盖 {lexical['bm25_corpus_chunks']} 切片"
        f"{'，索引构建失败' if lexical['bm25_build_failed'] else ''}）"
        f"  {recall_key}={lexical[recall_key]}  mrr={lexical['mrr']}  keyword={lexical['keyword_hit_rate']}"
    )
    print()
    print(f"  Per Doc-Type Recall ({'融合 / 词法'}, 括号内是该类 query 数):")
    for t in sorted(set(report["per_doc_type_recall"]) | set(lexical["per_doc_type_recall"])):
        n = sum(1 for item in eval_set if t in item.get("expected_doc_types", []))
        print(
            f"    {t:20s} : {report['per_doc_type_recall'].get(t, '-')} / "
            f"{lexical['per_doc_type_recall'].get(t, '-')}  ({n})"
        )
    if report["error_samples"] or lexical["error_samples"]:
        print("  检索异常样例:")
        for sample in report["error_samples"] + lexical["error_samples"]:
            print(f"    {sample}")
    print("=" * 58)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("报告已写入 %s", out_path)

    failed = check_thresholds(
        report,
        top_k=args.top_k,
        min_recall=args.min_recall,
        min_mrr=args.min_mrr,
        min_keyword_hit=args.min_keyword_hit,
        max_retrieval_errors=args.max_retrieval_errors,
        min_lexical_recall=args.min_lexical_recall,
        min_lexical_keyword_hit=args.min_lexical_keyword_hit,
        max_empty_results=args.max_empty_results,
        embedding_provider=provider,
        random_baselines=baselines,
    )

    if failed:
        print("[FAIL] RAG eval 未通过：")
        for item in failed:
            print(f"  - {item}")
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
