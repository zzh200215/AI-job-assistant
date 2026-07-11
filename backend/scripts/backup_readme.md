# 备份与恢复说明

本目录提供智能招聘平台的备份与恢复脚本，覆盖 MySQL 数据库、上传文件（uploads/）和 Chroma 向量数据（chroma_db/）。

## 前置要求

- Python 3.11+
- `mysqldump` 命令行工具
- 当前用户可读取 `backend/.env`（或对应环境变量）以获取 MySQL 连接信息

## 备份

### 手动执行

```bash
# 从项目根目录执行
python backend/scripts/backup.py

# 模拟运行（不写入任何文件）
python backend/scripts/backup.py --dry-run

# 保留最近 14 天备份
python backend/scripts/backup.py --keep 14
```

备份目录结构示例：

```
backups/
├── 20260711_120000/
│   ├── llmXM.sql
│   ├── uploads.tar.gz
│   ├── chroma.tar.gz
│   └── manifest.json
└── backup.log
```

### 定时任务（cron）

```bash
# 每天凌晨 2 点执行备份，保留 7 天
0 2 * * * /path/to/project/backend/scripts/backup.sh --keep 7
```

`--keep` 默认会回退到 `BACKUP_KEEP_DAYS` 环境变量（默认值 7）。

## 恢复

> 恢复操作会覆盖当前数据，执行前请确保已备份当前状态。

```bash
# 先查看会恢复哪些内容（dry-run）
./backend/scripts/restore.sh backups/20260711_120000 --dry-run

# 正式恢复，需要输入 YES 确认
./backend/scripts/restore.sh backups/20260711_120000
```

恢复流程：

1. 将 `.sql` 导入 MySQL。
2. 解压 `uploads.tar.gz` 到项目根目录的 `uploads/`。
3. 解压 `chroma.tar.gz` 到项目根目录的 `chroma_db/`。

## 注意事项

- 生产环境建议将备份目录同步到异地存储（如对象存储、NAS）。
- 恢复前请停止定时任务或业务写入，避免数据不一致。
- Chroma 数据恢复后可能需要重启后端服务以重新加载向量索引。
- 备份脚本不会备份环境变量文件（`.env`），请单独妥善保管。
