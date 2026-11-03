"""비밀번호 재설정 API (forgot → reset → login)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_password_reset_after_register(client: AsyncClient, monkeypatch):
    from app.core.config import settings
    from app.integrations import sms_client

    monkeypatch.setattr(settings, "SMS_DEMO_MODE", True)
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(sms_client, "is_configured", lambda: False)

    phone = "01088887777"
    send = await client.post("/api/v1/auth/phone/send", json={"phone": phone})
    assert send.status_code == 200, send.text
    code = send.json().get("dev_code")
    if not code:
        pytest.skip("SMS live mode without dev_code")

    verify = await client.post(
        "/api/v1/auth/phone/verify",
        json={"phone": phone, "code": code},
    )
    assert verify.status_code == 200
    token = verify.json()["verification_token"]

    email = "ResetTest@Example.com"
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": "reset_user1",
            "full_name": "리셋 테스트",
            "password": "OldPass1!",
            "phone": phone,
            "birth_date": "1990-01-01",
            "marketing_consent": False,
            "phone_verification_token": token,
            "terms_version": "2026-01",
        },
    )
    assert reg.status_code == 201, reg.text

    forgot = await client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert forgot.status_code == 200, forgot.text
    reset_token = forgot.json().get("dev_reset_token")
    assert reset_token

    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "password": "NewPass2!"},
    )
    assert reset.status_code == 200, reset.text

    old_login = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "OldPass1!"},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "NewPass2!"},
    )
    assert new_login.status_code == 200, new_login.text
    assert new_login.json().get("access_token")
