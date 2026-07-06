# -*- coding: utf-8 -*-
"""Unified entrypoint for async analysis execution."""

from app.core.config import settings
from app.services.orchestration_runner import run_strategy_async


def _resolve_strategy_name() -> str:
    strategy_name = getattr(settings, "ORCHESTRATION_STRATEGY", "linear")
    engine_name = getattr(settings, "ORCHESTRATION_ENGINE", "native")
    langgraph_strategy_map = {
        "linear": "langgraph_linear",
        "layered": "langgraph_layered",
        "step_by_step": "langgraph_step_by_step",
    }

    if engine_name == "langgraph":
        return langgraph_strategy_map.get(strategy_name, strategy_name)
    return strategy_name


def get_configured_strategy_name() -> str:
    return _resolve_strategy_name()


def run_smart_analysis(resume_id: int, jd_id: int, user_id: int = None) -> int:
    """Create an analysis task and execute the configured strategy in background."""
    strategy_name = _resolve_strategy_name()
    return run_strategy_async(strategy_name, resume_id, jd_id, user_id=user_id)
