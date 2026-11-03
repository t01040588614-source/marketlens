import pytest
from app.services.phone_verification import (
    consume_verification_token,
    normalize_phone,
    send_verification_code,
    verify_code,
)


def test_normalize_phone():
    assert normalize_phone("010-1234-5678") == "01012345678"
    assert normalize_phone("+82 10 1234 5678") == "01012345678"


def test_normalize_phone_invalid():
    with pytest.raises(ValueError):
        normalize_phone("12345")


def test_send_and_verify_flow(monkeypatch):
    from app.core.config import settings
    from app.integrations import sms_client
    from app.services import phone_verification as pv

    monkeypatch.setattr(settings, "SMS_DEMO_MODE", True)
    monkeypatch.setattr(sms_client, "is_configured", lambda: False)

    send_verification_code("01099998888")
    code = pv._pending["01099998888"][0]
    verified = verify_code("01099998888", code)
    token = verified["verification_token"]
    assert consume_verification_token("01099998888", token)
    assert not consume_verification_token("01099998888", token)
