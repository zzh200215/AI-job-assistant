"""邮件发送服务。"""

from __future__ import annotations

import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    html_body: str,
) -> bool:
    """
    发送邮件。
    未配置 SMTP 时仅写入日志（开发模式）。
    返回是否发送成功。
    """
    if not settings.SMTP_HOST:
        logger.info("[EMAIL MOCK] To: %s | Subject: %s | Body: %s...", to, subject, html_body[:100])
        return True

    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


def send_verification_email(to: str, token: str) -> bool:
    """发送邮箱验证邮件。"""
    url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    html = f"""
    <h2>验证您的邮箱</h2>
    <p>请点击下方链接验证您的邮箱：</p>
    <p><a href="{url}" style="display:inline-block;padding:12px 24px;background:#409EFF;color:#fff;text-decoration:none;border-radius:6px;">验证邮箱</a></p>
    <p>或复制链接到浏览器：{url}</p>
    <p>链接 24 小时内有效。如果不是您本人操作，请忽略此邮件。</p>
    """
    return send_email(to, "验证您的邮箱 - Career Signal", html)


def send_password_reset_email(to: str, token: str) -> bool:
    """发送密码重置邮件。"""
    url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    html = f"""
    <h2>重置密码</h2>
    <p>请点击下方链接重置您的密码：</p>
    <p><a href="{url}" style="display:inline-block;padding:12px 24px;background:#409EFF;color:#fff;text-decoration:none;border-radius:6px;">重置密码</a></p>
    <p>或复制链接到浏览器：{url}</p>
    <p>链接 1 小时内有效。如果不是您本人操作，请忽略此邮件。</p>
    """
    return send_email(to, "重置密码 - Career Signal", html)
