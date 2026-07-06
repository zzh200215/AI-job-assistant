-- ============================================================
-- 岗位推荐功能 — 数据库变更 SQL
-- ============================================================

-- 1) tb_jd 表新增字段（若已存在则跳过）
ALTER TABLE `tb_jd`
  ADD COLUMN `source`    VARCHAR(20) NOT NULL DEFAULT 'manual' COMMENT '来源: manual/imported/api' AFTER `parsed_json`,
  ADD COLUMN `industry`  VARCHAR(100)          DEFAULT NULL     COMMENT '所属行业' AFTER `source`,
  ADD COLUMN `is_active` INT         NOT NULL DEFAULT 1         COMMENT '是否活跃: 0-下架 1-上架' AFTER `industry`;

-- 2) 推荐反馈表
CREATE TABLE IF NOT EXISTS `job_recommend_feedback` (
    `id`            BIGINT      NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `user_id`       BIGINT      NOT NULL                 COMMENT '用户ID',
    `resume_id`     BIGINT      NOT NULL                 COMMENT '简历ID',
    `jd_id`         BIGINT      NOT NULL                 COMMENT '岗位JD ID',
    `feedback_type` VARCHAR(10) NOT NULL                 COMMENT '反馈类型: like/dislike',
    `match_score`   FLOAT       NULL                     COMMENT '推荐时的匹配分数',
    `created_at`    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    INDEX `idx_user_id`   (`user_id`),
    INDEX `idx_resume_id` (`resume_id`),
    INDEX `idx_jd_id`     (`jd_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位推荐用户反馈表';
