from unittest.mock import MagicMock, patch

import pytest
from app.integrations import sms_client


@pytest.fixture(autouse=True)
def clear_keys(monkeypatch):
    monkeypatch.setattr(sms_client, "get_key", lambda name: "")
    monkeypatch.setattr(sms_client.settings, "SMS_DEMO_MODE", False)


def test_active_provider_auto_aligo(monkeypatch):
    def fake_get(name: str) -> str:
        return {
            "ALIGO_API_KEY": "k",
            "ALIGO_USER_ID": "u",
            "ALIGO_SENDER": "01012345678",
        }.get(name, "")

    monkeypatch.setattr(sms_client, "get_key", fake_get)
    assert sms_client.active_provider() == "aligo"
    assert sms_client.is_configured()


def test_send_aligo_success(monkeypatch):
    def fake_get(name: str) -> str:
        return {
            "SMS_PROVIDER": "aligo",
            "ALIGO_API_KEY": "k",
            "ALIGO_USER_ID": "u",
            "ALIGO_SENDER": "01011112222",
        }.get(name, "")

    monkeypatch.setattr(sms_client, "get_key", fake_get)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result_code": "1"}
    mock_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("app.integrations.sms_client.httpx.Client", return_value=mock_client):
        out = sms_client.send_sms("01012345678", "test msg")
    assert out["provider"] == "aligo"
    mock_client.post.assert_called_once()
