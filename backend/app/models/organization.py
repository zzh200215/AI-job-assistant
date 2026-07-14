"""Organization tenancy and membership models."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, String, UniqueConstraint

from app.core.database import Base
from app.utils.time_helper import utc_now


class Organization(Base):
    __tablename__ = "organization"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    owner_id = Column(BigInteger, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active")
    sso_provider = Column(String(20), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "slug": self.slug, "owner_id": self.owner_id, "status": self.status, "sso_provider": self.sso_provider}


class OrganizationMembership(Base):
    __tablename__ = "organization_membership"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_organization_membership_user"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    role = Column(String(20), nullable=False, default="member")
    status = Column(String(20), nullable=False, default="active")
    joined_at = Column(DateTime, nullable=False, default=utc_now)


class OrganizationSSOIdentity(Base):
    __tablename__ = "organization_sso_identity"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "subject", name="uq_organization_sso_subject"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(BigInteger, nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    subject = Column(String(200), nullable=False)
    user_id = Column(BigInteger, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class OrganizationSSOState(Base):
    __tablename__ = "organization_sso_state"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    state_hash = Column(String(64), nullable=False, unique=True, index=True)
    organization_id = Column(BigInteger, nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
