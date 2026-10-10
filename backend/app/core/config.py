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
