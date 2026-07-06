-- ============================================================
-- Agentic RAG 工作流 初始化脚本  MySQL 8.0+
-- ============================================================

USE llmXM;

-- ------------------------------------------------------------
-- 1) Agent 任务表  agent_task
--    一次完整的 Agent 分析 = 一条记录
-- ------------------------------------------------------------
DROP TABLE IF EXISTS agent_task;
CREATE TABLE agent_task (
    id              BIGINT AUTO_INCREMENT          COMMENT '任务ID',
    -- 关联的简历和 JD
    resume_id       BIGINT          NOT NULL       COMMENT '关联简历ID',
    jd_id           BIGINT          NOT NULL       COMMENT '关联JDID',
    -- 意图识别结果
    intent          VARCHAR(100)                   COMMENT '用户意图: resume_match / optimize / interview / full_analysis',
    intent_detail   JSON                           COMMENT '意图识别详情',
    -- 任务规划结果
    plan            JSON                           COMMENT 'AI拆解的任务列表 [{step_name, description}]',
    -- 最终报告
    final_report    JSON                           COMMENT '汇总后的最终报告',
    -- 状态
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending'
        COMMENT '状态: pending / running / completed / failed',
    error_msg       TEXT                           COMMENT '失败原因',
    -- 时间
    start_time      DATETIME                       COMMENT '开始时间',
    end_time        DATETIME                       COMMENT '结束时间',
    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    PRIMARY KEY (id),
    KEY idx_agent_task_status (status),
    KEY idx_agent_task_create (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 任务表';


-- ------------------------------------------------------------
-- 2) Agent 步骤日志表  agent_step_log
--    每一步的执行记录
-- ------------------------------------------------------------
DROP TABLE IF EXISTS agent_step_log;
CREATE TABLE agent_step_log (
    id              BIGINT AUTO_INCREMENT          COMMENT '日志ID',
    task_id         BIGINT          NOT NULL       COMMENT '关联任务ID',
    step_name       VARCHAR(100)    NOT NULL       COMMENT '步骤名称: intent_recognition / resume_parse / jd_parse / task_planning / knowledge_retrieval / matching_analysis / resume_optimization / interview_generation / self_check / final_report',
    step_index      INT             NOT NULL       COMMENT '步骤序号(从1开始)',
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending'
        COMMENT '步骤状态: pending / running / completed / failed',
    -- 输入输出
    input_data      JSON                           COMMENT '步骤输入',
    output_data     JSON                           COMMENT '步骤输出',
    -- 耗时
    started_at      DATETIME                       COMMENT '步骤开始时间',
    completed_at    DATETIME                       COMMENT '步骤完成时间',
    duration_ms     INT                            COMMENT '耗时(毫秒)',
    -- 错误
    error_msg       TEXT                           COMMENT '步骤失败原因',
    retry_count     INT             DEFAULT 0      COMMENT '重试次数',
    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_step_task (task_id),
    KEY idx_step_name (step_name),
    KEY idx_step_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 步骤日志表';


-- ------------------------------------------------------------
-- 3) 知识检索日志表  retrieval_log
--    记录每次知识库检索的详细信息
-- ------------------------------------------------------------
DROP TABLE IF EXISTS retrieval_log;
CREATE TABLE retrieval_log (
    id              BIGINT AUTO_INCREMENT          COMMENT '日志ID',
    task_id         BIGINT          NOT NULL       COMMENT '关联任务ID',
    step_log_id     BIGINT                         COMMENT '关联步骤日志ID',
    query_text      TEXT            NOT NULL       COMMENT '检索查询文本',
    doc_type_filter VARCHAR(50)                    COMMENT '文档类型过滤',
    top_k           INT             DEFAULT 5      COMMENT '返回数量',
    result_count    INT             DEFAULT 0      COMMENT '实际返回数量',
    results         JSON                           COMMENT '检索结果 [{doc_title, doc_type, chunk_text, score}]',
    duration_ms     INT                            COMMENT '检索耗时(毫秒)',
    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_retrieval_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识检索日志表';


-- ------------------------------------------------------------
-- 4) 自我校验日志表  self_check_log
--    记录 AI 自我校验的结果
-- ------------------------------------------------------------
DROP TABLE IF EXISTS self_check_log;
CREATE TABLE self_check_log (
    id              BIGINT AUTO_INCREMENT          COMMENT '日志ID',
    task_id         BIGINT          NOT NULL       COMMENT '关联任务ID',
    check_target    VARCHAR(100)    NOT NULL       COMMENT '校验对象: matching_analysis / resume_optimization / interview_generation / full_report',
    passed          TINYINT         DEFAULT 0      COMMENT '是否通过: 0-未通过 1-通过',
    score           INT                            COMMENT '质量评分(0-100)',
    issues          JSON                           COMMENT '发现的问题列表 [{severity, description, suggestion}]',
    improvement     JSON                           COMMENT '改进建议',
    retry_needed    TINYINT         DEFAULT 0      COMMENT '是否需要重试',
    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_check_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自我校验日志表';
