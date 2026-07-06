-- ============================================================
-- 知识库模块 初始化脚本  MySQL 8.0+
-- ============================================================

USE llmXM;

-- ------------------------------------------------------------
-- 知识库文档表  kb_document
-- 记录上传的知识库文件及其处理状态
-- ------------------------------------------------------------
DROP TABLE IF EXISTS kb_document;
CREATE TABLE kb_document (
    id              BIGINT          AUTO_INCREMENT      COMMENT '主键ID',
    title           VARCHAR(255)    NOT NULL            COMMENT '文档标题（用户填写）',
    file_name       VARCHAR(255)    NOT NULL            COMMENT '原始文件名',
    file_type       VARCHAR(20)     NOT NULL            COMMENT '文件类型: txt/md/pdf/docx',
    file_size       BIGINT                              COMMENT '文件大小(字节)',
    file_path       VARCHAR(500)    NOT NULL            COMMENT '文件存储相对路径',

    -- 文档分类，便于检索时按类型过滤
    doc_type        VARCHAR(50)     NOT NULL DEFAULT 'general'
        COMMENT '文档类型: resume_template(优秀简历模板) / jd_lib(岗位描述) / interview_q(面试题库) / skill_model(能力模型) / industry_report(行业报告) / general(通用)',

    -- 处理状态
    chunk_count     INT             DEFAULT 0           COMMENT '切片数量',
    status          VARCHAR(20)     NOT NULL DEFAULT 'processing'
        COMMENT '状态: processing(处理中) / ready(就绪) / failed(失败)',
    error_msg       TEXT                                COMMENT '处理失败原因',

    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time     DATETIME        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    PRIMARY KEY (id),
    KEY idx_kb_doc_type (doc_type),
    KEY idx_kb_status (status),
    KEY idx_kb_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库文档表';
