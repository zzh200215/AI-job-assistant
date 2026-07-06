-- ============================================================
-- 多智能体协作 初始化脚本  MySQL 8.0+
-- ============================================================

USE llmXM;

-- ------------------------------------------------------------
-- 1) 智能体运行记录表  agent_run
--    一次完整的多智能体分析 = 一条记录
-- ------------------------------------------------------------
DROP TABLE IF EXISTS agent_run;
CREATE TABLE agent_run (
    id              BIGINT AUTO_INCREMENT          COMMENT '运行ID',
    resume_id       BIGINT          NOT NULL       COMMENT '关联简历ID',
    jd_id           BIGINT          NOT NULL       COMMENT '关联JDID',
    -- 智能调度（自然语言需求驱动）
    user_request    TEXT                           COMMENT '用户自然语言需求',
    intent          VARCHAR(50)                    COMMENT '调度识别出的意图',
    selected_agents JSON                           COMMENT '本次实际调用的智能体列表',
    dispatch_reason TEXT                           COMMENT '调度理由',
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending'
        COMMENT '状态: pending/running/completed/failed',
    -- 汇总报告
    summary_report  JSON                           COMMENT 'SummaryAgent 生成的最终汇总报告',
    error_msg       TEXT                           COMMENT '整体失败原因',
    start_time      DATETIME                       COMMENT '开始时间',
    end_time        DATETIME                       COMMENT '结束时间',
    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_ar_status (status),
    KEY idx_ar_create (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='多智能体运行记录表';


-- ------------------------------------------------------------
-- 2) 智能体消息表  agent_message
--    每个智能体的一次执行 = 一条消息
-- ------------------------------------------------------------
DROP TABLE IF EXISTS agent_message;
CREATE TABLE agent_message (
    id              BIGINT AUTO_INCREMENT          COMMENT '消息ID',
    run_id          BIGINT          NOT NULL       COMMENT '关联运行ID',
    agent_name      VARCHAR(50)     NOT NULL       COMMENT '智能体名称: ResumeAgent/JobAgent/MatchAgent/InterviewAgent/CareerAgent/SummaryAgent',
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending'
        COMMENT '状态: pending/running/completed/failed',
    -- 依赖
    depends_on      JSON                           COMMENT '依赖的智能体名称列表',
    -- 输入输出
    input_data      JSON                           COMMENT '该智能体收到的输入',
    output_data     JSON                           COMMENT '该智能体的输出JSON',
    error_msg       TEXT                           COMMENT '执行失败原因',
    -- 耗时
    started_at      DATETIME                       COMMENT '开始时间',
    completed_at    DATETIME                       COMMENT '完成时间',
    duration_ms     INT                            COMMENT '耗时(毫秒)',
    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_am_run (run_id),
    KEY idx_am_agent (agent_name),
    KEY idx_am_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体消息表';


-- ------------------------------------------------------------
-- 3) 智能体结果表  agent_result
--    每个智能体的结构化输出（冗余存储，方便直接查询）
-- ------------------------------------------------------------
DROP TABLE IF EXISTS agent_result;
CREATE TABLE agent_result (
    id              BIGINT AUTO_INCREMENT          COMMENT '结果ID',
    run_id          BIGINT          NOT NULL       COMMENT '关联运行ID',
    message_id      BIGINT                         COMMENT '关联消息ID',
    agent_name      VARCHAR(50)     NOT NULL       COMMENT '智能体名称',
    result_type     VARCHAR(50)     NOT NULL       COMMENT '结果类型: resume_report/job_report/match_report/interview_report/career_report/summary_report',
    result_json     JSON            NOT NULL       COMMENT '结构化结果',
    summary         VARCHAR(500)                   COMMENT '结果一句话摘要',
    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_ar_run (run_id),
    KEY idx_ar_agent (agent_name),
    KEY idx_ar_type (result_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体结果表';


-- ============================================================
-- 【可选】已建库升级：若不想 DROP 重建 agent_run（保留历史数据），
-- 单独执行下面 4 条为旧表补上智能调度字段（首次执行；已存在会报错，忽略即可）。
-- 本脚本顶部已是 DROP+CREATE，全新安装无需执行本节。
-- ============================================================
-- ALTER TABLE agent_run ADD COLUMN user_request    TEXT        COMMENT '用户自然语言需求' AFTER jd_id;
-- ALTER TABLE agent_run ADD COLUMN intent          VARCHAR(50) COMMENT '调度识别出的意图' AFTER user_request;
-- ALTER TABLE agent_run ADD COLUMN selected_agents JSON        COMMENT '本次实际调用的智能体列表' AFTER intent;
-- ALTER TABLE agent_run ADD COLUMN dispatch_reason TEXT        COMMENT '调度理由' AFTER selected_agents;
