import pytest
from app.db.session import Base, get_db
from app.main import app
from app.services.market_data import market_data
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
async_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="function", autouse=True)
async def setup_test_db():
    import app.models  # noqa: F401 — register ORM tables

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    market_data._korea_source = "fdr"
    market_data._us_source = "yahoo"
    market_data._cache = {
        "005930": {
            "symbol": "005930",
            "name": "삼성전자",
            "price": 71500,
            "change": 1500,
            "change_percent": 2.14,
            "volume": 15234567,
            "market": "KOSPI",
            "type": "korea",
            "sector": "기술",
            "pe_ratio": 15.3,
            "market_cap": 400000000000000,
        },
        "AAPL": {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "price": 227.52,
            "change": 3.45,
            "change_percent": 1.54,
            "volume": 52345678,
            "exchange": "NASDAQ",
            "currency": "USD",
            "type": "us",
        },
    }

    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
