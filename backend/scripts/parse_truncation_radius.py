#!/usr/bin/env python3
"""解析截断的**伤害半径**报告——只读，一条都不写。

`简历与面试优化.md` §4 P1.1 把"先量半径再动手"列为前置步骤，理由写在 §6 风险 6：
新阈值 15000 是拍的。而"现有库里到底有多少简历真被切过、切掉多少字符、切在尾部还是中部"
不查就无从判断修复的优先级，也无从判断"结构感知截断"那半值不值得做。这张表回答的就是这些数。

量的是**字符数**（`char_length`），不是字节数（`length`）：`raw_text[:6000]` 切的是 Python 字符串，
utf8mb4 下一个中文字符最多 3 字节——本库里同一条 1,664 字符的简历存成 4,142 字节（2.5 倍，简历里混着
ASCII 所以不到 3），拿 `length()` 会把半径虚报两倍半。

四个截断位（计划文档 §3.1 只点了 R1/R4 两处，同一族的其余两处一起量，免得修完一处剩三处）：

| 族 | 入口 | 锚点 | 阈值 |
|---|---|---|---|
| 简历 | 上传后解析（主入口） | `app/services/resume_service.py:87` | 6000 |
| 简历 | 外部文本入口 | `app/services/external_service.py:62` | 6000（`_RESUME_TEXT_MAX`） |
| JD | 解析（`JDParseAgent` 也复用这条） | `app/services/jd_service.py:27` | 4000 |
| JD | embedding 文本 | `app/services/jd_embedding_service.py:71,81` | 6000（`RAWS_TEXT_LIMIT`） |

顺带出第二张表：库里已落的 `parsed_json` 的**字段完整度**（按两支 prompt 的 Schema 逐字段数"缺键 / 值为 null /
类型不对 / 空数组"）。这是 R2 的半径代理——真 provider 的一次通过率要到 P2 评测才有数，但"已落库的解析结果
长什么样"现在就能读，而且它直接决定 P1.1 那个 Pydantic Schema 该把哪些字段判成必填。

用法：
    python scripts/parse_truncation_radius.py            # 人读的两张表
    python scripts/parse_truncation_radius.py --json      # 机读，回写文档和账用
    python scripts/parse_truncation_radius.py --detail 8  # 最长的 8 条（默认 5）

退出码：0 = 正常出表。连不上库、或列读不出来时**不吞、不猜数**——异常直接抛出去（非 0 退出）。

代价：纯 CPU + 读库，一次 `char_length` 聚合 + 一次 `parsed_json` 全表读，与 provider 无关、零花费。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.models.history import JobDescription, Resume  # noqa: E402

# 计划文档 §4 P1.1 提议把简历阈值抬到的位置。§6 风险 6 明说这个数是拍的，
# 所以这里把它当作**被量的对象**报一遍占比，而不是当作事实。
PROPOSED_RESUME_THRESHOLD = 15000


@dataclass(frozen=True)
class Site:
    family: str  # "resume" | "jd"
    label: str
    anchor: str
    threshold: int


SITES: tuple[Site, ...] = (
    Site("resume", "简历解析（上传后主入口）", "app/services/resume_service.py:87", 6000),
    Site("resume", "简历解析（外部文本入口）", "app/services/external_service.py:62", 6000),
    Site("jd", "JD 解析（含 JDParseAgent）", "app/services/jd_service.py:27", 4000),
    Site("jd", "JD embedding 文本", "app/services/jd_embedding_service.py:71,81", 6000),
)

# 逐字取自两支 prompt 的【JSON Schema】：app/prompts/resume_parse.py:13-28、app/prompts/jd_parse.py:11-21。
# 类型按 schema 声明写：str / int / list / list_of_dict。
RESUME_FIELDS: tuple[tuple[str, str], ...] = (
    ("name", "str"),
    ("phone", "str"),
    ("email", "str"),
    ("years_exp", "int"),
    ("education", "str"),
    ("major", "str"),
    ("current_company", "str"),
    ("current_title", "str"),
    ("skills", "list"),
    ("work_experience", "list_of_dict"),
    ("project_experience", "list_of_dict"),
    ("self_evaluation", "str"),
)

JD_FIELDS: tuple[tuple[str, str], ...] = (
    ("title", "str"),
    ("company", "str"),
    ("location", "str"),
    ("salary_range", "str"),
    ("experience_requirement", "str"),
    ("education_requirement", "str"),
    ("responsibilities", "list"),
    ("required_skills", "list"),
    ("nice_to_have", "list"),
    ("keywords", "list"),
)


def _percentile(sorted_values: list[int], q: float) -> int | None:
    """小样本用最近秩法——不插值，报的就是库里真实存在的某个长度。"""
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[idx]


def measure_family(db, model, family: str, live_only_col: str, live_value: int) -> dict:
    """一条 SQL 出长度分布，不在 Python 侧拉全量 raw_text。

    `live_value` 不是笔误的 1：两张表的"活"标记**方向相反**——`tb_resume.is_deleted` 的活行是 0，
    `tb_jd.is_active` 的活行是 1。写成统一按 1 判，简历那一族会把 26 行全读成已删除（n=0）。
    """
    live_col = getattr(model, live_only_col)
    cols = [model.id, func.char_length(model.raw_text), func.coalesce(live_col, 0)]
    rows = db.query(*cols).all()

    all_lengths: list[int] = []
    live_lengths: list[int] = []
    empty_rows = 0
    for _id, n, flag in rows:
        if n is None or n == 0:
            empty_rows += 1
            continue
        all_lengths.append(n)
        if flag == live_value:
            live_lengths.append(n)

    def _dist(values: list[int]) -> dict:
        values = sorted(values)
        return {
            "n": len(values),
            "min": values[0] if values else None,
            "p50": _percentile(values, 0.50),
            "p90": _percentile(values, 0.90),
            "max": values[-1] if values else None,
            "mean": round(statistics.fmean(values)) if values else None,
        }

    distinct = db.query(func.count(func.distinct(func.md5(model.raw_text)))).scalar()

    return {
        "family": family,
        "table": model.__tablename__,
        "rows": len(rows),
        "distinct_texts": distinct,
        "empty_or_null_raw_text": empty_rows,
        "lengths": all_lengths,
        "lengths_live": live_lengths,
        "length_all": _dist(all_lengths),
        "length_live": _dist(live_lengths),
        "live_filter": f"{live_only_col}={live_value}",
        "thresholds": {},  # 下面按 site 填
    }


def build_report(db) -> dict:
    fam = {
        "resume": measure_family(db, Resume, "resume", "is_deleted", live_value=0),
        "jd": measure_family(db, JobDescription, "jd", "is_active", live_value=1),
    }

    for family in ("resume", "jd"):
        lengths = sorted(fam[family]["lengths"])
        live_lengths = sorted(fam[family]["lengths_live"])
        for site in SITES:
            if site.family != family:
                continue
            t = site.threshold
            over = [n for n in lengths if n > t]
            # "离火多近"：没超阈值但已在阈值 80% 以上——这些是下一次上传就可能变半径的行
            near = [n for n in lengths if int(t * 0.8) <= n <= t]
            fam[family]["thresholds"][f"{site.anchor}"] = {
                "label": site.label,
                "threshold": t,
                "over_count": len(over),
                "over_count_live": len([n for n in live_lengths if n > t]),
                "over_ratio_of_texts": round(len(over) / len(lengths), 4) if lengths else None,
                "dropped_chars_total": sum(n - t for n in over),
                "dropped_chars_max": max((n - t for n in over), default=0),
                "near_band_80_100pct": len(near),
            }

    # 提议中的新阈值：让"15000 够不够"这一问也有数，而不是留在风险清单里。
    resume_lengths = fam["resume"]["lengths"]
    over_proposed = [n for n in resume_lengths if n > PROPOSED_RESUME_THRESHOLD]
    fam["resume"]["proposed_threshold"] = {
        "threshold": PROPOSED_RESUME_THRESHOLD,
        "over_count": len(over_proposed),
        "over_ratio_of_texts": round(len(over_proposed) / len(resume_lengths), 4) if resume_lengths else None,
        "headroom_ratio_at_max": (
            round(PROPOSED_RESUME_THRESHOLD / max(resume_lengths), 2) if resume_lengths else None
        ),
    }
    for family in ("resume", "jd"):
        fam[family].pop("lengths")
        fam[family].pop("lengths_live")

    fam["resume"]["schema_probe"] = probe_parsed_json(db, Resume, RESUME_FIELDS)
    fam["jd"]["schema_probe"] = probe_parsed_json(db, JobDescription, JD_FIELDS)
    return {"generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"), "families": fam}


def probe_parsed_json(db, model, fields) -> dict:
    """已落库解析结果的字段完整度——R2 的半径代理。只读，不调 provider。"""
    rows = db.query(model.id, model.parsed_json).all()
    per_field = {
        key: {"missing_key": 0, "null_value": 0, "wrong_type": 0, "empty_list": 0, "ok": 0} for key, _ in fields
    }
    n_json_null = 0
    n_not_dict = 0
    for _id, parsed in rows:
        if parsed is None:
            n_json_null += 1
            continue
        if not isinstance(parsed, dict):
            n_not_dict += 1
            continue
        for key, kind in fields:
            if key not in parsed:
                per_field[key]["missing_key"] += 1
                continue
            value = parsed[key]
            if value is None:
                per_field[key]["null_value"] += 1
            elif (
                kind == "str"
                and not isinstance(value, str)
                or kind == "int"
                and (isinstance(value, bool) or not isinstance(value, int))
                or kind == "list"
                and not isinstance(value, list)
                or kind == "list_of_dict"
                and not isinstance(value, list)
            ):
                per_field[key]["wrong_type"] += 1
            elif kind in ("list", "list_of_dict") and len(value) == 0:
                per_field[key]["empty_list"] += 1
            else:
                per_field[key]["ok"] += 1

    scored = sum(1 for _id, p in rows if isinstance(p, dict))
    return {
        "rows": len(rows),
        "parsed_json_null": n_json_null,
        "parsed_json_not_dict": n_not_dict,
        "rows_scored": scored,
        "fields": per_field,
    }


def _fmt_len(n: int | None) -> str:
    return "—" if n is None else f"{n:,}"


def print_human(report: dict, detail: int) -> None:
    print("=" * 78)
    print("解析截断伤害半径（只读；长度单位=字符，非字节）")
    print("=" * 78)

    for family, fam in report["families"].items():
        d = fam["length_all"]
        print(f"\n【{family}】表 {fam['table']}")
        print(
            f"  行数 {fam['rows']}｜去重后的文本 {fam['distinct_texts']} 份"
            f"｜无文本(null/0) {fam['empty_or_null_raw_text']} 行"
        )
        print(
            f"  长度分布：min {_fmt_len(d['min'])} / p50 {_fmt_len(d['p50'])} / "
            f"p90 {_fmt_len(d['p90'])} / max {_fmt_len(d['max'])} / 均值 {_fmt_len(d['mean'])}"
        )
        lv = fam["length_live"]
        print(f"  仅活行({fam['live_filter']})：n={lv['n']} p50 {_fmt_len(lv['p50'])} max={_fmt_len(lv['max'])}")
        for anchor, t in fam["thresholds"].items():
            ratio = t["over_ratio_of_texts"]
            pct = "—" if ratio is None else f"{ratio * 100:.1f}%"
            print(
                f"  ▷ {t['label']}（{anchor}）阈值 {t['threshold']:,}："
                f"超阈 {t['over_count']} 份 / 其中活行 {t['over_count_live']} 份（{pct}）"
                f"，被切掉共 {t['dropped_chars_total']:,} 字符（单份最多 {t['dropped_chars_max']:,}）"
                f"｜落在阈值 80–100% 的 {t['near_band_80_100pct']} 份"
            )
        if "proposed_threshold" in fam:
            p = fam["proposed_threshold"]
            ratio = p["over_ratio_of_texts"]
            pct = "—" if ratio is None else f"{ratio * 100:.1f}%"
            print(
                f"  ▷ 提议阈值 {p['threshold']:,}：超阈 {p['over_count']} 份（{pct}）"
                f"｜最长的一份只用掉新阈值的 1/{p['headroom_ratio_at_max'] or '∞'}"
            )

        sp = fam["schema_probe"]
        print(
            f"  已落解析结果：{sp['rows']} 行里 parsed_json 为 null 的 {sp['parsed_json_null']} 行"
            f"，非 dict 的 {sp['parsed_json_not_dict']} 行，按字段计分母 {sp['rows_scored']} 行"
        )
        bad = []
        for key, c in sp["fields"].items():
            lost = c["missing_key"] + c["null_value"] + c["wrong_type"] + c["empty_list"]
            if lost:
                parts = ", ".join(
                    f"{lbl} {c[k]}"
                    for lbl, k in (
                        ("缺键", "missing_key"),
                        ("null", "null_value"),
                        ("类型不对", "wrong_type"),
                        ("空数组", "empty_list"),
                    )
                    if c[k]
                )
                bad.append(f"{key} {lost}/{sp['rows_scored']}（{parts}）")
        print("    有缺失的字段：" + ("；".join(bad) if bad else "无——全部字段齐全且类型对"))

    print("\n" + "=" * 78)
    print("读法：超阈 0 份 = 这条修复在**本库**当前没有受害者，属潜在缺陷；半径由上传内容决定，不是常量。")
    print("=" * 78)

    if detail:
        print(f"\n最长的 {detail} 条简历（id / 字符数 / 文件名）：")
        db = SessionLocal()
        try:
            rows = (
                db.query(Resume.id, func.char_length(Resume.raw_text), Resume.file_name)
                .order_by(func.char_length(Resume.raw_text).desc())
                .limit(detail)
                .all()
            )
            for rid, n, fname in rows:
                print(f"  {rid:>4}  {_fmt_len(n):>8}  {fname}")
        finally:
            db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="输出机读 JSON")
    ap.add_argument("--detail", type=int, default=5, help="列出最长的 N 条简历（0 = 不列）")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        report = build_report(db)
    finally:
        db.close()

    if args.json:
        report["database"] = engine.url.render_as_string(hide_password=True)
        report["read_only"] = True
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report, args.detail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
