-- 动态岗位数据源模块表初始化脚本
-- 执行: mysql -u root -p your_db < init_datasource_tables.sql

CREATE TABLE IF NOT EXISTS job_data_source (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT DEFAULT NULL COMMENT '所属用户',
    name VARCHAR(100) NOT NULL COMMENT '数据源名称',
    source_type VARCHAR(20) NOT NULL COMMENT '类型: csv/json/api/mock',
    config JSON DEFAULT '{}' COMMENT '连接配置(JSON)',
    status TINYINT DEFAULT 1 COMMENT '状态: 0-禁用 1-启用',
    last_sync_at DATETIME DEFAULT NULL COMMENT '上次同步时间',
    last_sync_log_id BIGINT DEFAULT NULL COMMENT '上次同步日志ID',
    sync_interval INT DEFAULT 0 COMMENT '自动同步间隔(分钟), 0=手动',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_source_type (source_type),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='岗位数据源配置表';

CREATE TABLE IF NOT EXISTS job_sync_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT NOT NULL COMMENT '数据源ID',
    user_id BIGINT DEFAULT NULL,
    status VARCHAR(20) DEFAULT 'running' COMMENT '状态: running/success/failed/partial',
    total_count INT DEFAULT 0 COMMENT '读取总数',
    success_count INT DEFAULT 0 COMMENT '成功写入数',
    fail_count INT DEFAULT 0 COMMENT '失败数',
    duplicate_count INT DEFAULT 0 COMMENT '去重跳过数',
    embed_count INT DEFAULT 0 COMMENT '生成向量数',
    duration_ms INT DEFAULT 0 COMMENT '耗时(毫秒)',
    error_msg TEXT DEFAULT NULL COMMENT '错误信息',
    detail JSON DEFAULT '[]' COMMENT '明细错误列表',
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME DEFAULT NULL,
    INDEX idx_source_id (source_id),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='同步日志表';

CREATE TABLE IF NOT EXISTS job_import_batch (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT NOT NULL COMMENT '数据源ID',
    sync_log_id BIGINT NOT NULL COMMENT '同步日志ID',
    user_id BIGINT DEFAULT NULL,
    external_id VARCHAR(100) DEFAULT NULL COMMENT '外部唯一标识',
    title VARCHAR(200) NOT NULL,
    company VARCHAR(200) DEFAULT NULL,
    location VARCHAR(100) DEFAULT NULL,
    jd_id BIGINT DEFAULT NULL COMMENT '关联 tb_jd.id',
    status VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/success/failed',
    error_msg TEXT DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_source_id (source_id),
    INDEX idx_sync_log_id (sync_log_id),
    INDEX idx_external_id (external_id),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='导入批次记录表';
