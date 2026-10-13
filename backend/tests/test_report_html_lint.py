"""报告机检的守卫（`app/services/report_html_lint.py`）。

一条"合格报告能过"用的是**人工确认过的那份成品**——这一条同时也在验我反推出来的规则：
如果机检和成品互相矛盾，红的是机检，不是成品。
其余每条变异只应红它自己的那一项，所以断言写成"这一发产生的 code 集合 == 期望集合"。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.report_html_lint import lint_report_html

FIXTURE = Path(__file__).parent / "fixtures" / "report_sample_good.html"


@pytest.fixture(scope="module")
def good_report() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def codes(html: str) -> set[str]:
    return {issue.code for issue in lint_report_html(html)}


def _once(html: str, old: str, new: str) -> str:
    assert html.count(old) >= 1, f"夹具里找不到 {old!r}，这条变异测的是空气"
    return html.replace(old, new, 1)


def test_an_accepted_report_passes_every_check(good_report):
    assert codes(good_report) == set(), [str(i) for i in lint_report_html(good_report)]


def test_comments_are_not_the_report(good_report):
    """成品顶部那段注释就是写作规范原文，里面逐字写着"门禁""可面试水位"和三个示例值。
    不剥注释的话，一份完全合格的报告会因为带着规范原文而被判不合格。"""
    assert "门禁" in good_report and "可面试水位" in good_report
    assert codes(good_report) == set()


def test_the_candidates_own_quoted_words_are_exempt(good_report):
    """机制字眼那道扫描管的是报告自己的话。被引用进批改稿的候选人原文不算——
    "人工兜底"是他简历里的用词，真要收拾的是他的用词，不是把机检改成会误报的样子。"""
    mutated = _once(good_report, "<h3>基本信息</h3>", "<h3>基本信息</h3><p>高风险任务人工兜底。</p>")

    assert codes(mutated) == set()


@pytest.mark.parametrize(
    "old,new,expected",
    [
        # 导航少一项 / 文案与 §1 点名的不一致
        ('<a href="#m-summary">小结</a>', "", {"navigation"}),
        ('<a href="#m-summary">小结</a>', '<a href="#m-summary">总结</a>', {"navigation"}),
        # 导航指向的锚点在页面上不存在
        ('<section class="card" id="m-fit">', '<section class="card" id="m-compare">', {"navigation", "module-order"}),
        # 省略写法
        ('<span class="mk">1</span>', '<span class="mk">1</span>其余项目照此处理。', {"ellipsis"}),
        # 内部机制字眼进了报告自己的话
        ('<span class="mk">3</span>', '<span class="mk">3</span>这一档是硬条件。', {"mechanism-word"}),
        # 没替换干净的示例值
        ("报告生成日期：2026-09-12", "报告生成日期：2026-09-12 · 李明", {"unreplaced-sample"}),
        # 引用外部资源
        (
            "</head>",
            '<link rel="stylesheet" href="https://cdn.example.com/a.css"></head>',
            {"external-resource"},
        ),
        # 合计行与逐维相加不是同一个数
        ('<td>合计</td><td class="n">84</td>', '<td>合计</td><td class="n">85</td>', {"total-authority"}),
        # 追问类型飘出词表
        ("（预期指标）", "（薪资谈判）", {"followup-kind"}),
    ],
)
def test_one_mutation_one_verdict(good_report, old, new, expected):
    assert codes(_once(good_report, old, new)) == expected


def test_a_quoted_resume_sentence_outside_the_paper_is_also_exempt(good_report):
    """报告在别处引用候选人的原话（第五节那两处填空）走同一个豁免，靠 `quoted-resume` 标记。
    不豁免的话，候选人自己写过"人工兜底"的人永远拿不到报告——那是机检在逼人改简历。"""
    with_quote = _once(
        good_report,
        "</main>",
        '<div class="boss-blk"><p class="muted quoted-resume">高风险任务人工兜底。</p></div>\n</main>',
    )

    assert codes(with_quote) == set()


def test_the_same_word_in_the_reports_own_voice_still_fires(good_report):
    """反向那一条：豁免是按标记给的，不是按"兜底"这个词一律放过。"""
    outside = _once(good_report, "</main>", "<p>这一档是硬条件，人工兜底由系统判定。</p>\n</main>")

    assert codes(outside) == {"mechanism-word"}


def test_an_empty_module_is_caught(good_report):
    """模块整块是空的：导航与顺序都对，但那一段没有内容，候选人点开只看到一张白卡。"""
    mutated = re.sub(
        r'(<section class="card" id="m-summary">).*?(</section>)',
        r"\1\n    <p>短</p>\n  \2",
        good_report,
        count=1,
        flags=re.S,
    )

    assert codes(mutated) == {"empty-module"}


def test_a_mark_without_its_annotation_is_caught(good_report):
    """编号与批注必须一一对应：正文有 14 号、右栏没有那条，候选人就看不到为什么改。"""
    mutated = _once(good_report, '<div class="note key"><span class="mk">14</span>', '<div class="note key">')

    assert codes(mutated) == {"redline-numbering"}


def test_an_annotation_without_a_mark_is_caught(good_report):
    mutated = _once(
        good_report,
        '<div class="note"><span class="mk">15</span>',
        '<div class="note"><span class="mk">23</span>凭空多出来的批注<span class="mk">15</span>',
    )

    assert codes(mutated) == {"redline-numbering"}


def test_the_declared_change_count_must_match_the_body(good_report):
    """声明 22 处、正文实际 21 处：候选人按声明去数，会发现少一处。"""
    mutated = _once(good_report, '<sup class="mk key">14</sup>', "")

    assert codes(mutated) == {"redline-numbering", "redline-count"}


def test_a_report_claiming_no_changes_must_not_carry_marks(good_report):
    mutated = _once(
        good_report,
        '<span class="rvstat">共 <b>22</b> 处改动，其中 <b>5</b> 处是关键项（改完并补齐【待补】数据就能投）</span>',
        '<span class="rvstat">这一版可以原样用，无需改动</span>',
    )

    assert codes(mutated) == {"redline-count"}
