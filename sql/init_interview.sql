-- ============================================================
-- AI 模拟面试 — 数据库表初始化 SQL
-- ============================================================

-- 面试会话表
CREATE TABLE IF NOT EXISTS `interview_session` (
    `id`              BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `user_id`         BIGINT          NOT NULL                 COMMENT '用户ID，关联 tb_user.id',
    `resume_id`       BIGINT          NULL                     COMMENT '简历ID，关联 tb_resume.id',
    `jd_id`           BIGINT          NULL                     COMMENT '岗位JD ID，关联 tb_jd.id',
    `interview_type`  VARCHAR(20)     NOT NULL DEFAULT 'tech'  COMMENT '面试类型: tech/hr/comprehensive',
    `status`          VARCHAR(20)     NOT NULL DEFAULT 'created' COMMENT '状态: created/ongoing/completed',
    `questions`       JSON            NULL                     COMMENT '面试题列表(有序数组)',
    `messages`        JSON            NULL                     COMMENT '消息记录(完整对话)',
    `evaluation`      JSON            NULL                     COMMENT '评估结果(最终报告)',
    `total_questions` INT             NOT NULL DEFAULT 0       COMMENT '总题数',
    `answered_count`  INT             NOT NULL DEFAULT 0       COMMENT '已回答题数',
    `timeout_count`   INT             NOT NULL DEFAULT 0       COMMENT '超时次数',
    `created_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `completed_at`    DATETIME        NULL                     COMMENT '完成时间',
    PRIMARY KEY (`id`),
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_status`  (`status`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI模拟面试会话表';
