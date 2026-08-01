"""外部能力 API 包（M6）：X-API-Key 鉴权 + 三个能力端点 + 计费账单 + Webhook。"""

from app.api.external.router import external_router

__all__ = ["external_router"]
