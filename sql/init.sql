-- ============================================================
-- 基于 Agentic RAG 与多智能体协作的智能招聘与职业规划平台
-- 数据库初始化脚本  MySQL 8.0+
-- 字符集：utf8mb4  支持 emoji 与全字符
-- ============================================================

-- 1) 创建数据库
CREATE DATABASE IF NOT EXISTS llmXM
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE llmXM;

-- ------------------------------------------------------------
-- 2) 简历表  tb_resume
--    存储：上传文件信息 + 解析后的纯文本 + LLM 结构化结果
-- ------------------------------------------------------------
DROP TABLE IF EXISTS tb_resume;
CREATE TABLE tb_resume (
    id              BIGINT          AUTO_INCREMENT      COMMENT '主键ID',
    file_name       VARCHAR(255)    NOT NULL            COMMENT '原始文件名',
    file_path       VARCHAR(500)    NOT NULL            COMMENT '文件存储相对路径',
    file_type       VARCHAR(20)                         COMMENT '文件类型 pdf / docx',
    file_size       BIGINT                              COMMENT '文件大小（字节）',
    raw_text        MEDIUMTEXT                          COMMENT '从文件提取出的纯文本',

    -- 解析后冗余的关键字段（便于检索 / 列表展示，避免每次解析 JSON）
    parsed_json     JSON                                COMMENT 'LLM 解析后的完整结构化数据',
    name            VARCHAR(100)                        COMMENT '候选人姓名',
    phone           VARCHAR(50)                         COMMENT '联系电话',
    email           VARCHAR(200)                        COMMENT '邮箱',
    years_exp       INT                                 COMMENT '工作年限',

    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP
                                                        COMMENT '创建时间',
    update_time     DATETIME        DEFAULT CURRENT_TIMESTAMP
                                                        ON UPDATE CURRENT_TIMESTAMP
                                                        COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_resume_name (name),
    KEY idx_resume_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='简历表';

-- ------------------------------------------------------------
-- 3) 岗位 JD 表  tb_jd
--    存储：用户输入的 JD 文本 + LLM 解析后的结构化字段
-- ------------------------------------------------------------
DROP TABLE IF EXISTS tb_jd;
CREATE TABLE tb_jd (
    id              BIGINT          AUTO_INCREMENT      COMMENT '主键ID',
    title           VARCHAR(200)    NOT NULL            COMMENT '岗位名称',
    company         VARCHAR(200)                        COMMENT '招聘公司',
    location        VARCHAR(100)                        COMMENT '工作地点',
    salary_range    VARCHAR(100)                        COMMENT '薪资范围，如 15k-25k',
    raw_text        MEDIUMTEXT      NOT NULL            COMMENT 'JD 原始文本',
    parsed_json     JSON                                COMMENT 'LLM 解析后的完整结构化数据',

    create_time     DATETIME        DEFAULT CURRENT_TIMESTAMP
                                                        COMMENT '创建时间',
    update_time     DATETIME        DEFAULT CURRENT_TIMESTAMP
                                                        ON UPDATE CURRENT_TIMESTAMP
                                                        COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_jd_title (title),
    KEY idx_jd_company (company),
    KEY idx_jd_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='岗位 JD 表';

-- ------------------------------------------------------------
-- 4) 分析历史记录表  tb_analysis_record
--    核心表：一次分析 = 1 条记录
--    字段包含：匹配度报告 / 简历优化建议 / 面试题
--    三块结果均以 JSON 存储，便于前端灵活渲染
-- ------------------------------------------------------------
DROP TABLE IF EXISTS tb_analysis_record;
CREATE TABLE tb_analysis_record (
    id                  BIGINT      AUTO_INCREMENT      COMMENT '主键ID',
    resume_id           BIGINT      NOT NULL            COMMENT '关联简历 tb_resume.id',
    jd_id               BIGINT      NOT NULL            COMMENT '关联岗位 tb_jd.id',

    -- 综合匹配度评分 0-100
    match_score         INT                             COMMENT '综合匹配度',

    -- 三类 AI 结果，统一 JSON
    match_report        JSON                            COMMENT '岗位匹配度报告',
    optimize_suggestions JSON                           COMMENT '简历优化建议',
    interview_questions JSON                            COMMENT '面试题列表',

    remark              VARCHAR(500)                    COMMENT '用户备注',
    create_time         DATETIME    DEFAULT CURRENT_TIMESTAMP
                                                        COMMENT '创建时间',

    PRIMARY KEY (id),
    KEY idx_ar_resume (resume_id),
    KEY idx_ar_jd (jd_id),
    KEY idx_ar_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分析历史记录表';

-- ------------------------------------------------------------
-- 5) 数据完整性检查
-- ------------------------------------------------------------
SELECT 'init.sql executed ✅' AS message;
