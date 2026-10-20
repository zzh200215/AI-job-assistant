"""Centralized application settings."""

from __future__ import annotations

import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "dev-jwt-secret-change-me-before-production-1234"
_WEAK_DB_PASSWORDS = {"", "root", "123456", "password"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = False
    TESTING: bool = False
    LOG_LEVEL: str = "INFO"
    AUTO_CREATE_TABLES: bool = True

    CORS_ORIGINS: str = ""
    ADMIN_USERNAMES: str = "admin"
    # 采集端（Prometheus）读 /api/system/metrics 用的静态 Bearer 令牌。
    # 留空时该端点退回"仅管理员会话可读"，但任何时候都不会对匿名开放。
    METRICS_TOKEN: str = ""

    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DB: str = "llmXM"
    DATABASE_URL: str | None = None

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 10

    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: str | None = None
    LLM_BASE_URL: str | None = None
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT: int = 120
    LLM_FALLBACK_MODEL: str | None = None
    LLM_ALLOW_MOCK_FALLBACK: bool = False
    LLM_INPUT_COST_PER_1K_CENTS: float = 0.0
    LLM_OUTPUT_COST_PER_1K_CENTS: float = 0.0
    # 按型号的单价，逗号分隔：`model:输入分/1k:输出分/1k`，例如
    #   LLM_MODEL_COSTS=deepseek-v4-flash:0.02:0.2,glm-5.2:0.06:0.4
    # 为什么要有它：`_record_usage` 拿得到 `model`（`llm_service.py:919/1166`）却只用两个**全局**
    # 数算钱，而 2026-10-10 起主备是两个不同型号（`deepseek-v4-flash` + `glm-5.2`），
    # 再叠上"换供应商只改 .env 三行"这条路——两个全局数无法表达按型号分价，成本会静默错。
    # 现量事实：SenseNova 官方页写"公测期完全免费开放，付费档位即将上线"，所以**今天留空是对的**
    # （成本真的是 0）；这条机制是为了付费档位上线那天不必改代码，而不是为了补一个我编的数。
    LLM_MODEL_COSTS: str = ""

    ORCHESTRATION_STRATEGY: str = "linear"
    ORCHESTRATION_ENGINE: str = "native"
    ORCHESTRATION_BACKEND: str = "thread"
    ORCHESTRATION_MAX_WORKERS: int = 4
    ORCHESTRATION_STALE_TASK_MINUTES: int = 30
    ORCHESTRATION_QUEUE_NAME: str = "analysis-tasks"
    ORCHESTRATION_QUEUE_POLL_SECONDS: float = 1.0
    # 只作用于 redis_queue 后端。可见性超时必须**大于**单条编排任务的真实最长耗时：
    # 短于它就会把一个还在跑的 TaskPayload 重投，两个 worker 同时跑同一个 run（LLM 白付两遍、
    # 结果互相覆盖）。3600 是刻意取在 ORCHESTRATION_STALE_TASK_MINUTES(30 分钟) 之上的。
    ORCHESTRATION_VISIBILITY_SECONDS: float = 3600.0
    # 含首次执行：跑满这么多回仍失败就进死信队列，不再回到主队列。
    ORCHESTRATION_MAX_ATTEMPTS: int = 3
    REDIS_URL: str | None = None
    # 连接池三个数（§10.15 的那半决策）：以前没设，跑的是 SQLAlchemy 默认的 5 + 10 = 15 根、
    # 排队 30 秒 —— 而 E16 之后每条面试 WS 会独占一根，这个隐式上限就成了实际吞吐上限。
    # 现在写死并让它可读：`core/database.py:engine_kwargs_for` 只在非 sqlite 上生效。
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    INTERVIEW_EVALUATION_MAX_WORKERS: int = 2
    # 动态面试官（P3.1）：关掉这个开关，`next_question` 回到"按建会话时冻结的那份列表按下标取题"
    # 这条今天的链，逐字相同。它存在的理由不是兼容，是**回滚半径**：决策器接管的是候选人正在等的
    # 下一题，出意料行为时关一个开关就能回到今天，而不是回滚代码。
    INTERVIEW_USE_DECIDER: bool = True
    # 决策器那一档的 LLM 硬截止时间（秒）。超了就落回启发式那句——候选人不能为一句追问等两分钟。
    INTERVIEW_DECISION_TIMEOUT_SECONDS: float = 6.0
    # 一场面试最多出多少题。生成链、引擎上限与设置页展示都读这一个数；默认 10（历史行为），
    # 允许 1–20，越界由 `interview_config_service.max_questions()` 夹取。
    INTERVIEW_MAX_QUESTIONS: int = 10
    # 逐题评分是投给**本地线程池**的：进程一死，那一行就留在 pending/running，没人来捡。
    # 这个阈值就是"认定提交它的进程已经不在了"要等多久。下界有数：单题最坏 = LLM_TIMEOUT(120s)
    # × 3 次尝试 + 线性退避(1.5s + 3.0s) = 364.5s ≈ 6.1 分钟（`utils/retry.py:49` 的
    # `wait = backoff_factor * (attempt + 1)`，`_LLM_MAX_RETRIES=2`），取 15 分钟仍在它之上——
    # 否则一次扫描会把还在跑的评分抢过来重付一遍模型调用。上界是候选人的终报要等多久才能补齐。
    INTERVIEW_EVALUATION_REQUEUE_MINUTES: int = 15
    # 认领租约（D178）：一行被 claim 之后，多久之内**任何人**都不能再 claim 它——包括换了
    # observed status 的那个（`pending→running` 与 `running→pending` 是两条 transition，
    # 只按 status 做条件的旧认领让两个副本各领一次，同一道题付两遍模型钱，2026-10-09 D177
    # 用真 8 进程 + 真 MySQL 跑出 `1 0 0 1 0 0 0 0`）。下界与上面那条同源：单题最坏 364.5s
    # ≈ 6.1 分钟 ⇒ 原来的 5 分钟在 D185 把 LLM_TIMEOUT 抬到 120s 之后就**短于在途时长**了
    # （租约过期等于把双付路径重新打开），所以取 10 分钟 = 1.64 倍余量；它仍小于
    # REQUEUE_MINUTES(15)，所以"主人真死了"的恢复等待没有被拉长——那条上界一直是 15 分钟。
    INTERVIEW_EVALUATION_CLAIM_LEASE_MINUTES: int = 10
    # 同时在途的面试 WS 上限。**每连接一个引擎 = 一条连接期间持有一个 SQLAlchemy Session**。
    # 取 12 的理由现在写在纸面上而不是注释里：池子上限 10 + 10 = 20 根，留 8 根给同期 HTTP 请求。
    # 改 DB_POOL_SIZE/DB_MAX_OVERFLOW 时必须同时回头看这个数还留不留得出 HTTP 的余量。
    WS_MAX_LIVE_INTERVIEWS: int = 12

    # D200：行级改写建议改成后台任务之后的三个数。
    # 线程数取 2 是拿连接池算过的：作业在等模型的那一段时间里，它那条 Session 仍占着一个连接
    # （`build_rewrite_suggestions` 读简历与调模型用的是同一条会话），而池子上限是
    # `DB_POOL_SIZE + DB_MAX_OVERFLOW = 20`，anyio 的 HTTP 线程上限也钉在同一个 20
    # （`core/threadpool.py`）。2 = 最多 2 个连接被作业按住，剩下 18 个仍够同期 HTTP 用；
    # 再大就会开始出现"请求没超时但看起来死了"的那幅形状。
    # D214 把"这是推的数、不是压测的吞吐"那句未验补掉了（模型那一发换成 sleep，花费 0；
    # 脚本在仓库外 `_probes/rewrite_job_throughput.py`）：单发按 D201 的 p50 10.68s 记，
    # 8 个作业下 W=1/2/4/8 的墙钟是 85.73 / 42.89 / 21.48 / 10.80 秒——**严格线性**，
    # rate 就是 `W / 单发时长`（W=2 时 0.187/s，理论 0.187）；观测到的 `pool.checkedout()`
    # 峰值 = W+1，证实"每个在跑的作业按住一根连接"这句不是修辞。按前端那 150s 轮询预算
    # （75×2000ms）折回来：W=2 时最慢那一发 43s，预算内能接的并发是 **26 发**（p50 口径；
    # 换成 D201 量到的最坏单发 16.02s 就只剩 18 发，这一半是算术不是实测）。所以 2 不是吞吐
    # 逼出来的下界，是池子留给 HTTP 的余量——结论不变，改的是它有数了。
    REWRITE_JOB_MAX_WORKERS: int = 2
    # 租约下界有数：最坏一发 = 主模型 3 次尝试 + 备模型 3 次尝试，各带 `LLM_TIMEOUT=120`，
    # 加上线性退避 1.5s/3s ≈ **729s ≈ 12.2 分钟**（D189 量的 364.5s 只是单型号那一半）。
    # 取 15 分钟在它之上，否则一次扫描会把还在跑的作业抢过来重付一遍模型调用。
    REWRITE_JOB_LEASE_MINUTES: int = 15
    # 终态作业留几天。这一张表存的是候选人**没采纳**的文本，留着只有排障价值；
    # 清理走"提交新作业时顺带删掉本人过期的"，不另立一条调度任务（见 rewrite_job_service）。
    REWRITE_JOB_RETENTION_DAYS: int = 7

    # D229：简历评估报告（六模块）是一项后台作业。
    # 一次报告最多三发模型调用（概览、批改稿、面试预演），投递策略那一节不过模型。
    # 所以池子比改写作业更小：同一时刻多一个报告，就从 HTTP 那 20 根连接里多扣一根。
    REPORT_JOB_MAX_WORKERS: int = 1
    # 租约 = 改写作业那 15 分钟的最坏单发 × 三发。短于此会把还在跑的报告抢过来重付模型钱。
    REPORT_JOB_LEASE_MINUTES: int = 45
    # 这一张表存的是整份报告（含批改稿原文），体积比建议那一份大得多，保留期因此取 3 天。
    REPORT_JOB_RETENTION_DAYS: int = 3

    # D226：批量导入岗位变成后台作业（`job_import_task`）。
    # 1 而不是 2：一次导入是纯数据库写，占一根连接 + 一路 INSERT；D214/D215 已经量过"后台并发
    # 直接从 HTTP 那 20 根里扣"，而这种活儿并排跑只会互相抢池子、没有吞吐收益。
    JOB_IMPORT_MAX_WORKERS: int = 1
    # 租约要大于最坏一次跑动。现量（D219，同一份工作：解析 + 每行一个 ORM 对象 + commit）：
    # 50 行 20ms、300 行 99ms、2000 行 677ms；文件上限 10MB ⇒ 行数上限是万级，秒级到几十秒。
    # 取 10 分钟留两个数量级余量：宁可晚一步重投，也不要把还在跑的导入抢过来跑第二遍。
    JOB_IMPORT_LEASE_MINUTES: int = 10
    # 这张表存的是"导入到第几行、成了几行、跳过了几行"，跑完只对排障有价值，一周足够。
    JOB_IMPORT_RETENTION_DAYS: int = 7
    # 每 N 行提交一次并刷进度。太小就把一次导入变成 N 次往返（2000 行按 1 行一提交就是 2000 次），
    # 太大客户端看不到走动；25 行 ≈ 万级文件也有 400 次刷新。
    JOB_IMPORT_PROGRESS_EVERY: int = 25
    # 逐行问题最多记几条：一个 10MB 的坏文件能让 `problems` 长到几十万字节的 JSON。
    JOB_IMPORT_MAX_PROBLEMS: int = 20

    # Operations alerting: thresholds are deliberately configurable per deployment.
    OPERATIONS_ALERT_WINDOW_MINUTES: int = 60
    OPERATIONS_ALERT_QUEUE_BACKLOG_THRESHOLD: int = 100
    OPERATIONS_ALERT_TASK_FAILURE_THRESHOLD: int = 5
    OPERATIONS_ALERT_LLM_FAILURE_THRESHOLD: int = 5
    # Degraded = a response that did not come from the configured primary model
    # (mock / truncated / fallback_model). Candidates are not told, so ops is the
    # only channel that can notice fabricated content reaching results.
    OPERATIONS_ALERT_LLM_DEGRADED_THRESHOLD: int = 3
    # A single mock response means fabricated content was already served to a
    # candidate, so it alerts on its own terms rather than waiting for a volume
    # threshold to be crossed.
    OPERATIONS_ALERT_LLM_MOCK_THRESHOLD: int = 1
    OPERATIONS_ALERT_TRACE_WRITE_FAILURE_THRESHOLD: int = 1
    OPERATIONS_ALERT_MIN_REQUESTS: int = 20
    OPERATIONS_ALERT_HTTP_ERROR_RATE_THRESHOLD: float = 0.15
    # D218：取连接排队（`db_pool_connection_acquire_seconds`，D217 装的仪器）进告警。
    # 1s 这条线来自 D215 的实测：掺进 2 个后台作业之后最差等待 10.68–11.73s，而**没有任何**
    # 一条现有规则会因此变红（池子还是 16/20，HTTP 错误率也没动）。1s 在"空闲 0.0003s"与
    # "排队 11s"之间，留出一个数量级的余量。
    OPERATIONS_ALERT_DB_ACQUIRE_P95_SECONDS: float = 1.0
    # p95 是小样本统计量：一个窗口只有 3 次取连接时，p95 就等于那一次的最大值，不构成门。
    # 20 与 `OPERATIONS_ALERT_MIN_REQUESTS` 同量级但**故意不是同一个设置**——那条数的是 HTTP 请求，
    # 这条数的是取连接次数，一条定时任务一拍就能贡献后者而不贡献前者。
    OPERATIONS_ALERT_DB_ACQUIRE_MIN_SAMPLES: int = 20
    # 越过 `DB_POOL_TIMEOUT` 的等待 = 直接抛 TimeoutError（路由 500 / 后台作业 failed），
    # 一次就要醒：它是"已经在丢请求"，不是"有点慢"。
    OPERATIONS_ALERT_DB_TIMEOUT_SAMPLES: int = 1

    # AI release governance. Every configured report type must have current, thresholded evidence.
    AI_RELEASE_REQUIRED_EVALUATION_TYPES: str = "rag,agent,recommend"
    AI_RELEASE_MAX_EVALUATION_AGE_DAYS: int = 30

    EMBEDDING_PROVIDER: str = "mock"
    EMBEDDING_API_KEY: str | None = None
    EMBEDDING_BASE_URL: str | None = None
    EMBEDDING_MODEL: str = "text-embedding-v3"
    EMBEDDING_TIMEOUT: int = 30
    EMBEDDING_MAX_RETRIES: int = 2

    RERANKER_PROVIDER: str = "auto"
    RERANKER_MODEL_PATH: str | None = None
    RERANKER_BATCH_SIZE: int = 8

    JWT_SECRET: str = _DEFAULT_JWT_SECRET
    JWT_ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    BCRYPT_ROUNDS: int = 12

    STRUCTURED_LOGS: bool = False
    RUN_SCHEDULER: bool = True

    # Rate limiting (slowapi). Empty/unset falls back to code defaults.
    RATE_LIMIT_GENERAL: str | None = None
    # §10.10 的决策：只给昂贵端点（=真实 provider 调用）独立额度，每 IP 总闸维持现状。
    # 30 不是拍的：一次 linear 编排实测 12 个 agent / 13 个 chat 调用点 ≈ 每个任务 ≤11 次调用，
    # 而请求内同步花钱的 resume 路由每次 1 次。30/分钟 ≈ 一分钟内三个完整深度分析。
    # 0 或负数 = 关闭额度（`llm_quota.charge_if_real_provider` 直接放行）。
    LLM_CALLS_PER_USER_PER_MINUTE: int = 30
    RATE_LIMIT_AUTH: str | None = None
    RATE_LIMIT_LOGIN: str | None = None

    # Backup retention
    BACKUP_KEEP_DAYS: int = 7

    RAG_TOP_K: int = 5
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50
    # Chroma 持久化目录；留空 = backend/chroma_db（默认）。CI 的语料评估用临时目录。
    CHROMA_DIR: str = ""
    # Chroma 距离阈值：score(=distance) > 该值的 chunk 视为低相关被过滤；0.0 表示禁用
    RAG_SCORE_THRESHOLD: float = 0.0
    # 是否启用 LLM 检索路由（关闭则走启发式回退，对 mock provider 也安全）
    RAG_USE_PLANNER: bool = True

    # SMTP 邮件服务
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_FROM: str = "noreply@career-signal.ai"
    FRONTEND_URL: str = "http://localhost:5173"

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
            f"?charset=utf8mb4"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @property
    def admin_usernames_list(self) -> list[str]:
        return [item.strip() for item in self.ADMIN_USERNAMES.split(",") if item.strip()]

    @property
    def ai_release_required_evaluation_types(self) -> list[str]:
        return [item.strip() for item in self.AI_RELEASE_REQUIRED_EVALUATION_TYPES.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() in {"prod", "production"}

    @property
    def llm_model_costs(self) -> dict[str, tuple[float, float]]:
        """`LLM_MODEL_COSTS` 解析成 `{model: (输入分/1k, 输出分/1k)}`。

        写错的条目**跳过并留一条 warning**，不抛：单价表是运维配置，一个逗号不该让整站在
        启动或算钱时崩掉；但也不能静默吞——那正是"成本看着是 0 其实是配错了"的形状。
        """
        costs: dict[str, tuple[float, float]] = {}
        for entry in (self.LLM_MODEL_COSTS or "").split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = [part.strip() for part in entry.split(":")]
            if len(parts) != 3 or not parts[0]:
                logging.getLogger(__name__).warning(
                    "LLM_MODEL_COSTS 里有一条读不懂，已跳过：%r（应为 model:输入分:输出分）", entry
                )
                continue
            try:
                in_cost, out_cost = float(parts[1]), float(parts[2])
            except ValueError:
                logging.getLogger(__name__).warning("LLM_MODEL_COSTS 里的单价不是数字，已跳过：%r", entry)
                continue
            costs[parts[0].lower()] = (in_cost, out_cost)
        return costs

    def unit_costs_for(self, model: str | None) -> tuple[float, float]:
        """这一发按哪个单价算钱：型号表里有就用它，否则退回两个全局数（今天的行为）。"""
        costs = self.llm_model_costs
        hit = costs.get((model or "").strip().lower())
        if hit is not None:
            return hit
        return float(self.LLM_INPUT_COST_PER_1K_CENTS or 0.0), float(self.LLM_OUTPUT_COST_PER_1K_CENTS or 0.0)

    @model_validator(mode="after")
    def _check_security_defaults(self):
        if len(self.JWT_SECRET or "") < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long.")

        if self.is_production and self.APP_DEBUG:
            raise ValueError("APP_DEBUG must be False when APP_ENV=production.")

        if self.is_production and self.AUTO_CREATE_TABLES:
            raise ValueError(
                "AUTO_CREATE_TABLES must be False when APP_ENV=production. Run Alembic migrations instead."
            )

        if self.is_production and self.JWT_SECRET == _DEFAULT_JWT_SECRET:
            raise ValueError("Set a unique JWT_SECRET before running in production.")

        if self.is_production and (self.MYSQL_PASSWORD or "").strip() in _WEAK_DB_PASSWORDS:
            raise ValueError("Set a non-default MYSQL_PASSWORD before running in production.")

        if self.is_production and str(self.LLM_PROVIDER or "").strip().lower() == "mock":
            raise ValueError("LLM_PROVIDER cannot be 'mock' in production.")

        if self.is_production and str(self.EMBEDDING_PROVIDER or "").strip().lower() == "mock":
            raise ValueError("EMBEDDING_PROVIDER cannot be 'mock' in production.")

        if self.is_production and str(self.LLM_FALLBACK_MODEL or "").strip().lower() == "mock":
            raise ValueError("LLM_FALLBACK_MODEL cannot be 'mock' in production.")

        if (
            self.is_production
            and str(self.LLM_PROVIDER or "").strip().lower() in {"openai", "qwen", "local"}
            and not (self.LLM_API_KEY or "").strip()
        ):
            raise ValueError("LLM_API_KEY is required for the configured LLM provider in production.")

        if (
            self.is_production
            and str(self.LLM_PROVIDER or "").strip().lower() in {"openai", "qwen", "local"}
            and not (self.LLM_BASE_URL or "").strip()
        ):
            # 2026-10-09 换到 SenseNova 之后，`openai` 这个值不再等于"用 OpenAI 的端点"——它只表示
            # "走 OpenAI 兼容协议"。此时留空 LLM_BASE_URL 会静默落到代码里的 api.openai.com 默认值，
            # 于是新供应商的 key 被发给旧端点：每一次调用都 401，而 `/api/system` 那格只看
            # `bool(api_key)`，管理员面板上仍然写着 "Configured"（`api/system.py:86-88`）。
            raise ValueError(
                "LLM_BASE_URL is required in production when LLM_PROVIDER is a network provider: "
                "an empty value silently targets the built-in api.openai.com default."
            )

        if (
            self.is_production
            and str(self.EMBEDDING_PROVIDER or "").strip().lower() in {"openai", "qwen", "dashscope"}
            and not (self.EMBEDDING_API_KEY or self.LLM_API_KEY or "").strip()
        ):
            raise ValueError(
                "EMBEDDING_API_KEY (or LLM_API_KEY) is required for the configured embedding provider in production."
            )

        self._reject_split_provider_embedding_fallback()

        return self

    def _reject_split_provider_embedding_fallback(self) -> None:
        """向量化会借用 LLM 那一套 key/base 的时候，必须说清楚。

        起因（2026-10-09 真撞）：`embedding_service.py` 里是 `EMBEDDING_API_KEY or LLM_API_KEY`、
        `EMBEDDING_BASE_URL or LLM_BASE_URL`。把 LLM 从 dashscope 换到另一家 OpenAI 兼容供应商时，
        如果只改 `LLM_*`，向量化会跟着去新供应商找 `text-embedding-v3`——新供应商通常没有向量模型，
        于是 RAG 整条静默挂掉，而界面上一切正常。生产直接拒绝启动；非生产留一条 warning
        （开发机上换供应商是常态，不该被硬挡）。

        判据按**两条真实的借用路径**分别算，不一刀切（第一版一刀切误杀了两种合法配置，D181 修）：
        * `base_url` 只有走 OpenAI 兼容 HTTP 的那一支会用到（`_openai_embed:337`）；
          `dashscope` 走阿里云 SDK（`_dashscope_embed:306-319`）**不读 base_url**，要求它就是误杀。
        * 同一家族之间借 key 是合法的——`qwen` 与 `dashscope` 都是阿里云、同一把 key；跨家族才要显式。
        """
        llm = str(self.LLM_PROVIDER or "").strip().lower()
        emb = str(self.EMBEDDING_PROVIDER or "").strip().lower()
        family = {"openai": "openai", "qwen": "aliyun", "dashscope": "aliyun", "local": "local"}
        if llm not in family or emb not in family or family[llm] == family[emb]:
            return

        missing: list[str] = []
        if not (self.EMBEDDING_API_KEY or "").strip():
            missing.append("EMBEDDING_API_KEY")
        if emb in {"openai", "qwen"} and not (self.EMBEDDING_BASE_URL or "").strip():
            missing.append("EMBEDDING_BASE_URL")
        if not missing:
            return

        borrowed = "端点/密钥" if emb in {"openai", "qwen"} else "密钥"
        message = (
            f"LLM_PROVIDER={llm} 与 EMBEDDING_PROVIDER={emb} 跨供应商家族（{family[llm]} → {family[emb]}），"
            f"但 {', '.join(missing)} 没配：embedding 会回退到 LLM 那一家的{borrowed}，"
            "向量化大概率直接失败。要么两家合一，要么把缺的那几行显式写上。"
        )
        if self.is_production:
            raise ValueError(message)
        logging.getLogger(__name__).warning(message)


settings = Settings()
