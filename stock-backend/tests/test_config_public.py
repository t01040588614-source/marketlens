import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_firebase_public_not_configured(client: AsyncClient):
    res = await client.get("/api/v1/config/firebase-public")
    assert res.status_code == 404
