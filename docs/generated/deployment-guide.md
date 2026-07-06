# 部署指南

- 生成时间: 2026-06-27 19:25:06 中国标准时间
- 当前后端编排后端: `thread`
- 当前编排策略: `linear`

## 环境前置

- Python 3.10+
- Node.js 18+
- MySQL 8.0+
- 可选 Redis（当 `ORCHESTRATION_BACKEND=redis_queue` 时启用）

## 启动步骤

```bash
cd backend
copy .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

## 交付验证

- 后端测试: `cd backend && pytest`
- 全量验证: `scripts/verify.ps1`
- 评测产物: `scripts/eval-quality.ps1`
- 接口文档导出: `cd backend && python scripts/export_delivery_docs.py`

## 关键配置

- `APP_ENV`
- `APP_DEBUG`
- `MYSQL_PASSWORD`
- `JWT_SECRET`
- `LLM_PROVIDER`
- `EMBEDDING_PROVIDER`
- `ORCHESTRATION_STRATEGY`
- `ORCHESTRATION_ENGINE`
- `ORCHESTRATION_BACKEND`
- `REDIS_URL`
- `RAG_TOP_K`
- `RAG_USE_PLANNER`
