"""Organization workspace and membership APIs."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_access_token, hash_password
from app.models.organization import Organization, OrganizationMembership, OrganizationSSOIdentity, OrganizationSSOState
from app.models.user import User
from app.services.audit_service import write_audit_log
from app.utils.http_errors import api_error
from app.utils.response import ERR_AUTH, ERR_PARAM, ok
from app.utils.time_helper import utc_now

router = APIRouter()
_MANAGER_ROLES = {"owner", "admin"}
_MEMBER_ROLES = {"admin", "member"}


def _membership(db: Session, organization_id: int, user_id: int) -> OrganizationMembership | None:
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
        .first()
    )


def _require_manager(db: Session, organization_id: int, user: User) -> OrganizationMembership:
    membership = _membership(db, organization_id, user.id)
    if membership is None or membership.role not in _MANAGER_ROLES:
        raise api_error(403, "需要组织管理员权限", ERR_AUTH)
    return membership


def _require_owner(db: Session, organization_id: int, user: User) -> OrganizationMembership:
    membership = _membership(db, organization_id, user.id)
    if membership is None or membership.role != "owner":
        raise api_error(403, "需要组织所有者权限", ERR_AUTH)
    return membership


def get_active_organization(
    x_organization_id: int | None = Header(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Organization:
    """Dependency for future organization-scoped resources."""
    organization_id = x_organization_id or current_user.active_organization_id
    if not organization_id:
        raise api_error(400, "请先选择组织工作区", ERR_PARAM)
    organization = db.query(Organization).filter(Organization.id == organization_id, Organization.status == "active").first()
    if not organization or not _membership(db, organization.id, current_user.id):
        raise api_error(403, "无权访问该组织工作区", ERR_AUTH)
    return organization


@router.get("", summary="List current user's organizations")
async def list_organizations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (
        db.query(Organization, OrganizationMembership)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .filter(OrganizationMembership.user_id == current_user.id, OrganizationMembership.status == "active")
        .order_by(Organization.created_at.desc())
        .all()
    )
    return ok(
        {
            "active_organization_id": current_user.active_organization_id,
            "items": [{**organization.to_dict(), "member_role": membership.role} for organization, membership in rows],
        }
    )


@router.post("", summary="Create an organization workspace")
async def create_organization(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    name = str(payload.get("name") or "").strip()
    slug = re.sub(r"[^a-z0-9-]+", "-", str(payload.get("slug") or name).strip().lower()).strip("-")
    if not name or not slug or len(name) > 100 or len(slug) > 80:
        raise api_error(400, "组织名称或标识不合法", ERR_PARAM)
    if db.query(Organization).filter(Organization.slug == slug).first():
        raise api_error(409, "组织标识已存在", ERR_PARAM)

    organization = Organization(name=name, slug=slug, owner_id=current_user.id)
    db.add(organization)
    db.flush()
    db.add(OrganizationMembership(organization_id=organization.id, user_id=current_user.id, role="owner"))
    current_user.active_organization_id = organization.id
    db.commit()
    db.refresh(organization)
    write_audit_log(db, current_user, "organization.create", resource_type="organization", resource_id=str(organization.id))
    return ok({**organization.to_dict(), "member_role": "owner"}, message="组织工作区已创建")


@router.put("/current", summary="Switch current organization workspace")
async def switch_organization(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    organization_id = int(payload.get("organization_id") or 0)
    if not _membership(db, organization_id, current_user.id):
        raise api_error(403, "无权切换至该组织", ERR_AUTH)
    current_user.active_organization_id = organization_id
    db.commit()
    return ok({"active_organization_id": organization_id})


@router.get("/{organization_id}/members", summary="List organization members")
async def list_members(organization_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_manager(db, organization_id, current_user)
    rows = (
        db.query(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .filter(OrganizationMembership.organization_id == organization_id, OrganizationMembership.status == "active")
        .order_by(OrganizationMembership.joined_at.asc())
        .all()
    )
    return ok({"items": [{"user_id": user.id, "username": user.username, "email": user.email, "role": member.role} for member, user in rows]})


@router.post("/{organization_id}/members", summary="Add an existing user to organization")
async def add_member(organization_id: int, payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_manager(db, organization_id, current_user)
    email = str(payload.get("email") or "").strip().lower()
    role = str(payload.get("role") or "member").strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or role not in _MEMBER_ROLES:
        raise api_error(400, "成员邮箱或角色不合法", ERR_PARAM)
    membership = _membership(db, organization_id, user.id)
    if membership:
        raise api_error(409, "该用户已是组织成员", ERR_PARAM)
    db.add(OrganizationMembership(organization_id=organization_id, user_id=user.id, role=role))
    db.commit()
    write_audit_log(db, current_user, "organization.member_add", resource_type="organization", resource_id=str(organization_id), detail={"user_id": user.id, "role": role})
    return ok({"user_id": user.id, "role": role}, message="组织成员已添加")


@router.put("/{organization_id}/members/{user_id}", summary="Change an organization member role")
async def change_member_role(
    organization_id: int,
    user_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_owner(db, organization_id, current_user)
    role = str(payload.get("role") or "").strip().lower()
    membership = _membership(db, organization_id, user_id)
    if membership is None or membership.role == "owner" or role not in _MEMBER_ROLES:
        raise api_error(400, "成员或角色不合法", ERR_PARAM)
    if membership.role == role:
        return ok({"user_id": user_id, "role": role}, message="成员角色未变化")
    previous_role = membership.role
    membership.role = role
    db.commit()
    write_audit_log(
        db,
        current_user,
        "organization.member_role_change",
        resource_type="organization",
        resource_id=str(organization_id),
        detail={"user_id": user_id, "previous_role": previous_role, "role": role},
    )
    return ok({"user_id": user_id, "role": role}, message="成员角色已更新")


@router.delete("/{organization_id}/members/{user_id}", summary="Remove an organization member")
async def remove_member(
    organization_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    actor_membership = _require_manager(db, organization_id, current_user)
    membership = _membership(db, organization_id, user_id)
    if membership is None or membership.role == "owner":
        raise api_error(400, "无法移除该成员", ERR_PARAM)
    if actor_membership.role != "owner" and membership.role == "admin":
        raise api_error(403, "组织管理员不能移除其他管理员", ERR_AUTH)
    membership.status = "removed"
    user = db.get(User, user_id)
    if user is not None and user.active_organization_id == organization_id:
        user.active_organization_id = None
    db.commit()
    write_audit_log(
        db,
        current_user,
        "organization.member_remove",
        resource_type="organization",
        resource_id=str(organization_id),
        detail={"user_id": user_id, "role": membership.role},
    )
    return ok(message="成员已移除")


@router.put("/{organization_id}/sso", summary="Configure organization SSO provider")
async def configure_sso(organization_id: int, payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_manager(db, organization_id, current_user)
    provider = str(payload.get("provider") or "").strip().lower()
    if provider not in {"", "feishu"}:
        raise api_error(400, "仅支持飞书 SSO", ERR_PARAM)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise api_error(404, "组织不存在", ERR_PARAM)
    organization.sso_provider = provider or None
    db.commit()
    write_audit_log(db, current_user, "organization.sso_configure", resource_type="organization", resource_id=str(organization_id), detail={"provider": provider or None})
    return ok(organization.to_dict())


@router.get("/sso/feishu/{slug}/start", summary="Start Feishu SSO")
async def start_feishu_sso(slug: str, db: Session = Depends(get_db)):
    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET or not settings.FEISHU_REDIRECT_URI:
        raise api_error(503, "飞书 SSO 尚未配置应用凭据", ERR_PARAM)
    organization = db.query(Organization).filter(Organization.slug == slug, Organization.status == "active").first()
    if not organization or organization.sso_provider != "feishu":
        raise api_error(404, "该组织未启用飞书 SSO", ERR_PARAM)
    nonce = secrets.token_urlsafe(24)
    state = create_access_token({"type": "feishu_sso", "organization_id": organization.id, "nonce": nonce}, expires_delta=timedelta(minutes=10))
    db.add(OrganizationSSOState(state_hash=hashlib.sha256(nonce.encode()).hexdigest(), organization_id=organization.id, provider="feishu", expires_at=utc_now() + timedelta(minutes=10)))
    db.commit()
    query = urlencode({"app_id": settings.FEISHU_APP_ID, "redirect_uri": settings.FEISHU_REDIRECT_URI, "state": state})
    return RedirectResponse(url=f"https://accounts.feishu.cn/open-apis/authen/v1/index?{query}", status_code=302)


@router.get("/sso/feishu/callback", summary="Complete Feishu SSO")
async def complete_feishu_sso(code: str = Query(..., min_length=1), state: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    state_data = decode_access_token(state)
    if not state_data or state_data.get("type") != "feishu_sso":
        raise api_error(400, "飞书 SSO 状态无效或已过期", ERR_PARAM)
    organization_id = int(state_data.get("organization_id") or 0)
    nonce = str(state_data.get("nonce") or "")
    state_record = db.query(OrganizationSSOState).filter(OrganizationSSOState.state_hash == hashlib.sha256(nonce.encode()).hexdigest(), OrganizationSSOState.organization_id == organization_id, OrganizationSSOState.provider == "feishu", OrganizationSSOState.expires_at >= utc_now()).first()
    if not nonce or state_record is None:
        raise api_error(400, "飞书 SSO 状态已被使用或已过期", ERR_PARAM)
    db.delete(state_record)
    db.commit()
    organization = db.query(Organization).filter(Organization.id == organization_id, Organization.sso_provider == "feishu").first()
    if organization is None:
        raise api_error(404, "组织未启用飞书 SSO", ERR_PARAM)
    try:
        token_response = requests.post(
            "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token",
            json={"grant_type": "authorization_code", "code": code, "client_id": settings.FEISHU_APP_ID, "client_secret": settings.FEISHU_APP_SECRET, "redirect_uri": settings.FEISHU_REDIRECT_URI},
            timeout=10,
        )
        token_response.raise_for_status()
        access_token = (token_response.json().get("data") or {}).get("access_token")
        profile_response = requests.get("https://open.feishu.cn/open-apis/authen/v1/user_info", headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        profile_response.raise_for_status()
        profile = profile_response.json().get("data") or {}
    except (requests.RequestException, ValueError, AttributeError) as exc:
        raise api_error(502, "飞书身份验证失败", ERR_PARAM) from exc
    subject = str(profile.get("union_id") or profile.get("open_id") or profile.get("user_id") or "")
    if not subject:
        raise api_error(400, "飞书未返回可用的用户标识", ERR_PARAM)
    identity = db.query(OrganizationSSOIdentity).filter(OrganizationSSOIdentity.organization_id == organization.id, OrganizationSSOIdentity.provider == "feishu", OrganizationSSOIdentity.subject == subject).first()
    user = db.get(User, identity.user_id) if identity else None
    if user is None:
        email = str(profile.get("email") or "").strip().lower()
        user = db.query(User).filter(User.email == email).first() if email else None
        if user is None:
            username = f"feishu-{subject[-12:]}".replace("_", "-")
            user = User(username=username[:50], email=email or f"{subject[:32]}@feishu.sso", password=hash_password(secrets.token_urlsafe(32)), email_verified=1)
            db.add(user)
            db.flush()
        db.add(OrganizationSSOIdentity(organization_id=organization.id, provider="feishu", subject=subject, user_id=user.id))
    if not _membership(db, organization.id, user.id):
        db.add(OrganizationMembership(organization_id=organization.id, user_id=user.id, role="member"))
    user.active_organization_id = organization.id
    db.commit()
    from app.api.auth import _create_auth_response

    return _create_auth_response(user, message="飞书登录成功")
