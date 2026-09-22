"""E14: whose budget is a request charged to?

The limiter used `get_remote_address` for everything, so every candidate behind one shared egress
(NAT, campus network, phone hotspot) spent from a single `RATE_LIMIT_GENERAL` bucket - one person
with a chatty page could 429 everyone else on that exit, and the victims had done nothing. Now a
request carrying a valid JWT is charged to its user, while anonymous traffic (login/register,
where there is no identity yet) keeps the address bucket so brute-force protection is not weakened.

Each behaviour test builds its own `Limiter` rather than using `get_limiter()`: that instance is a
process-global singleton whose route registry and counters are shared by every app in the run, so
two tests registering a same-named probe would eat each other's budget.
"""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request

from app.core.rate_limiter import _EMPTY_CONFIG_FILE, get_user_or_remote_address
from app.core.security import create_access_token

SHARED_EGRESS_IP = "203.0.113.7"


def _request(authorization: str | None = None, client_ip: str = SHARED_EGRESS_IP) -> Request:
    headers = [(b"authorization", authorization.encode())] if authorization else []
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/probe",
            "raw_path": b"/probe",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": headers,
            "client": (client_ip, 51234),
            "server": ("testserver", 80),
        }
    )


def _client(key_func=get_user_or_remote_address, limit: str = "2/minute") -> TestClient:
    limiter = Limiter(
        key_func=key_func,
        storage_uri="memory://",
        default_limits=["100/minute"],
        headers_enabled=True,
        config_filename=str(_EMPTY_CONFIG_FILE),
    )
    app = FastAPI()
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/probe")
    @limiter.limit(limit)
    def _probe(request: Request, response: Response):  # noqa: ARG001 - 与 auth.py 里被限流的端点同形
        return {"ok": True}

    return TestClient(app)


def _bearer(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': sub})}"}


def test_a_valid_token_is_charged_to_its_user():
    assert get_user_or_remote_address(_request(_bearer("42")["Authorization"])) == "user:42"


def test_forged_or_expired_tokens_do_not_get_a_private_bucket():
    """不能靠塞一个坏 token 就换到独立额度——解不开就回到地址桶。"""
    assert get_user_or_remote_address(_request("Bearer not-a-jwt")) == SHARED_EGRESS_IP
    no_subject = create_access_token({"not_sub": "attacker"})
    assert get_user_or_remote_address(_request(f"Bearer {no_subject}")) == SHARED_EGRESS_IP
    assert get_user_or_remote_address(_request(None)) == SHARED_EGRESS_IP


def test_two_users_on_one_egress_ip_have_separate_budgets():
    """A 用满自己的额度不该让 B 的第一次请求就被拒——这正是改之前会发生的画面。"""
    client = _client()
    a = _bearer("11")
    b = _bearer("22")

    assert client.get("/probe", headers=a).status_code == 200
    assert client.get("/probe", headers=a).status_code == 200
    assert client.get("/probe", headers=a).status_code == 429
    assert client.get("/probe", headers=b).status_code == 200


def test_the_control_arm_ip_keying_shares_one_budget():
    """对照组：仍然按 IP 算（改动前的接法）时，A 用满额度后 B 的第一次就被拒。

    这条是上面那条的反证——没有它，"两个用户各自有额度"可能只是测试自己造的假象。
    """
    from slowapi.util import get_remote_address

    client = _client(key_func=get_remote_address)
    a = _bearer("11")
    b = _bearer("22")

    assert client.get("/probe", headers=a).status_code == 200
    assert client.get("/probe", headers=a).status_code == 200
    assert client.get("/probe", headers=b).status_code == 429


def test_anonymous_traffic_still_shares_the_address_bucket():
    """登录前只有地址可依据；匿名请求必须继续共用地址桶，否则爆破防护被削弱。"""
    client = _client()
    assert client.get("/probe").status_code == 200
    assert client.get("/probe").status_code == 200
    assert client.get("/probe").status_code == 429


def test_the_running_app_charges_by_this_key_function():
    """接线证明：真实 app 上挂的 limiter 用的就是它——换回 get_remote_address 时这条会红。"""
    from app.main import app

    assert app.state.limiter._key_func is get_user_or_remote_address
