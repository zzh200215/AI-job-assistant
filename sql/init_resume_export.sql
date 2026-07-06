-- ============================================================
-- 简历智能生成与导出  MySQL 8.0+
-- ============================================================

USE llmXM;

-- 1) tb_resume 增加优化版字段
ALTER TABLE tb_resume
  ADD COLUMN optimized_content TEXT   COMMENT '优化版简历内容(Markdown)',
  ADD COLUMN optimized_at    DATETIME COMMENT '优化时间';

-- 2) 简历版本表
DROP TABLE IF EXISTS resume_version;
CREATE TABLE resume_version (
    id              BIGINT AUTO_INCREMENT      COMMENT '主键ID',
    resume_id       BIGINT NOT NULL            COMMENT '关联简历ID',
    version_type    VARCHAR(20) NOT NULL       COMMENT '版本类型: original/optimized',
    content         TEXT NOT NULL              COMMENT '简历内容(Markdown)',
    format          VARCHAR(10) DEFAULT 'md'   COMMENT '格式: md/json/txt',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    PRIMARY KEY (id),
    KEY idx_rv_resume (resume_id),
    KEY idx_rv_type (version_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='简历版本表';
