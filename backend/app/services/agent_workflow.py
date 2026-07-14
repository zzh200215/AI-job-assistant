"""Deprecated compatibility wrapper for the old step-by-step workflow API."""

import warnings

from app.orchestration.strategies import StepByStepStrategy
from app.services.orchestration_runner import run_strategy_async

# Backward-compatible exports for legacy imports.
STEP_REGISTRY = StepByStepStrategy.STEP_REGISTRY


def run_workflow(resume_id: int, jd_id: int, user_id: int = None) -> int:
    """Start the legacy workflow by delegating to the shared step-by-step runner."""
    warnings.warn(
        "run_workflow 已废弃，请使用 run_smart_analysis → smart_orchestrator",
        DeprecationWarning,
        stacklevel=2,
    )
    return run_strategy_async("step_by_step", resume_id, jd_id, user_id=user_id)
