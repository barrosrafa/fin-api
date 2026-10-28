import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_rent3_return_within_valid_domain():
    """
    FIN-QA-02: Equity return cannot be below -100%.
    RENT3 must show mathematically valid 12M return (actual ~ -18.82%, strictly >= -100%).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/market/assets?asset_type=ACAO&limit=100")
        assert res.status_code == 200
        items = res.json()
        rent3_item = next((item for item in items if item["ticker"] == "RENT3"), None)
        assert rent3_item is not None, "RENT3 should be present in Ações"
        
        # Must be mathematically valid: strictly >= -100.0%
        assert rent3_item["change12m"] >= -100.0, f"RENT3 change12m {rent3_item['change12m']} is below -100%"
        assert rent3_item["change12m"] < 50.0
        # Check actual expected range around -18.8%
        assert -30.0 <= rent3_item["change12m"] <= 0.0, f"Expected RENT3 12M return around -18.8%, got {rent3_item['change12m']}"


@pytest.mark.asyncio
async def test_no_equity_has_return_below_minus_100():
    """
    Every ACAO in /assets must have change12m >= -100.0.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/market/assets?asset_type=ACAO&limit=200")
        assert res.status_code == 200
        items = res.json()
        for item in items:
            if item.get("change12m") is not None:
                assert item["change12m"] >= -100.0, f"Asset {item['ticker']} has invalid return: {item['change12m']}%"
