-- 用户认证相关表结构

-- 1. 用户表
CREATE TABLE IF NOT EXISTS `tb_user` (
    `id`         BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
    `username`   VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    `password`   VARCHAR(255) NOT NULL COMMENT '密码(bcrypt加密存储)',
    `email`      VARCHAR(100) UNIQUE COMMENT '邮箱',
    `role`       VARCHAR(20) NOT NULL DEFAULT 'candidate' COMMENT '用户身份: candidate/recruiter',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';
