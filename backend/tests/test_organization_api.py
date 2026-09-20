"""Organization membership and isolation boundary tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.organization import router as organization_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.user import User


def _user(db, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com", password=hash_password("StrongP@ssw0rd"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'email': user.email, 'username': user.username})}"
    }


def test_organization_owner_controls_membership_and_workspace(db_session):
    app = FastAPI()
    app.include_router(organization_router, prefix="/organizations")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    owner = _user(db_session, "org_owner")
    member = _user(db_session, "org_member")
    outsider = _user(db_session, "org_outsider")

    with TestClient(app) as client:
        created = client.post(
            "/organizations", json={"name": "Career Team", "slug": "career-team"}, headers=_headers(owner)
        )
        assert created.status_code == 200
        organization = created.json()["data"]
        assert organization["member_role"] == "owner"

        denied = client.get(f"/organizations/{organization['id']}/members", headers=_headers(outsider))
        assert denied.status_code == 403

        added = client.post(
            f"/organizations/{organization['id']}/members",
            json={"email": member.email, "role": "member"},
            headers=_headers(owner),
        )
        assert added.status_code == 200

        member_orgs = client.get("/organizations", headers=_headers(member))
        assert member_orgs.json()["data"]["items"][0]["id"] == organization["id"]

        switched = client.put(
            "/organizations/current", json={"organization_id": organization["id"]}, headers=_headers(member)
        )
        assert switched.status_code == 200
        assert switched.json()["data"]["active_organization_id"] == organization["id"]

        listed = client.get(f"/organizations/{organization['id']}/members", headers=_headers(owner))
        assert {item["email"] for item in listed.json()["data"]["items"]} == {owner.email, member.email}

        promoted = client.put(
            f"/organizations/{organization['id']}/members/{member.id}",
            json={"role": "admin"},
            headers=_headers(owner),
        )
        assert promoted.status_code == 200
        assert promoted.json()["data"]["role"] == "admin"

        removed = client.delete(f"/organizations/{organization['id']}/members/{member.id}", headers=_headers(owner))
        assert removed.status_code == 200
        assert db_session.get(User, member.id).active_organization_id is None

        no_longer_member = client.get("/organizations", headers=_headers(member))
        assert no_longer_member.json()["data"]["items"] == []
