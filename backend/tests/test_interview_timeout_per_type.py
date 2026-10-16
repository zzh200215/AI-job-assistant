"""P1.2 面试超时按题型可配的**护栏**（`简历与面试优化.md` §4 P1.2 测试护栏那两条）。

同 D238 那一族护栏的做法：先于功能代码写，钉的是"改完之后必须长成什么样"。它对应文档两条：

1. 各题型超时值从配置读取的断言，**含未配置时回落内置默认的对照**
   → `TestBuiltInDefaults` 与 `TestTwoLevelFallback` 两族（配置读到什么 / 没配到什么）；
2. WS 消息 metadata 字段契约测试（协议文档同步更新）
   → `TestMessageContract`（两处发射点都得盖章）＋ `TestTimeoutArm`（守卫读的是这一题的预算，不是类常量）
   ＋ `test_protocol_doc_documents_the_field`（`docs/面试消息协议.md` 里必须有这个字段）。

**立案当天量到的两件事，直接改变了修法**（都写进了断言，不是注释）：
- 文档那行写"按 category 平台配置 basic/tech/scenario/project"，但 `category` 这个字段**同时装两种域**：
  starter 那条路塞的是 `_map_category()` 出来的**中文标签**（技术基础 / 场景应对…），
  而既有夹具与模型生成的题塞的是**英文题型键**（tech / project）。
  照字面用 `category` 当查表键，四种题型里会有整族永远查不中、静默走默认——
  所以键必须是解析出来的 `type`，`resolve_question_type` 那条就是替这件事站岗的。
- `TIMEOUT_SECONDS = 30` 的消费者只有一处（`interview_ws.py:195` 那个 `asyncio.sleep`），
  但前端 `stores/interview.js:15` 的 `ROUND_SECONDS = 30` 有**四个**消费者：三处重置、一个进度条分母，
  外加两处 `<= 10` 的红色门槛与占位文案。所以预算必须随消息一起下发，前端不许自己再抄一个 30。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.interview_config import InterviewQuestionBank
from app.services.interview_engine import InterviewEngine

BACKEND = Path(__file__).resolve().parents[1]
PROTOCOL_DOC = BACKEND.parent / "docs" / "面试消息协议.md"


@pytest.fixture
def mixed_questions() -> list[dict]:
    """三道**不同题型**的题：project / basic / scenario → 120 / 45 / 90。
    故意不用 `test_interview_engine.py` 那份（三道里两道都是 tech，预算同为 120），
    那样"整场取第一个数"这种错法照样能过。
    题型写在 `category` 里是照既有夹具的形状——那正是这族数据今天的真实长相。
    """
    return [
        {"id": 0, "question": "讲一个你主导的项目", "category": "project", "ref_answer": "", "intent": ""},
        {"id": 1, "question": "介绍一下你自己", "category": "basic", "ref_answer": "", "intent": ""},
        {"id": 2, "question": "线上事故怎么处置", "category": "scenario", "ref_answer": "", "intent": ""},
    ]


@pytest.fixture
def engine(db_session, make_interview_session, mixed_questions):
    """自建一份 engine（与 `test_interview_engine.py` 同形状，但题是三道不同题型的）。"""
    session_id = make_interview_session(status="created", questions=mixed_questions)
    eng = InterviewEngine(session_id)
    eng.db = db_session  # 复用测试会话，别让它去开 SessionLocal 连真库
    from app.models.interview_session import InterviewSession

    eng.session = db_session.get(InterviewSession, session_id)
    return eng


@pytest.fixture
def bank_row(db_session):
    """插一行平台级题库配置（`tenant_id IS NULL` 就是 T3-2 的"平台那一档"）。"""

    def _make(qtype: str, timeout=None, *, tenant_id=None, active=1) -> InterviewQuestionBank:
        row = InterviewQuestionBank(
            type=qtype,
            title=f"{qtype} 平台配置",
            timeout_seconds=timeout,
            tenant_id=tenant_id,
            is_active=active,
        )
        db_session.add(row)
        db_session.commit()
        return row

    return _make


# ---------- 内置默认那一档 ----------


class TestBuiltInDefaults:
    def test_the_four_documented_types_have_the_documented_budgets(self):
        """四个键与四个秒数是文档 §4 P1.2 那张表，逐字钉住——改任何一个数都要同时改文档。"""
        from app.services.interview_config_service import QUESTION_TIMEOUT_SECONDS

        assert QUESTION_TIMEOUT_SECONDS == {"basic": 45, "tech": 120, "scenario": 90, "project": 120}

    def test_unrecognised_type_gets_the_floor_not_the_old_thirty(self):
        """认不出题型时给的是**下限 45**，不是原来那个 30。
        理由：30 就是"系统设计题没法答"那条硬伤的根因，不该继续发给任何认不出的题。
        """
        from app.services.interview_config_service import TIMEOUT_FLOOR_SECONDS, timeout_for_type

        assert TIMEOUT_FLOOR_SECONDS == 45
        assert timeout_for_type(None, "general") == 45
        assert timeout_for_type(None, "stress") == 45
        assert timeout_for_type(None, "") == 45

    def test_the_hard_coded_thirty_is_gone_from_the_class(self):
        """类常量必须出树：留着它，任何一处 `InterviewEngine.TIMEOUT_SECONDS` 都能悄悄把修复退回去。"""
        assert not hasattr(InterviewEngine, "TIMEOUT_SECONDS")
        assert hasattr(InterviewEngine, "MAX_TIMEOUTS"), "只该摘掉超时那个，次数上限与本条无关"


# ---------- 两级回落：平台配置 → 内置默认（复刻 T3-2 scoring_rules 的形状）----------


class TestTwoLevelFallback:
    def test_without_any_row_the_built_in_default_wins(self, db_session):
        """本库两张配置表实测都是 0 行——所以这一档才是今天真实在跑的那条路，必须有对照。"""
        from app.services.interview_config_service import timeout_for_type

        assert db_session.query(InterviewQuestionBank).count() == 0
        assert timeout_for_type(db_session, "tech") == 120

    def test_a_platform_row_overrides_the_built_in(self, db_session, bank_row):
        from app.services.interview_config_service import timeout_for_type

        bank_row("tech", 200)
        assert timeout_for_type(db_session, "tech") == 200
        # 没配的那些题型仍走内置默认，不是被整表覆盖成空
        assert timeout_for_type(db_session, "scenario") == 90

    def test_a_row_without_the_column_falls_back_per_type(self, db_session, bank_row):
        """配置行为这个题型存在、但没填超时——回落**该题型的内置默认**，不是全局下限。"""
        from app.services.interview_config_service import timeout_for_type

        bank_row("project", None)
        assert timeout_for_type(db_session, "project") == 120

    def test_inactive_rows_do_not_count(self, db_session, bank_row):
        from app.services.interview_config_service import timeout_for_type

        bank_row("tech", 200, active=0)
        assert timeout_for_type(db_session, "tech") == 120

    def test_tenant_rows_are_not_read_as_platform_defaults(self, db_session, bank_row):
        """`tenant_id IS NULL` 才是平台那一档。租户行不能污染没登录态/其它租户的取值。"""
        from app.services.interview_config_service import timeout_for_type

        bank_row("tech", 200, tenant_id=77)
        assert timeout_for_type(db_session, "tech") == 120


# ---------- 题型解析：那个字段装着两种域 ----------


class TestQuestionTypeResolution:
    """`category` 一词两域（中文标签 / 英文键），`type` 才是稳定键。解析必须只看 `type` 与能回推的标签。"""

    def test_type_field_wins_and_a_chinese_label_maps_back(self):
        from app.services.interview_engine import resolve_question_type

        assert resolve_question_type({"type": "tech", "category": "技术基础"}) == "tech"
        assert resolve_question_type({"category": "场景应对"}) == "scenario"
        assert resolve_question_type({"category": "通用/HR"}) == "basic"

    def test_english_value_arriving_via_category_is_kept(self):
        """既有夹具与模型生成的题把英文题型写在 category 里（`sample_questions` 就是这么写的），
        这一族不能掉进"未知"，否则它们全部拿 45 秒而不是各自题型的预算。
        """
        from app.services.interview_engine import resolve_question_type

        assert resolve_question_type({"category": "tech"}) == "tech"
        assert resolve_question_type({"category": "project"}) == "project"

    def test_no_signal_at_all_is_general(self):
        from app.services.interview_engine import resolve_question_type

        assert resolve_question_type({}) == "general"
        assert resolve_question_type({"category": "面试动机与职业规划"}) == "general"

    def test_the_label_table_is_the_inverse_of_the_renderer(self):
        """`_map_category()` 是标签的唯一出处；回推表必须是它的逆，不许第二份真相。"""
        from app.api.interview_rest import _map_category
        from app.services.interview_engine import QUESTION_TYPE_LABELS

        for qtype, label in QUESTION_TYPE_LABELS.items():
            assert _map_category(qtype) == label, f"{qtype} 的标签与渲染那侧不一致"


# ---------- 消息契约：两处发射点都要盖章 ----------


class TestMessageContract:
    def test_each_question_carries_its_own_type_budget(self, engine):
        """三道题各自 120 / 45 / 90。这一条挡住的是"整场取第一个数"那种错法——
        那在样题预算相同的情况下看不出来，所以夹具特意让三道题的预算互不相同。
        """
        got = [engine.next_question()["metadata"]["timeout_seconds"] for _ in range(3)]
        assert got == [120, 45, 90]

    def test_next_question_stamps_the_budget_in_metadata(self, engine):
        """第一题是 project → 120 秒，且明确不是那个 30。"""
        from app.services.interview_config_service import timeout_for_type

        meta = engine.next_question()["metadata"]
        assert meta["timeout_seconds"] == timeout_for_type(engine.db, "project") == 120
        assert meta["timeout_seconds"] != 30, "还是那个 30，等于没改"

    def test_both_question_emission_sites_stamp_the_field(self):
        """静态腿：引擎里每一处 `"type": "question"` 的 metadata **字典体内**都得有 timeout_seconds。
        行为测试只覆盖 next_question；追问那条发射点靠这条守着——少盖一处，重连/追问时前端
        会静默掉回兜底值，两边都不报错。

        取的是花括号配对后的字典体，不是"往后数 N 个字符"：第一版我用 `metadata[^\\n]*`，
        它只截到 `"metadata": {` 这一行，于是这条护栏判的其实是"我的正则没看到"，
        把仪器坏误报成代码坏（同 D152 那条"注入—撤除必须证明源规则还在"是一个毛病）。
        """
        source = (BACKEND / "app/services/interview_engine.py").read_text(encoding="utf-8")
        dicts = _metadata_dicts_after_question_starts(source)
        assert len(dicts) >= 2, f"问题发射点变成 {len(dicts)} 处，这条护栏要重读代码再改"
        for index, body in dicts:
            assert "timeout_seconds" in body, f"第 {index} 处问题消息的 metadata 没盖章"


def _metadata_dicts_after_question_starts(source: str) -> list[tuple[int, str]]:
    """每个 `"type": "question"` 之后第一个 `"metadata": {` 的字典体（配对到闭合的 `}`）。"""
    found: list[tuple[int, str]] = []
    for hit in re.finditer(r'"type": "question"', source):
        start = source.find('"metadata"', hit.end())
        if start == -1 or start - hit.end() > 400:
            continue
        brace = source.find("{", start)
        depth, cursor = 0, brace
        while cursor < len(source):
            if source[cursor] == "{":
                depth += 1
            elif source[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        found.append((len(found) + 1, source[brace : cursor + 1]))
    return found


# ---------- WS：定时器读的是这一题的预算 ----------


class TestTimeoutArm:
    def test_the_ws_no_longer_sleeps_a_class_constant(self):
        source = (BACKEND / "app/api/interview_ws.py").read_text(encoding="utf-8")
        # 只判**可执行的那几行**：这个文件里有一句注释写着 `InterviewEngine.TIMEOUT_SECONDS`
        # 来交代"原来是什么、为什么摘掉"。按全文扫会把那条注释判成违规，于是仪器坏伪装成代码坏
        # ——同一条毛病在 styleDebtRatchet 那族守卫上记过（注释里逐字写被禁形态会把自己钉红）。
        offenders = [
            line.strip()
            for line in source.splitlines()
            if "InterviewEngine.TIMEOUT_SECONDS" in line and not line.strip().startswith("#")
        ]
        assert not offenders, f"还在睡那个常量：{offenders}"
        assert "timeout_for_payload" in source, "arming 没走那个取值函数"

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({"type": "question", "metadata": {"timeout_seconds": 200}}, 200),
            ({"type": "question", "metadata": {}}, 45),  # 老会话落库的题没这字段
            ({"type": "question"}, 45),
            ({"type": "answer"}, None),  # 非题消息不该起定时器
        ],
    )
    def test_timeout_for_payload(self, payload, expected):
        from app.api.interview_ws import timeout_for_payload

        assert timeout_for_payload(payload) == expected

    def test_a_bogus_budget_does_not_bring_the_room_down(self):
        """库里存的值可能是脏的（0、负数、字符串）——兜底到下限，而不是起一个 0 秒的定时器。"""
        from app.api.interview_ws import timeout_for_payload

        assert timeout_for_payload({"type": "question", "metadata": {"timeout_seconds": 0}}) == 45
        assert timeout_for_payload({"type": "question", "metadata": {"timeout_seconds": -5}}) == 45
        assert timeout_for_payload({"type": "question", "metadata": {"timeout_seconds": "abc"}}) == 45


# ---------- 协议文档同步（文档 §4 P1.2 明写"同步更新"）----------


def test_protocol_doc_documents_the_field():
    assert PROTOCOL_DOC.exists(), f"协议文档路径变了：{PROTOCOL_DOC}"
    doc = PROTOCOL_DOC.read_text(encoding="utf-8")
    assert "timeout_seconds" in doc, "docs/面试消息协议.md 没写这个字段：前端照文档实现会漏读"
    assert re.search(
        r"timeout_seconds.{0,240}(45|120|缺省|兜底|默认)", doc, re.S
    ), "文档只列了字段名没给兜底值：老会话没这字段时前端该从哪取数，写清楚"
