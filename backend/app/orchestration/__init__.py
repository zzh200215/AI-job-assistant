# -*- coding: utf-8 -*-
"""智能体编排层

统一三套并行编排器（线性 / 分层并行 / 细粒度步骤），
通过 orchestration.registry 共用同一个 Agent 注册表，
通过 orchestration.strategies 切换 ExecutionStrategy。

用法:
    from app.orchestration.registry import DEFAULT_REGISTRY
    from app.orchestration.strategies import LinearStrategy

    strategy = LinearStrategy(DEFAULT_REGISTRY)
    result = strategy.run(task_id, resume_id, jd_id, user_id, db)
"""
