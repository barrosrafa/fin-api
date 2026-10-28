import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_fii_property_isolation_hglg_shop_ftce():
    """
    FIN-QA-03: FIIs must have strictly isolated property portfolios.
    HGLG11 has logistics properties.
    SHOP11 has shopping center properties.
    FTCE11B is a CRI fund with 0 physical properties.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. HGLG11
        res_hglg = await client.get("/api/v1/fiis/HGLG11")
        assert res_hglg.status_code == 200
        hglg = res_hglg.json()
        assert len(hglg["properties"]) > 0
        hglg_prop_names = [p["name"] for p in hglg["properties"]]
        assert any("HGLG" in name or "Logístico" in name for name in hglg_prop_names)

        # 2. SHOP11
        res_shop = await client.get("/api/v1/fiis/SHOP11")
        assert res_shop.status_code == 200
        shop = res_shop.json()
        assert len(shop["properties"]) > 0
        shop_prop_names = [p["name"] for p in shop["properties"]]
        assert any("Shopping" in name for name in shop_prop_names)
        # Verify SHOP11 does NOT have HGLG properties!
        assert not any("HGLG" in name for name in shop_prop_names)

        # 3. FTCE11B (CRI fund)
        res_ftce = await client.get("/api/v1/fiis/FTCE11B")
        assert res_ftce.status_code == 200
        ftce = res_ftce.json()
        # Must have 0 physical properties
        assert len(ftce["properties"]) == 0, f"Expected 0 properties for FTCE11B, got {len(ftce['properties'])}"
