# 数据库迁移说明

后端现在使用 Alembic 管理长期 schema 演进。开发环境仍默认允许自动建表，生产环境必须关闭自动建表并显式执行迁移。

## 环境变量

- `AUTO_CREATE_TABLES=True`：开发默认值，应用启动时会执行 `Base.metadata.create_all`，便于本地快速启动。
- `AUTO_CREATE_TABLES=False`：生产推荐值，应用启动不再自动建表，需要先运行 Alembic。
- `APP_ENV=production` 时，如果 `AUTO_CREATE_TABLES=True`，应用会拒绝启动。
- `DATABASE_URL`：可选的完整 SQLAlchemy 连接串。设置后优先于 `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DB`。

## 常用命令

在 `backend` 目录执行：

```bash
pip install -r requirements.txt
alembic upgrade head
alembic current
alembic history
```

使用临时 SQLite 文件验证迁移：

```bash
DATABASE_URL=sqlite:///./migration_check.sqlite3 alembic upgrade head
```

也可以在仓库根目录运行完整验证脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1 -Python py -SkipFrontend
```

验证脚本会临时设置控制台输出为 UTF-8，并启用 `PYTHONUTF8=1`，用于避免中文项目路径在 Windows PowerShell 输出中乱码。

生成新迁移：

```bash
alembic revision --autogenerate -m "describe schema change"
```

生成后需要人工 review 迁移文件，确认不会误删表、误删列或错误变更 JSON/Text/DateTime 类型。

## 空库初始化

空 MySQL 库可以直接执行：

```bash
alembic upgrade head
```

当前基线迁移会根据 SQLAlchemy ORM 模型创建完整表结构。

## 已有开发库

如果数据库已经由旧的 `sql/init*.sql`、`add_columns.py` 或应用自动建表创建，先确认当前表结构和 ORM 模型一致，再执行：

```bash
alembic stamp 20260612_0001
```

`stamp` 只记录迁移版本，不会修改现有表。若旧库缺字段，需要先补一个显式增量迁移，而不是直接 stamp。

## 生产建议

生产发布顺序：

1. 备份数据库。
2. 部署代码和依赖。
3. 执行 `alembic upgrade head`。
4. 设置 `APP_ENV=production`、`AUTO_CREATE_TABLES=False`。
5. 启动后端服务。

Docker Compose 部署时，可以先执行一次性迁移服务：

```bash
APP_ENV=production AUTO_CREATE_TABLES=false docker compose --profile tools run --rm migrate
APP_ENV=production AUTO_CREATE_TABLES=false docker compose up -d backend frontend
```

如果只是本地开发，仍可直接运行：

```bash
docker compose up --build -d
```

旧的 SQL 初始化脚本可以继续作为历史参考，但新 schema 变更应优先写 Alembic 迁移。
