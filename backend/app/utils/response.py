"""统一 JSON 响应格式 + 错误码

成功：{"code": 0,   "message": "success", "data": ...}
失败：{"code": -1,  "message": "错误描述", "data": null}
"""

from typing import Any

from app.core.request_context import get_request_id

# ===== 错误码常量 =====
ALL_OK: int = 0
ERR_COMMON: int = -1  # 通用错误
ERR_PARAM: int = -2  # 参数校验失败
ERR_FILE: int = -3  # 文件处理失败
ERR_AI: int = -4  # AI 调用失败
ERR_DB: int = -5  # 数据库操作失败
ERR_AUTH: int = -6  # 认证 / 授权失败
ERR_QUOTA: int = -7  # 额度不足 / 套餐限制


def _build_payload(code: int, message: str, data: Any) -> dict:
    payload = {"code": code, "message": message, "data": data}
    request_id = get_request_id()
    if request_id:
        payload["request_id"] = request_id
    return payload


def ok(data: Any = None, message: str = "success") -> dict:
    return _build_payload(ALL_OK, message, data)


def fail(message: str = "error", code: int = ERR_COMMON, data: Any = None) -> dict:
    return _build_payload(code, message, data)
