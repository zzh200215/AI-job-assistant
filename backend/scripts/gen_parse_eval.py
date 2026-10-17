"""P2 评测集生成器：先有 gold（画像），再排版出简历原文。

方向必须是"gold → 文本"，不能反过来。理由沿用 `recommend_eval` 那条成文纪律
（`backend/tests/eval/recommend_eval.jsonl` 文件头第 1-5 行）：**标签不许由被测代码回生成**——
否则"解析准确率"变成"模型自己跟自己对答案"。这里被测的是 `chat_json` + 那两支解析 prompt，
gold 来自这份文件里手写的画像字段，文本是从画像渲染出来的，两者不同源。

同时留一条臂给**真实素材**：`kind: "real"` 那几行的文本直接取库里已抽取的真实简历 `raw_text`，
标签由正则从原文里取（电话/邮箱/姓名这类客观字段），并带 `_label_source` 说明它怎么来的——
正则不是被测系统的一部分，所以这不违反上一条。合成样本的排版我尽量打散（段名带 `▎` 装饰、
段序不同、字段缺项、中英混排），但它们仍然是"我知道答案才写的题"，F1 天然偏乐观：
**合成分只能当回归基线，不能当产品能力说事**，能当能力说的是真文本那一臂。这一点在
`简历与面试优化.md` §6 风险 5 里已经记着。

跑法（零 provider 花费，纯本地）：
    python scripts/gen_parse_eval.py            # 重写 tests/eval/parse_eval.jsonl
    python scripts/gen_parse_eval.py --check     # 只校验现有文件与生成结果一致，不写盘

`--check` 是给 CI 用的：语料是数据不是二进制，漂了要能看见。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

OUT = pathlib.Path("tests/eval/parse_eval.jsonl")
MIN_RESUME_SAMPLES = 24
MIN_JD_SAMPLES = 10
MIN_LONG_SAMPLES = 2
LONG_THRESHOLD = 15000

DECORATIONS = ("", "▎", "【", "# ")
FILLER_ZH = "负责召回链路的建设与稳定性治理，参与检索质量评估体系的设计与落地，" "推动线上服务在高峰期保持可用。"
FILLER_EN = (
    "Owned the retrieval pipeline and its reliability work, designed the evaluation harness "
    "for retrieval quality, and kept the service healthy through peak traffic. "
)


def _profile(
    index: int,
    *,
    language: str,
    cohort: str,
    name: str,
    phone: str,
    email: str,
    years_exp: int,
    title: str,
    company: str,
    skills: list[str],
    education: str = "本科",
    major: str = "计算机科学与技术",
    projects: list[str] | None = None,
    deco: str = "",
    long_tail: bool = False,
) -> dict:
    """一份画像 = 一条样本的 gold。渲染函数只读它，不回写它。"""
    jobs = [{"company": company, "title": title, "start": "2021-07", "end": "至今", "desc": ""}]
    if long_tail:
        # 长样本特意把最近的一份工作压在段尾：那正是 `[:6000]` 硬切会丢掉的位置。
        jobs.insert(
            0,
            {"company": "早期东家", "title": "初级工程师", "start": "2019-07", "end": "2021-06", "desc": ""},
        )
    # 段尾那行同时是 gold 的一部分：长样本要能证明"值钱的内容留在被切的那一侧之外"。
    tail_line = (
        f"最近一份：{title}｜{company}｜2024-03 至今"
        if long_tail
        else (f"{title}, {company}" if language == "en" else f"{title}｜{company}")
    )
    return {
        "id": f"p{index:02d}",
        "language": language,
        "cohort": cohort,
        "deco": deco,
        "long_tail": long_tail,
        "tail_line": tail_line,
        "gold": {
            "name": name,
            "phone": phone,
            "email": email,
            "years_exp": years_exp,
            "current_title": title,
            "current_company": company,
            "skills": skills,
            "education": education,
            "major": major,
            "work_experience": jobs,
            "project_experience": [{"name": p} for p in (projects or [])],
        },
    }


def _fill(filler: str, target_chars: int) -> str:
    """按**目标字数**铺正文——长度是这条语料要量的东西之一（>15000 那一档），
    不能靠"重复 24 遍"这种拍出来的次数：第一版就是这么算出 0 份长简历、被形状锁当场拦下。
    """
    reps = max(1, target_chars // len(filler) + 1)
    return filler * reps


def _target(p: dict) -> int:
    if p["long_tail"]:
        return 3500  # 工作经历保持"人样"的长度，最近那份仍在段尾
    return 900 if p["cohort"] in ("experienced", "real") else 320


def _bulk(p: dict, chars: int) -> str:
    """长样本的体量来自**内容多**（一堆项目、证书、获奖、兼职），不是某一栏被灌到 18k 字。
    第一版我就是这么造的，结果按优先级整段丢掉"工作经历"是**正确行为**，gold 里那份最新工作
    反而没了——样本不真实会把评测指到一个不存在的问题上。
    """
    filler = FILLER_EN if p["language"] == "en" else FILLER_ZH
    lines = []
    n = 0
    while sum(len(x) for x in lines) < chars:
        n += 1
        lines.append(f"第 {n} 项：{filler}")
    return "\n".join(lines)


def _render_zh(p: dict) -> str:
    g = p["gold"]
    deco = p["deco"]
    blocks = [f"{g['name']}\n电话：{g['phone']}　邮箱：{g['email']}\n"]
    if p["cohort"] != "fresh":
        blocks.append(f"{deco}工作经历\n{_fill(FILLER_ZH, _target(p))}\n{p['tail_line']}\n")
    if p["gold"]["project_experience"]:
        names = "、".join(x["name"] for x in p["gold"]["project_experience"])
        blocks.append(f"{deco}项目经历\n{_fill(FILLER_ZH, _target(p) // 2)}\n{names}\n")
    skills = "、".join(g["skills"])
    blocks.append(f"{deco}专业技能\n{skills}\n")
    blocks.append(f"{deco}教育背景\n{g['education']}　{g['major']}\n")
    if p["cohort"] == "switcher":
        blocks.append(f"{deco}转行说明\n从上一份工作转向该方向的动机与已完成的学习。\n")
    if p["long_tail"]:
        # 体量堆在**低优先级**那两侧（证书/其他）：超预算时它们先被整段丢，工作经历留得住。
        blocks.append(f"{deco}证书与获奖\n{_bulk(p, 20000)}\n")
        blocks.append(f"{deco}其他\n{_bulk(p, 6000)}\n")
    return "\n".join(blocks)


def _render_en(p: dict) -> str:
    g = p["gold"]
    blocks = [f"{g['name']}\nPhone: {g['phone']}  Email: {g['email']}\n"]
    blocks.append(f"Experience\n{_fill(FILLER_EN, _target(p))}\n{p['tail_line']}\n")
    if p["gold"]["project_experience"]:
        names = "; ".join(x["name"] for x in p["gold"]["project_experience"])
        blocks.append(f"Projects\n{names}\n")
    blocks.append("Skills\n" + ", ".join(g["skills"]) + "\n")
    blocks.append(f"Education\n{g['education']} - {g['major']}\n")
    return "\n".join(blocks)


def render(p: dict) -> str:
    return _render_en(p) if p["language"] == "en" else _render_zh(p)


def _jd(
    index: int, *, title: str, company: str, skills: list[str], nice: list[str], responsibilities: list[str]
) -> dict:
    body = "\n".join(f"- {r}" for r in responsibilities)
    required = "、".join(skills)
    text = (
        f"{title}｜{company}\n\n岗位职责\n{body}\n\n"
        f"任职要求\n1. 具备：{required}\n2. 加分项：{('、'.join(nice)) or '无'}\n"
    )
    return {
        "id": f"j{index:02d}",
        "gold": {
            "title": title,
            "company": company,
            "required_skills": skills,
            "nice_to_have": nice,
            "responsibilities": responsibilities,
        },
        "raw_text": text,
    }


def _profiles() -> list[dict]:
    zh_common = {"language": "zh", "education": "本科", "major": "计算机科学与技术"}
    out: list[dict] = [
        _profile(
            1,
            cohort="fresh",
            name="林可",
            phone="13800001101",
            email="linke@example.com",
            years_exp=0,
            title="后端开发实习生",
            company="星海网络",
            skills=["Python", "MySQL", "Redis"],
            projects=["校园二手交易平台"],
            **zh_common,
        ),
        _profile(
            2,
            cohort="experienced",
            name="赵明",
            phone="13900002202",
            email="zhaoqm@example.com",
            years_exp=4,
            title="Java 后端工程师",
            company="远山科技",
            skills=["Java", "Spring Boot", "Kafka"],
            projects=["订单中台重构"],
            deco=DECORATIONS[1],
            **zh_common,
        ),
        _profile(
            3,
            cohort="switcher",
            name="孙悦",
            phone="13700003303",
            email="sunyue@example.com",
            years_exp=2,
            title="数据分析转算法工程",
            company="初芒数据",
            skills=["Python", "SQL", "Pandas"],
            projects=["增长指标看板"],
            **zh_common,
        ),
        _profile(
            4,
            cohort="experienced",
            language="en",
            name="Ada Chen",
            phone="13600004404",
            email="ada.chen@example.com",
            years_exp=6,
            title="Senior Backend Engineer",
            company="Northwind",
            skills=["Go", "gRPC", "PostgreSQL"],
            projects=["Billing service migration"],
            education="Bachelor",
            major="Computer Science",
        ),
        _profile(
            5,
            cohort="experienced",
            name="周立",
            phone="13500005505",
            email="zhouyan@example.com",
            years_exp=3,
            title="算法工程师",
            company="长河智能",
            skills=["PyTorch", "RAG", "向量检索"],
            projects=["知识库问答"],
            deco=DECORATIONS[2],
            **zh_common,
        ),
        _profile(
            6,
            cohort="fresh",
            language="en",
            name="Marco Liu",
            phone="13400006606",
            email="marco.liu@example.com",
            years_exp=1,
            title="Junior Frontend Engineer",
            company="Bluepeak",
            skills=["React", "TypeScript", "Vite"],
            projects=["Admin dashboard"],
            education="Bachelor",
            major="Software Engineering",
        ),
    ]
    # 20 份合成简历的批量位：段名装饰、 cohorts、语言轮着换，避免"一个模板抄 20 遍"。
    names = [
        "陈平",
        "许明",
        "沈青",
        "江岚",
        "蒋立",
        "韩亮",
        "尤立",
        "何明",
        "施安",
        "华南",
        "Ivy Wang",
        "Ken Zhao",
        "Luna Shi",
        "Owen Gu",
        "Rui Feng",
        "Tina He",
        "Vera Song",
        "Yan Bo",
        "Zoe Ma",
        "Bea Qin",
    ]
    skill_pool = [
        ["Python", "FastAPI", "MySQL"],
        ["Java", "MyBatis", "Redis"],
        ["Go", "Kubernetes", "etcd"],
        ["React", "Vue", "TypeScript"],
        ["PyTorch", "NLP", "Transformer"],
        ["Rust", "Tokio", "gRPC"],
        ["C++", "gRPC", "Protobuf"],
        ["Node.js", "NestJS", "MongoDB"],
        ["Scala", "Spark", "Hive"],
        ["Flutter", "Dart", "iOS"],
        ["Kotlin", "Android", "Compose"],
        ["Java", "Kafka", "Flink"],
        ["Python", "Airflow", "dbt"],
        ["Terraform", "AWS", "Linux"],
        ["Prometheus", "Grafana", "SRE"],
        ["Elasticsearch", "Logstash", "Kibana"],
        ["PostgreSQL", "TimescaleDB", "Go"],
        ["Spring Cloud", "Nacos", "Java"],
        ["RAG", "LangGraph", "向量库"],
        ["CUDA", "TensorRT", "C++"],
    ]
    for i, nm in enumerate(names, start=7):
        is_en = nm[0].isascii()
        out.append(
            _profile(
                i,
                cohort=("fresh" if i % 7 == 0 else "switcher" if i % 5 == 0 else "experienced"),
                language="en" if is_en else "zh",
                education="Bachelor" if is_en else "本科",
                major="Computer Science" if is_en else "计算机科学与技术",
                name=nm,
                phone=f"13{80000000 + i * 1111}"[:11],
                email=f"user{i}@example.com",
                years_exp=1 + (i % 8),
                title=f"工程师 {i}",
                company=f"样本公司{i}",
                skills=skill_pool[(i - 7) % len(skill_pool)],
                projects=[f"样本项目{i}"],
                deco=DECORATIONS[i % len(DECORATIONS)],
            )
        )
    # 两份 >15000 的长样本：同时量 P1.1 的截断修复与段落识别（值钱的经历压在尾部）。
    for j, nm in enumerate(("席文", "程舟"), start=27):
        out.append(
            _profile(
                j,
                cohort="experienced",
                language="zh",
                name=nm,
                phone=f"139000{j:02d}77777"[:11],
                email=f"long{j}@example.com",
                years_exp=9,
                title="资深后端工程师",
                company="长风出行",
                skills=["Python", "Go", "Kafka", "MySQL"],
                projects=["计价引擎", "派单系统"],
                deco=DECORATIONS[1],
                long_tail=True,
                education="硕士",
                major="软件工程",
            )
        )
    return out


PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
NAME_RE = re.compile(r"^([一-龥]{2,4})\s*$", re.M)
# 真实排版里姓名常常写成「姓名：<三个字的人名>」这种带标签的形式，光靠"整行只有中文名"会漏掉一半样本。
NAMED_RE = re.compile(r"姓\s*名[:：]\s*([一-龥]{2,4})")

# ---------------------------------------------------------------------------
# 真文本臂的脱敏（2026-10-17 拍板：脱敏后再入库）
# ---------------------------------------------------------------------------
# `tests/eval/real_resumes/` 里那几份是从 dev 库导出的**真人简历**，原始文本带着一位真人的
# 姓名、手机号、QQ 邮箱和就读学校（具体值不复述——把它们写进注释等于换个地方再泄露一次）。
# 按账本里"已进 git 历史的不动"那条，手机号一旦提交就再也拿不出来，所以入库前先过这一层。
# 映射表固定 ⇒ 语料仍然逐字可复现（`--check` 照旧成立），而版式、长度档、段分布一概没动——
# 评测真正测的就是这些。
# 这一层是**幂等**的：已脱敏的文本再跑一遍一字不改。夹具本身已就地脱敏，函数留着是防"下次有人
# 把原始导出直接扔进夹具目录"——那种情况下语料仍然干净，而 test_eval_datasets 的 PII 门会红。
#
# 映射**按 token 分槽，不按文件序号**：那 4 份真文本其实只有 2 个人（3 份是同一人的不同排版 +
# 1 份演示数据）。按文件序号发假名会把同一个人变成 3 个人，生成器最后那句"覆盖了几个人"就跟着
# 说谎——它数的是 gold 里的不同姓名。跨文件先扫一遍、按首次出现顺序定槽，同一个人无论在几份文件
# 里出现都落到同一个假身份上。
# 这四个假名要过 `tests/test_no_mojibake.py` 那把字频尺：它判的是**串**稀有与否，不是单字
# （"赵晓波"/"赵晓雨"都被判过，而"郑晓东"是干净的）。改这里的名字前先跑那条测试。
FAKE_NAMES = ("周思远", "陈慧敏", "吴子昂", "王军")
FAKE_SCHOOLS = {"南昌大学": "临江大学", "北京师范大学": "云岭大学"}


def fake_phone(slot: int) -> str:
    """假手机号取 138001380XX 这段保留号；PII 门按这个形状放行，其余 11 位号一律判红。"""
    return f"138001380{slot + 1:02d}"


def fake_email(slot: int) -> str:
    """域名用 RFC 2606 的 example.com，永远不会是真邮箱。"""
    return f"resume{slot + 1:02d}@example.com"


def _slots(texts: list[str]) -> dict[str, dict[str, str]]:
    """按首次出现顺序给每份文本里的身份 token 定槽，返回逐文件的替换表。"""
    name_slot: dict[str, int] = {}
    phone_slot: dict[str, int] = {}
    email_slot: dict[str, int] = {}
    for text in texts:
        name = NAMED_RE.search(text) or NAME_RE.match(text.strip().splitlines()[0])
        if name and name.group(1) not in name_slot:
            name_slot[name.group(1)] = len(name_slot)
        for token in PHONE_RE.findall(text):
            phone_slot.setdefault(token, len(phone_slot))
        for token in EMAIL_RE.findall(text):
            email_slot.setdefault(token, len(email_slot))
    return {"name": name_slot, "phone": phone_slot, "email": email_slot}


def _apply(text: str, slots: dict[str, dict[str, str]]) -> str:
    out = text
    name = NAMED_RE.search(out) or NAME_RE.match(out.strip().splitlines()[0])
    if name:
        out = out.replace(name.group(1), FAKE_NAMES[slots["name"][name.group(1)] % len(FAKE_NAMES)])
    out = PHONE_RE.sub(lambda m: fake_phone(slots["phone"][m.group(0)]), out)
    out = EMAIL_RE.sub(lambda m: fake_email(slots["email"][m.group(0)]), out)
    for real_school, fake_school in FAKE_SCHOOLS.items():
        out = out.replace(real_school, fake_school)
    return out


def redact(text: str, texts: list[str]) -> str:
    """把一份真文本里的姓名/电话/邮箱/学校换成固定假值，其余一字不动。
    `texts` 是同一臂的全部文本（决定槽位），顺序必须与写盘时一致。"""
    return _apply(text, _slots(texts))


def _real_row(index: int, name_hint: str, raw_text: str) -> dict:
    """真实素材那一臂：标签由**正则从原文**取，不经过被测系统。取不到就留空，
    空位表示"这条没有这个 gold"，判卷器对空 gold 不计分（不猜）。
    """
    phone = PHONE_RE.search(raw_text)
    email = EMAIL_RE.search(raw_text)
    name = NAMED_RE.search(raw_text) or NAME_RE.match(raw_text.strip().splitlines()[0])
    return _row(
        kind="real",
        id=f"real{index:02d}",
        language="zh",
        cohort="real",
        source_file=name_hint,
        raw_text=raw_text,
        gold={
            "name": name.group(1) if name else "",
            "phone": phone.group(0) if phone else "",
            "email": email.group(0) if email else "",
        },
        required_fields=[k for k in ("name", "phone", "email") if (name or k != "name")],
        label_source="regex-on-source：正则不属于被测系统，符合 recommend_eval 头注释那条纪律",
    )


REAL_DIR = pathlib.Path("tests/eval/real_resumes")


def _real_rows() -> list[dict]:
    """库里抽取出的真实简历文本（4 份）。**不包含**我自己造的测试上传件——
    那一件（tb_resume id=82，9,597 字符，是四份真文本的拼接）曾经被当成真实素材算进过来，
    剔除的理由记在这里：拿自己拼的东西当"真实臂"，测的就不是真实分布了。
    """
    if not REAL_DIR.exists():
        return []
    paths = sorted(REAL_DIR.glob("*.txt"))
    texts = [path.read_text(encoding="utf-8") for path in paths]
    rows = []
    for i, (path, text) in enumerate(zip(paths, texts, strict=False), start=1):
        rows.append(_real_row(i, path.name, redact(text, texts)))
    return rows


ROW_KEYS = (
    "kind",
    "id",
    "cohort",
    "language",
    "long_tail",
    "source_file",
    "tail_line",
    "raw_text",
    "gold",
    "required_fields",
    "label_source",
)


def _row(**fields: object) -> dict:
    """三种类（合成简历 / JD / 真文本臂）共用同一个顶层形状。

    不齐本身就是件事：读的人得先判断这是哪一类才知道有哪些键。`test_eval_datasets.py` 里
    "同一文件顶层键形状必须一致"那条门刚立起来，就抓到了我之前那个不自齐的版本。
    """
    row = dict.fromkeys(ROW_KEYS, "")
    for key, value in fields.items():
        if key not in ROW_KEYS:
            raise KeyError(f"未知的行字段 {key}（要加就先加进 ROW_KEYS，别塞野键）")
        row[key] = value
    return row


def build_rows() -> list[dict]:
    rows: list[dict] = _real_rows()
    for p in _profiles():
        text = render(p)
        rows.append(
            _row(
                kind="resume",
                id=p["id"],
                language=p["language"],
                cohort=p["cohort"],
                long_tail=p["long_tail"],
                # fresh 档的模板里没有工作经历段，那种样本压根没有"段尾"可保——不硬塞一个
                # 从没出现在原文里的 needle，否则评测会把它算成丢尾（第一版就是这样 25/28）。
                tail_line=p["tail_line"] if p["tail_line"] in text else "",
                raw_text=text,
                gold=p["gold"],
                required_fields=["name", "phone", "email", "skills"],
                label_source="profile→render：gold 在前、文本在后，不经被测系统",
            )
        )
    for jd in [
        _jd(
            1,
            title="大模型应用工程师",
            company="长风出行",
            skills=["Python", "RAG", "向量检索"],
            nice=["LangGraph"],
            responsibilities=["建设召回链路", "负责评估体系"],
        ),
        _jd(
            2,
            title="后端开发工程师",
            company="星海网络",
            skills=["Java", "Spring Boot", "MySQL"],
            nice=["Kafka"],
            responsibilities=["订单服务开发与维护", "接口性能优化"],
        ),
        _jd(
            3,
            title="Data Platform Engineer",
            company="Northwind",
            skills=["Scala", "Spark", "Airflow"],
            nice=["dbt"],
            responsibilities=["own the batch pipeline", "data quality checks"],
        ),
        _jd(
            4,
            title="前端工程师",
            company="Bluepeak",
            skills=["React", "TypeScript"],
            nice=["Vite"],
            responsibilities=["搭建管理后台", "组件库维护"],
        ),
        _jd(
            5,
            title="算法工程师",
            company="长河智能",
            skills=["PyTorch", "NLP"],
            nice=["Transformer"],
            responsibilities=["意图识别模型", "模型评估与上线"],
        ),
        _jd(
            6,
            title="SRE",
            company="远山科技",
            skills=["Kubernetes", "Prometheus"],
            nice=["Terraform"],
            responsibilities=["可用性治理", "容量规划"],
        ),
        _jd(
            7,
            title="测试开发工程师",
            company="初芒数据",
            skills=["Python", "自动化测试"],
            nice=["性能测试"],
            responsibilities=["建设回归体系", "用例平台化"],
        ),
        _jd(
            8,
            title="数据分析师",
            company="华原咨询",
            skills=["SQL", "Pandas"],
            nice=["Tableau"],
            responsibilities=["指标体系", "专题分析"],
        ),
        _jd(
            9,
            title="Mobile Engineer",
            company="Appia",
            skills=["Kotlin", "Compose"],
            nice=["Flutter"],
            responsibilities=["ship monthly releases", "crash rate down"],
        ),
        _jd(
            10,
            title="运维开发工程师",
            company="谷风",
            skills=["Go", "Linux", "Docker"],
            nice=["eBPF"],
            responsibilities=["工具平台开发", "发布系统建设"],
        ),
    ]:
        rows.append(
            _row(
                kind="jd",
                id=jd["id"],
                language="en" if any(c.isascii() and c.isalpha() for c in jd["gold"]["title"]) else "zh",
                cohort="jd",
                raw_text=jd["raw_text"],
                gold=jd["gold"],
                required_fields=["required_skills"],
                label_source="profile→render：gold 在前、文本在后，不经被测系统",
            )
        )
    return rows


def validate(rows: list[dict]) -> list[str]:
    """数据集自身的形状锁。跑在 CI 里，语料漂了当场红。"""
    bad: list[str] = []
    resumes = [r for r in rows if r["kind"] == "resume"]
    jds = [r for r in rows if r["kind"] == "jd"]
    if len(resumes) < MIN_RESUME_SAMPLES:
        bad.append(f"简历样本 {len(resumes)} < {MIN_RESUME_SAMPLES}")
    if len(jds) < MIN_JD_SAMPLES:
        bad.append(f"JD 样本 {len(jds)} < {MIN_JD_SAMPLES}")
    long_rows = [r for r in resumes if len(r["raw_text"]) > LONG_THRESHOLD]
    if len(long_rows) < MIN_LONG_SAMPLES:
        bad.append(f">15000 长简历 {len(long_rows)} < {MIN_LONG_SAMPLES}，量不到截断修复")
    if {r["language"] for r in rows} != {"zh", "en"}:
        bad.append("语言覆盖必须同时有 zh 与 en")
    if {r["cohort"] for r in resumes} < {"fresh", "experienced", "switcher"}:
        bad.append("应届/社招/转行三档没齐")
    seen = set()
    for r in rows:
        if r["id"] in seen:
            bad.append(f"id 重复：{r['id']}")
        seen.add(r["id"])
        if not r["raw_text"].strip():
            bad.append(f"{r['id']} 原文是空的")
        for f in r.get("required_fields", []):
            if not r["gold"].get(f):
                bad.append(f"{r['id']} 的必填 gold 字段 {f} 是空的")
        if r["kind"] == "resume" and r["cohort"] != "fresh" and not r["gold"].get("phone"):
            bad.append(f"{r['id']} 没有电话，客观字段召回测不了")
        if r.get("tail_line") and r["tail_line"] not in r["raw_text"]:
            bad.append(f"{r['id']} 声明了段尾 needle，但原文里没有它——这条样本测不了『保尾』")
    # 长样本的**数据级自检**：这条样本存在的意义就是"超预算之后，段尾那份最新工作还在不在"。
    # 没这条的话，第一版那种"一栏灌 18k 字、整段被正确丢掉"的假样本能一路混进评测。
    from app.utils.text_budget import fit_structured_text

    for r in rows:
        if r["kind"] == "resume" and r.get("long_tail"):
            fitted = fit_structured_text(r["raw_text"], LONG_THRESHOLD)
            if r.get("tail_line") not in fitted.text:
                bad.append(
                    f"{r['id']} 长样本裁剪后段尾丢了 gold 的关键内容（丢了 {fitted.dropped_sections}）："
                    "样本不真实，或优先级表与『留段尾』的承诺不符"
                )
            if not fitted.truncated:
                bad.append(f"{r['id']} 号称长样本，却没超预算（{len(r['raw_text'])} 字符），量不到截断")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="只比对现有文件，不写盘")
    args = ap.parse_args()

    rows = build_rows()
    bad = validate(rows)
    if bad:
        print("[FAIL] 数据集形状不合格：")
        for line in bad:
            print("  -", line)
        return 3

    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current.strip() != payload.strip():
            print(f"[FAIL] {OUT} 与生成器输出不一致——要么改语料要么改生成器，别只改一边")
            return 3
        print(f"[ok] {OUT} 与生成器一致（{len(rows)} 条）")
        return 0

    OUT.write_text(payload, encoding="utf-8", newline="\n")
    resumes = sum(1 for r in rows if r["kind"] == "resume")
    jds = sum(1 for r in rows if r["kind"] == "jd")
    reals = [r for r in rows if r["kind"] == "real"]
    longs = sum(1 for r in rows if r["kind"] == "resume" and len(r["raw_text"]) > LONG_THRESHOLD)
    print(
        f"已写 {OUT}：合成简历 {resumes} 份（其中 >15000 长简历 {longs} 份）"
        f"+ JD {jds} 份 + 真文本臂 {len(reals)} 份"
    )
    # 真臂的诚实标注：库里这几份其实是同一个人在不同排版下的版本，别把 4 读成 4 个人。
    people = {r["gold"].get("name") for r in reals if r["gold"].get("name")}
    print(f"  真文本臂覆盖的是 {len(people)} 个人（{len(reals)} 份不同排版），不是 {len(reals)} 个人")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
