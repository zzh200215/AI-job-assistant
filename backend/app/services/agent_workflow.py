"""Deprecated compatibility wrapper for the old workflow API (`/api/agent/start`).

它过去启动的是 `step_by_step` 编排——11 个绕过 agent 类的裸步骤，与前两条流水线
重复，而且是 `RetrievalLog`/`SelfCheckLog` 唯一的（空）写入点。该策略已随阶段 C4
删除，这里改为按当前配置的编排策略启动，与 `run_smart_analysis` 走同一条路。
"""

import warnings

from app.services.analysis_service import run_smart_analysis


def run_workflow(resume_id: int, jd_id: int, user_id: int = None) -> int:
    """按配置策略启动一次分析；返回值仍是 agent_task.id。"""
    warnings.warn(
        "run_workflow 已废弃，请直接使用 run_smart_analysis → smart_orchestrator",
        DeprecationWarning,
        stacklevel=2,
    )
    return run_smart_analysis(resume_id, jd_id, user_id=user_id)
