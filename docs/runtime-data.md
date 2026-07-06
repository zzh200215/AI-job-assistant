# 运行产物与版本控制边界

本项目会在本地运行、测试和演示过程中生成上传文件、向量库、模型缓存、构建产物和日志。这些内容不应该作为业务代码提交到 Git。

## 应保留在 Git 中

- 源代码：`backend/app/`、`frontend/src/`
- 配置样例：`backend/.env.example`、`frontend/.env.example`
- Docker 文件：`Dockerfile`、`docker-compose.yml`、`nginx.conf`
- 测试代码：`backend/tests/`、`backend/conftest.py`
- 文档和种子知识库：`docs/`、`docs/knowledge-seeds/`
- 空目录占位：`backend/uploads/.gitkeep`、`backend/chroma_db/.gitkeep`、`backend/models/.gitkeep`

## 不应提交到 Git

- 用户上传文件：`backend/uploads/**`
- 导出的简历文件：`backend/uploads/export/**`
- Chroma 向量库：`backend/chroma_db/**`
- 本地模型缓存：`backend/models/**`
- 前端构建产物：`frontend/dist/**`
- 依赖目录：`frontend/node_modules/**`、Python 虚拟环境
- 运行日志：`*.log`
- 临时端口/启动记录：`ports.log`、`fetch.log`
- Vite 临时文件：`frontend/vite.config.js.timestamp-*`

## 已被 Git 跟踪时的处理方式

`.gitignore` 只对未跟踪文件生效。已经进入 Git 的运行产物，需要从索引中移除，但保留本地文件：

```bash
git rm --cached -r backend/chroma_db backend/models
git rm --cached -r backend/uploads
git add backend/uploads/.gitkeep backend/chroma_db/.gitkeep backend/models/.gitkeep
git rm --cached -- backend/*.log frontend/*.log fetch.log ports.log
```

执行前先用下面命令确认清单：

```bash
git ls-files backend/chroma_db backend/models backend/uploads backend/*.log frontend/*.log *.log
```

如果某些上传文件是答辩必须使用的样例，不要放在 `backend/uploads`。建议改放到 `docs/sample-data/`，并用脱敏文件名和说明文档管理。

## 建议提交分组

当前仓库改动较多，建议拆成以下几类提交，便于评审和回滚：

1. 运行时产物清理：`.gitignore`、`backend/uploads/**` 索引删除、`backend/chroma_db/**` 索引删除、`backend/models/**` 索引删除、日志文件索引删除，以及三个 `.gitkeep`。
2. 后端工程质量：任务中心、权限隔离、运行指标、迁移、评估脚本和对应测试。
3. Agent/RAG 质量：prompt 迁移、检索规划、mock embedding 维度修复、Agent eval 调优和回归测试。
4. 前端交付体验：系统状态、任务中心、企业筛选、职业规划、页面入口和请求追踪。
5. 文档交付：README、工程质量、部署安全、知识库维护、数据源边界和答辩材料。

## 本机 Git 告警

如果命令输出出现 `unable to access 'C:\Users\TX/.config/git/ignore': Permission denied`，这是本机 Git 默认全局 ignore 路径权限问题，不是项目文件问题。可选处理：

```powershell
git config --global core.excludesfile "%USERPROFILE%\.gitignore_global"
```

如果 `.git/config` 或用户 Git 配置不可写，需要先修复本机目录权限；项目验证不依赖该文件。
