# -*- coding: utf-8 -*-
from app.agents.tools import get_tool, tool_names
from app.agents.match_analysis_agent import MatchAnalysisAgent


def test_dangerous_get_document_tool_is_not_registered():
    assert get_tool("get_document") is None
    assert "get_document" not in tool_names()


def test_match_analysis_agent_only_uses_safe_tools():
    assert MatchAnalysisAgent._TOOL_NAMES == ["search_knowledge", "calc_skill_coverage"]
