# 接口参考

- 生成时间: 2026-06-27 19:25:06 中国标准时间
- API 文档: `docs/generated/openapi.json`
- 路由数量: 103

## 方法统计

| 方法 | 数量 |
| --- | ---: |
| `GET` | 52 |
| `POST` | 41 |
| `PUT` | 3 |
| `DELETE` | 7 |

## agent

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/agent/start` | [Deprecated] Start agent workflow |
| `GET` | `/api/agent/task/{task_id}` | Get task status |
| `POST` | `/api/agent/task/{task_id}/cancel` | Cancel a running task |
| `POST` | `/api/agent/task/{task_id}/retry` | Retry a finished task |
| `GET` | `/api/agent/task/{task_id}/steps` | Get task step details |
| `GET` | `/api/agent/tasks` | List current user's agent tasks |
| `GET` | `/api/agent/tasks/summary` | Get current user's agent task summary |

## analysis

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/analysis/explain-match` | 匹配度解释器 |
| `POST` | `/api/analysis/full` | 一键智能分析：统一编排 Agent 工作流 |
| `POST` | `/api/analysis/match` | 一键分析：匹配度 + 优化 + 面试题 |
| `POST` | `/api/analysis/screen-candidates` | 企业端候选人批量筛选 |
| `POST` | `/api/analysis/screen-candidates/save` | 保存候选人筛选记录 |
| `GET` | `/api/analysis/screen-candidates/sessions` | 获取筛选记录列表 |
| `GET` | `/api/analysis/screen-candidates/sessions/{session_id}` | 获取筛选记录详情 |
| `GET` | `/api/analysis/screen-candidates/sessions/{session_id}/export` | 导出筛选记录 CSV |
| `GET` | `/api/analysis/{record_id}` | 获取单条分析结果详情 |
| `POST` | `/api/analysis/{record_id}/interview/regenerate` | 重新生成面试题 |
| `POST` | `/api/analysis/{record_id}/optimize/regenerate` | 重新生成简历优化建议 |
| `GET` | `/api/analysis/{record_id}/references` | 获取分析引用的知识库来源 |

## auth

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/auth/login` | 用户登录 |
| `GET` | `/api/auth/me` | 获取当前登录用户信息 |
| `POST` | `/api/auth/register` | 用户注册 |
| `POST` | `/api/auth/reset-password` | 重置密码 |

## career-path

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/career-path/recommend` | 职业方向推荐 |

## datasource

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/datasource` | 数据源列表 |
| `POST` | `/api/datasource` | 创建数据源 |
| `DELETE` | `/api/datasource/{ds_id}` | 删除数据源 |
| `GET` | `/api/datasource/{ds_id}` | 数据源详情 |
| `PUT` | `/api/datasource/{ds_id}` | 更新数据源 |
| `GET` | `/api/datasource/{ds_id}/logs` | 同步日志列表 |
| `POST` | `/api/datasource/{ds_id}/sync` | 手动触发同步 |
| `POST` | `/api/datasource/{ds_id}/test` | 测试数据源连接 |

## eval-reports

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/eval-reports/compare` | Compare two offline evaluation reports |
| `GET` | `/api/eval-reports/list` | List offline evaluation reports |
| `GET` | `/api/eval-reports/summary` | Offline evaluation report summary |
| `GET` | `/api/eval-reports/{report_id}` | Get offline evaluation report detail |

## history

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/history` | 历史记录列表（按时间倒序） |
| `DELETE` | `/api/history/{record_id}` | 软删除一条历史记录 |
| `GET` | `/api/history/{record_id}` | 历史记录详情 |

## interview

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/interview/sessions` | 用户面试列表 |
| `POST` | `/api/interview/sessions` | 创建 AI 模拟面试 |
| `DELETE` | `/api/interview/sessions/{session_id}` | 删除面试 |
| `GET` | `/api/interview/sessions/{session_id}` | 面试详情（含报告） |

## jd

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/jd` | 创建岗位 JD（同时可选解析） |
| `GET` | `/api/jd/list` | JD 列表 |
| `POST` | `/api/jd/parse` | 解析 JD（调用 LLM） |
| `GET` | `/api/jd/{jd_id}` | 获取 JD 详情 |

## job-pipeline

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/jobs/pipeline` | 创建投递流程记录 |
| `GET` | `/api/jobs/pipeline/list` | 获取投递流程列表 |
| `DELETE` | `/api/jobs/pipeline/rejected` | 清理已淘汰投递记录 |
| `DELETE` | `/api/jobs/pipeline/{entry_id}` | 删除投递流程记录 |
| `PUT` | `/api/jobs/pipeline/{entry_id}` | 更新投递流程记录 |

