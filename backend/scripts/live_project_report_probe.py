"""真 provider 跑一份单项目分析：量 token、秒数、每一节的落没落、复核拒了什么。

安全口径（一次没做好就是往他真库里写数据）：
* 先建同机临时库 `project_report_live_probe`，`os.environ["DATABASE_URL"]` 在 **import app 之前**
  指过去，并在动手前 assert `engine.url.database` 真是那一个；
* 从 llmXM **只读**一条真简历，复制进临时库；全程不 INSERT 到 llmXM；
* 口令只在这里拼接、一次都不打印；渲染出的 HTML 落到**仓库外**目录，PII 不进树；
* 结束时 DROP 临时库，并各用一条**新连接**读 llmXM 的表数与探针痕迹做前后对照。

跑法（花钱那一发由人自己敲：工具层的付费闸门不认代理人的点选授权，被拦两次就交回给人）：
  cd backend && ./.venv/Scripts/python.exe scripts/live_project_report_probe.py                  # 真 provider，会花钱
  cd backend && PROBE_PROVIDER=mock ./.venv/Scripts/python.exe scripts/live_project_report_probe.py  # 零花费，只验链路
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
OUTSIDE = Path("D:/AI/llmXM/_live_project_reports")

env = {}
with open(BACKEND / ".env", encoding="utf-8", errors="replace") as handle:
    for line in handle:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"')

HOST = env["MYSQL_HOST"]
PORT = env.get("MYSQL_PORT", "3306")
USER = env["MYSQL_USER"]
PASSWORD = env["MYSQL_PASSWORD"]
SOURCE_DB = env["MYSQL_DB"]
TEMP_DB = "project_report_live_probe"

os.environ["DATABASE_URL"] = f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{TEMP_DB}?charset=utf8mb4"
os.environ["APP_ENV"] = "development"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["LLM_PROVIDER"] = os.environ.get("PROBE_PROVIDER") or env.get("LLM_PROVIDER", "mock")
os.environ["EMBEDDING_PROVIDER"] = env.get("EMBEDDING_PROVIDER", "mock")
os.environ["REDIS_URL"] = ""
os.environ["RUN_SCHEDULER"] = "false"

sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

SOURCE_URL = f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/{SOURCE_DB}?charset=utf8mb4"
SERVER_URL = f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/?charset=utf8mb4"


def source_table_count() -> int:
    eng = create_engine(SOURCE_URL)
    try:
        with eng.connect() as conn:
            return int(
                conn.execute(
                    text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=:d"), {"d": SOURCE_DB}
                ).scalar()
            )
    finally:
        eng.dispose()


def probe_footprint_in_source() -> tuple[int, int]:
    """llmXM 里有没有探针留下的痕迹（用户/简历）。"""
    eng = create_engine(SOURCE_URL)
    try:
        with eng.connect() as conn:
            users = int(conn.execute(text("SELECT COUNT(*) FROM tb_user WHERE username LIKE 'live_probe_%'")).scalar())
            resumes = int(
                conn.execute(text("SELECT COUNT(*) FROM tb_resume WHERE file_name LIKE 'live_probe%'")).scalar()
            )
        return users, resumes
    finally:
        eng.dispose()


print("== 前置对照：llmXM ==")
before_tables = source_table_count()
before_footprint = probe_footprint_in_source()
print(f"  表数 {before_tables}  探针痕迹 {before_footprint}")

# 临时库
server = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
with server.connect() as conn:
    conn.execute(text(f"DROP DATABASE IF EXISTS `{TEMP_DB}`"))
    conn.execute(text(f"CREATE DATABASE `{TEMP_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
server.dispose()

import app.models  # noqa: E402, F401  —— 注册全部模型
from app.core.config import settings  # noqa: E402
from app.core.database import Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.history import Resume  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import project_report_service as svc  # noqa: E402
from app.services.project_report_html import render_project_report_html  # noqa: E402

assert engine.url.database == TEMP_DB, (engine.url.database, TEMP_DB)
assert settings.DATABASE_URL.endswith(TEMP_DB + "?charset=utf8mb4"), settings.DATABASE_URL[-40:]
print(f"== 写侧引擎指向临时库 {engine.url.database}，provider={os.environ['LLM_PROVIDER']} ==")

Base.metadata.create_all(bind=engine)

# 只读源库，挑一条有项目的真简历
source = create_engine(SOURCE_URL)
Session = sessionmaker(bind=engine)
db = Session()
chosen = None
try:
    with source.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT id, name, user_id, raw_text, parsed_json, file_name FROM tb_resume "
                    "WHERE parsed_json IS NOT NULL ORDER BY id DESC LIMIT 40"
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            parsed = row["parsed_json"]
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except json.JSONDecodeError:
                    continue
            projects = (parsed or {}).get("project_experience") or []
            longest = max((len(str(p.get("desc") or "")) for p in projects if isinstance(p, dict)), default=0)
            if len(projects) >= 1 and longest >= 140:
                chosen = (
                    int(row["id"]),
                    str(row["name"] or ""),
                    str(row["file_name"] or ""),
                    parsed,
                    projects,
                    longest,
                )
                break
finally:
    source.dispose()


def drop_temp() -> None:
    eng = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{TEMP_DB}`"))
    eng.dispose()


if chosen is None:
    print("没找到可用的真简历（近 40 条里项目正文都短于 140 字）")
    db.close()
    drop_temp()
    raise SystemExit(3)

resume_id_src, name, file_name, parsed, projects, longest = chosen
print(f"== 取用源简历 id={resume_id_src} 项目数={len(projects)} 最长项目正文={longest} 字 ==")

user = User(
    username="live_probe_run",
    email="live_probe_run@example.com",
    password=hash_password("StrongP@ssw0rd"),
    role="candidate",
)
db.add(user)
db.flush()
resume = Resume(
    name=name,
    file_name="live_probe.pdf",
    file_path="uploads/live_probe.pdf",
    file_type="pdf",
    file_size=1024,
    user_id=user.id,
    parsed_json=parsed,
)
db.add(resume)
db.commit()
target_resume_id = resume.id
project_index = max(range(len(projects)), key=lambda i: len(str((projects[i] or {}).get("desc") or "")))

print("== 前三节（档案 / 图解 / 使用建议，三发）==")
t0 = time.time()
report = svc.generate_project_report(db, target_resume_id, project_index, user_id=user.id)
elapsed_report = time.time() - t0
print(
    f"  用时 {elapsed_report:.1f}s  合计 {report.score_cell()}  评级 {report.grade}  难度 {report.difficulty.get('level')}"
)
print(f"  命中红线 {[row['key'] for row in report.excluded_by]}")
print(
    f"  图 {report.diagrams.get('figures') if report.diagrams else '整节缺席'}  使用建议 {'有' if report.advice else '缺席'}"
)
print(f"  阶段失败 {report.stage_errors}")
print(f"  出处 { {k: (v or {}).get('source') for k, v in report.provenance.items()} }")

print("== 第四节（二十题，一发）==")
t1 = time.time()
questions = svc.build_questions(db.get(Resume, target_resume_id), report)
elapsed_q = time.time() - t1
dist = questions.get("distribution") or {}
print(
    f"  用时 {elapsed_q:.1f}s  共 {dist.get('total')} 题（目标 {dist.get('target')}）"
    f" 可答 {dist.get('answerable')} 需补强 {dist.get('weak')} 高危 {dist.get('high_risk')} 配图 {dist.get('diagrammed')}"
)
print(f"  题型分布 {dist.get('by_kind')}")
print(
    f"  本题被拒 {len(report.questions_rejected)} 条，原因计数 "
    f"{ {r: sum(1 for x in report.questions_rejected if x.get('reason') == r) for r in {x.get('reason') for x in report.questions_rejected}} }"
)
report.questions = questions

print("== 交付前机检 ==")
try:
    html = render_project_report_html(report)
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    out = OUTSIDE / f"live_project_report_{int(time.time())}.html"
    out.write_text(html, encoding="utf-8", newline="\n")
    print(f"  过检，HTML {len(html.encode('utf-8')) / 1024:.1f} KB 写到仓库外：{out}")
except RuntimeError as exc:
    print("  未过检：\n" + str(exc)[:2000])

print("== 全部被拒条目按原因计数（对内，不上屏）==")
for label, rows in (
    ("红线", report.red_line_rejected),
    ("图解", report.diagram_rejected),
    ("建议", report.advice_rejected),
):
    reasons: dict[str, int] = {}
    for row in rows:
        reasons[str(row.get("reason"))] = reasons.get(str(row.get("reason")), 0) + 1
    print(f"  {label}：{len(rows)} 条 {reasons}")

print("== 真 provider 的账（临时库 prompt_trace）==")
with engine.connect() as conn:
    trace = (
        conn.execute(
            text(
                "SELECT source, prompt_version, model, response_source, status, cache_hit, duration_ms, "
                "prompt_tokens, completion_tokens, total_tokens FROM prompt_trace ORDER BY id"
            )
        )
        .mappings()
        .all()
    )
total = {"prompt": 0, "completion": 0, "all": 0}
for row in trace:
    total["prompt"] += int(row["prompt_tokens"] or 0)
    total["completion"] += int(row["completion_tokens"] or 0)
    total["all"] += int(row["total_tokens"] or 0)
    print(
        f"  {row['source'][:52]:<52} v={row['prompt_version']} src={row['response_source']} "
        f"{row['duration_ms']}ms in={row['prompt_tokens']} out={row['completion_tokens']}"
    )
print(f"  合计 token：prompt {total['prompt']} / completion {total['completion']} / total {total['all']}")

db.close()
engine.dispose()

# 收尾：删临时库，再对照源库
drop_temp()

after_tables = source_table_count()
after_footprint = probe_footprint_in_source()
print("== 后置对照：llmXM ==")
print(f"  表数 {after_tables}（前置 {before_tables}）  探针痕迹 {after_footprint}（前置 {before_footprint}）")
print(f"  阶段总用时：前三节 {elapsed_report:.1f}s + 第四节 {elapsed_q:.1f}s")
print(f"  临时库 {TEMP_DB} 已 DROP")
if after_tables != before_tables or after_footprint != before_footprint:
    print("!! 源库被改动，立刻查")
    raise SystemExit(4)
