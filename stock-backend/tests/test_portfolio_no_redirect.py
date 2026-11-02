"""/portfolio 요청이 /portfolio/ 로 리다이렉트되지 않는지 확인.

리다이렉트되면 프록시 경유 시 인증 헤더가 빠져 로그아웃됩니다.
"""

import pytest
from httpx import AsyncClient


async def _token(client: AsyncClient, monkeypatch) -> str:
    from app.core.config import settings
    from app.integrations import sms_client

    monkeypatch.setattr(settings, "SMS_DEMO_MODE", True)
    monkeypatch.setattr(sms_client, "is_configured", lambda: False)

    phone = "01055556666"
    send = await client.post("/api/v1/auth/phone/send", json={"phone": phone})
    code = send.json().get("dev_code")
    if not code:
        pytest.skip("SMS live mode without dev_code in test env")
    verify = await client.post("/api/v1/auth/phone/verify", json={"phone": phone, "code": code})
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "portfolio_test@example.com",
            "username": "portfolio_user01",
            "password": "TestPass1!",
            "phone": phone,
            "birth_date": "1990-05-15",
            "phone_verification_token": verify.json()["verification_token"],
            "terms_version": "2026-01",
        },
    )
    assert reg.status_code == 201, reg.text
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "portfolio_test@example.com", "password": "TestPass1!"},
    )
    return login.json()["access_token"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/portfolio", "/api/v1/portfolio/"])
async def test_portfolio_list_without_redirect(client: AsyncClient, monkeypatch, path: str):
    token = await _token(client, monkeypatch)
    res = await client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    assert isinstance(res.json(), list)
