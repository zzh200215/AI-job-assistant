"""Centralized application settings."""

from __future__ import annotations

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
    LLM_MODEL: str = "gpt-3.5-turbo"
    LLM_TIMEOUT: int = 60
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
            and str(self.EMBEDDING_PROVIDER or "").strip().lower() in {"openai", "qwen", "dashscope"}
            and not (self.EMBEDDING_API_KEY or self.LLM_API_KEY or "").strip()
        ):
            raise ValueError(
                "EMBEDDING_API_KEY (or LLM_API_KEY) is required for the configured embedding provider in production."
            )

        return self


settings = Settings()
