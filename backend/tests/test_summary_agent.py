"""SummaryAgent 的展示摘要要同时吃得下 dict 与字符串。

真 provider 按 prompt 返回 `summary` 对象；mock/降级路径返回的是
`{"summary": "一句中文", "match_score": 82}`。后者曾经让整条编排在最后一步
以 `'str' object has no attribute 'get'` 失败。
"""

from app.agents.summary_agent import SummaryAgent


def test_make_summary_accepts_dict_payload():
    text = SummaryAgent()._make_summary({"summary": {"match_score": 82, "recommendation": "推荐"}})
    assert text == "汇总报告: 综合匹配 82/100 | 推荐"


def test_make_summary_accepts_string_payload_from_mock():
    text = SummaryAgent()._make_summary({"summary": "技术栈高度匹配，建议推进面试", "match_score": 82})
    assert "82/100" in text
    assert "技术栈高度匹配" in text


def test_make_summary_tolerates_missing_summary():
    assert SummaryAgent()._make_summary({}) == "汇总报告: 综合匹配 0/100 | "
