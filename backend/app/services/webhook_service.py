"""外部 Webhook 服务（T6-3）：订阅管理 + 事件投递（HMAC 签名，失败重试 3 次）。

签名：HMAC-SHA256(secret, raw JSON body) 十六进制 → 头 `X-Webhook-Signature`。
投递：POST JSON 到订阅 URL，HTTP 2xx 视为成功；失败重试 3 次（0.5s/1s/2s 退避）。
事件类型：resume.parsed / match.evaluated / interview.completed。
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import threading
import time
import urllib.request
import urllib.error
import uuid
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.webhook import WebhookSubscription

logger = logging.getLogger(__name__)

VALID_EVENTS = {"resume.parsed", "match.evaluated", "interview.completed"}
RETRY_COUNTS = 3
BACKOFF_SECONDS = [0.5, 1.0, 2.0]


def _sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _is_private_ip(ip_str: str) -> bool:
    """判断 IP 是否为内网/环回/链路本地/保留/组播等不可对外投递的地址。"""
    try:
        ip = ipaddress.ip_address(str(ip_str).split("%")[0])
    except ValueError:
        return True  # 解析失败按危险地址处理
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_delivery_url(url: str) -> None:
    """SSRF 防护：拒绝向内网/环回/链路本地等私网地址投递 webhook。

    攻击者若能把订阅 URL 指向内部服务（如 169.254.169.254 元数据、内网管理后台），
    服务器会在每次事件时向其 POST，造成 SSRF。订阅与投递两处都校验。
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("url 缺少有效主机名")
    try:
        ip = ipaddress.ip_address(host)
        if _is_private_ip(host):
            raise ValueError(f"url 指向内网/保留地址 {host}，禁止投递")
        return
    except ValueError:
        pass  # 非 IP 字面量，按域名解析后校验
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"url 域名无法解析: {host}") from exc
    for info in infos:
        ip_str = info[4][0]
        if _is_private_ip(ip_str):
            raise ValueError(f"url 解析到内网地址 {ip_str}，禁止投递")


def subscribe_webhook(
    db: Session,
    *,
    api_key_id: int,
    tenant_id: int,
    event: str,
    url: str,
    secret: str = "",
    allow_private: bool = False,
) -> WebhookSubscription:
    if event not in VALID_EVENTS:
        raise ValueError(f"不支持的事件类型 {event}，可选 {sorted(VALID_EVENTS)}")
    if not url.startswith("https://") and not url.startswith("http://"):
        raise ValueError("url 必须为 http(s):// 地址")
    if not allow_private:
        try:
            _validate_delivery_url(url)
        except ValueError:
            raise
    sub = WebhookSubscription(
        api_key_id=api_key_id,
        tenant_id=tenant_id,
        event=event,
        url=url,
        secret=secret or "",
        status="active",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def deliver_webhook(sub: WebhookSubscription, payload: dict, *, allow_private: bool = False) -> bool:
    """同步投递一条事件到订阅 URL，失败按退避重试 RETRY_COUNTS 次。返回是否成功。

    防重放：每条投递生成唯一 event_id 与 timestamp，一并写入签名 body 并以头下发；
    订阅方可用 X-Webhook-Id 去重、用 X-Webhook-Timestamp 拒绝陈旧重放。
    """
    if not allow_private:
        try:
            _validate_delivery_url(sub.url)
        except ValueError as exc:
            logger.warning("webhook 投递被 SSRF 防护拦截 sub_id=%s url=%s: %s", sub.id, sub.url, exc)
            return False
    delivery_id = uuid.uuid4().hex
    timestamp = str(int(time.time()))
    body = {"event_id": delivery_id, "timestamp": timestamp}
    body.update(payload if isinstance(payload, dict) else {"data": payload})
    raw_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    signature = _sign(sub.secret or "", raw_body)
    last_error: Exception | None = None
    for attempt in range(1, RETRY_COUNTS + 1):
        req = urllib.request.Request(
            sub.url,
            data=raw_body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "recruit-ai-webhook/1.0",
                "X-Webhook-Signature": signature,
                "X-Webhook-Event": sub.event,
                "X-Webhook-Id": delivery_id,
                "X-Webhook-Timestamp": timestamp,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < RETRY_COUNTS:
            time.sleep(BACKOFF_SECONDS[attempt - 1])
    logger.warning("webhook 投递失败 sub_id=%s event=%s error=%s", sub.id, sub.event, last_error)
    return False


def publish_event(db: Session, *, api_key_id: int, event: str, payload: dict) -> int:
    """找到该 Key 对应事件的 active 订阅，异步投递。返回触发投递数。"""
    subs = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.api_key_id == api_key_id,
            WebhookSubscription.event == event,
            WebhookSubscription.status == "active",
        )
        .all()
    )
    for sub in subs:
        body = {"event": event, "data": payload}
        threading.Thread(target=deliver_webhook, args=(sub, body), daemon=True).start()
    return len(subs)


def validate_signature(secret: str, raw_body: bytes, signature: str | None) -> bool:
    """回调侧校验签名（供订阅方使用，示例代码含实现）。"""
    if not signature:
        return False
    expected = _sign(secret, raw_body)
    return hmac.compare_digest(expected, signature)
