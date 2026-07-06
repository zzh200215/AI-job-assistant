# 动态岗位数据接入与同步模块

## 文件清单

| 文件路径 | 说明 |
|---------|------|
| `backend/app/models/job_data_source.py` | SQLAlchemy 模型（job_data_source / job_sync_log / job_import_batch） |
| `backend/app/schemas/job_data_source.py` | Pydantic Schema（请求/响应校验） |
| `backend/scripts/init_datasource_tables.sql` | MySQL 初始化脚本 |
| `backend/app/services/job_data_source/adapter.py` | 适配器接口 `JobDataSourceAdapter` |
| `backend/app/services/job_data_source/csv_source.py` | CSV 数据源实现 |
| `backend/app/services/job_data_source/json_source.py` | JSON 数据源实现 |
| `backend/app/services/job_data_source/mock_source.py` | Mock 演示数据源实现 |
| `backend/app/services/job_data_source/api_source.py` | HTTP API 数据源框架（预留） |
| `backend/app/services/job_data_source/sync_service.py` | 同步核心服务（清洗/去重/写入/向量化） |
| `backend/app/api/job_data_source.py` | FastAPI Router `/api/datasource` |
| `backend/app/api/router.py` | 路由注册 |
| `frontend/src/api/datasource.js` | 前端 Axios API 封装 |
| `frontend/src/views/DataSource.vue` | 数据源管理页面 |
| `frontend/src/router/index.js` | 前端路由注册 |
| `backend/tests/test_datasource.py` | pytest 测试用例 |

## 快速开始

### 1. 初始化数据库

```bash
mysql -u root -p your_db < backend/scripts/init_datasource_tables.sql
```

### 2. 启动后端

```bash
cd backend
uvicorn main:app --reload
```

### 3. 启动前端

```bash
cd frontend
npm run dev
```

### 4. 访问页面

前端菜单或浏览器访问：`http://localhost:5173/datasource`

## API 列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/datasource` | 数据源列表 |
| POST | `/api/datasource` | 创建数据源 |
| GET | `/api/datasource/{id}` | 详情 |
| PUT | `/api/datasource/{id}` | 更新 |
| DELETE | `/api/datasource/{id}` | 删除 |
| POST | `/api/datasource/{id}/test` | 测试连接 |
| POST | `/api/datasource/{id}/sync` | 手动同步 |
| GET | `/api/datasource/{id}/logs` | 同步日志 |

## 数据源类型说明

- **csv**: 读取本地 CSV 文件，支持自定义分隔符、编码、字段映射
- **json**: 读取本地 JSON 文件，支持嵌套路径提取（如 `data.jobs`）
- **api**: HTTP API 数据源（预留框架，需补充鉴权/分页）
- **mock**: 返回 5 条演示数据，用于快速验证流程

## 同步流程

```
读取数据源 -> 字段清洗/映射 -> 去重检查 -> 写入 tb_jd
                                        |
                                        v
                              生成 Embedding -> 写入 Chroma
                                        |
                                        v
                              记录同步日志 (成功/失败/耗时)
```

## 去重逻辑

基于 `job_import_batch.external_id` + `source_id` 进行去重。同一数据源中，已导入成功的 `external_id` 在后续同步时会被跳过，并计入 `duplicate_count`。

## 扩展新的数据源类型

1. 继承 `JobDataSourceAdapter`
2. 实现 `connect()` 和 `read(limit)` 方法
3. 在 `sync_service.py` 的 `_SOURCE_REGISTRY` 中注册

示例：

```python
from app.services.job_data_source.adapter import JobDataSourceAdapter, SourceRow

class SpiderJobSource(JobDataSourceAdapter):
    def connect(self) -> bool:
        return True

    def read(self, limit: int = 0) -> List[SourceRow]:
        # 实现爬虫抓取逻辑
        return rows
```

然后在 `sync_service.py` 中注册：

```python
_SOURCE_REGISTRY = {
    "csv": CsvJobSource,
    "json": JsonJobSource,
    "mock": MockJobSource,
    "api": ApiJobSource,
    "spider": SpiderJobSource,  # 新增
}
```

## 运行测试

```bash
cd backend
pytest tests/test_datasource.py -v
```

## 注意事项

- 向量化依赖 `EMBEDDING_PROVIDER` 环境变量，开发环境默认使用 mock embedding
- Chroma 使用独立 collection `job_descriptions`，与知识库 `knowledge_base` 隔离
- 同步日志最多保留 50 条明细错误，防止 JSON 过大