## job-recommend

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/jobs/batch-import` | Batch import jobs |
| `POST` | `/api/jobs/feedback` | Submit recommendation feedback |
| `GET` | `/api/jobs/feedback/evaluation` | Recommendation feedback evaluation dashboard |
| `GET` | `/api/jobs/feedback/stats` | Recommendation feedback summary |
| `GET` | `/api/jobs/feedback/tuning-export` | Export recommendation tuning samples |
| `GET` | `/api/jobs/feedback/tuning-samples` | Recommendation tuning samples |
| `GET` | `/api/jobs/list` | List jobs |
| `GET` | `/api/jobs/recommend` | Recommend jobs |
| `GET` | `/api/jobs/recommend-config` | Get recommendation tuning config |
| `PUT` | `/api/jobs/recommend-config` | Update recommendation tuning config |
| `POST` | `/api/jobs/recommend-config/compare` | Compare two recommendation configs |
| `POST` | `/api/jobs/recommend-config/reset` | Reset recommendation tuning config |
| `POST` | `/api/jobs/seed` | Seed demo jobs |
| `GET` | `/api/jobs/{jd_id}` | Get job detail |

## job-search

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/jobs/cities` | 支持的城市列表 |
| `POST` | `/api/jobs/fetch-detail` | 抓取岗位详情 |
| `POST` | `/api/jobs/search-external` | 搜索外部招聘岗位 |
| `POST` | `/api/jobs/seed-demo` | 一键导入演示岗位数据 |

## knowledge

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/knowledge/admin/embedding-stats` | Get embedding runtime stats |
| `GET` | `/api/knowledge/list` | List knowledge documents |
| `POST` | `/api/knowledge/query-rewrite-test` | Test query rewrite and retrieval |
| `POST` | `/api/knowledge/rebuild` | Rebuild all knowledge vectors |
| `POST` | `/api/knowledge/search` | Search knowledge base |
| `POST` | `/api/knowledge/upload` | Upload a knowledge document |
| `DELETE` | `/api/knowledge/{doc_id}` | Delete a knowledge document |
| `GET` | `/api/knowledge/{doc_id}` | Get knowledge document detail |
| `GET` | `/api/knowledge/{doc_id}/chunks` | Get indexed chunks for a document |
| `GET` | `/api/knowledge/{doc_id}/download` | Download a knowledge document |
| `POST` | `/api/knowledge/{doc_id}/reprocess` | Reprocess a knowledge document |

## misc

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/` | Health check |

## multi-agent

| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/api/multi-agent/auto` | Deprecated auto-dispatch multi-agent entry |
| `GET` | `/api/multi-agent/run/{run_id}` | Get legacy multi-agent run |
| `GET` | `/api/multi-agent/run/{run_id}/detail` | Get legacy multi-agent run detail |
| `POST` | `/api/multi-agent/start` | Deprecated full multi-agent entry |

## prompt-traces

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/prompt-traces/compare` | Compare prompt versions |
| `GET` | `/api/prompt-traces/list` | List prompt traces |
| `GET` | `/api/prompt-traces/summary` | Prompt trace summary |
| `GET` | `/api/prompt-traces/{trace_id}` | Prompt trace detail |

## resume

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/resume/accessible-list` | 获取所有可筛选的简历（企业端使用） |
| `GET` | `/api/resume/list` | List resumes |
| `POST` | `/api/resume/parse` | Parse resume |
| `POST` | `/api/resume/seed-demo` | 一键生成演示候选人简历 |
| `POST` | `/api/resume/upload` | Upload resume |
| `DELETE` | `/api/resume/{resume_id}` | Soft delete resume |
| `GET` | `/api/resume/{resume_id}` | Get resume detail |
| `GET` | `/api/resume/{resume_id}/download` | Download exported resume |
| `POST` | `/api/resume/{resume_id}/export` | Prepare resume export |
| `POST` | `/api/resume/{resume_id}/generate-optimized` | Generate optimized resume |
| `GET` | `/api/resume/{resume_id}/versions` | Get resume versions |

## system

| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/api/system/overview` | Get project overview metrics |
| `GET` | `/api/system/status` | Get runtime system status |
