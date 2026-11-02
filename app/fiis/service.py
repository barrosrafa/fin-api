from fastapi import HTTPException
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.market.quality import verified_market_text as text
from app.market.lifecycle import trading_status
from app.fiis.schemas import (
    FIIDetailResponse, FIIPropertyItem, FIIRankingItem, FIIVacancyPoint,
    FIIVacancyHistoryResponse, FIICadastralData, FIIIndicatorsData,
    FIIDividendItem, FIIDisclosureItem,
)


def number(value):
    return float(value) if value is not None else None


def format_cnpj(value):
    if not value:
        return None
    digits = "".join(filter(str.isdigit, value))
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}" if len(digits) == 14 else value


class FIIService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def get_fii_detail(self, ticker: str, db_session: Optional[AsyncSession] = None) -> FIIDetailResponse:
        if db_session is None:
            raise HTTPException(status_code=503, detail="FII data unavailable")
        t = ticker.upper()
        result = await db_session.execute(text("""
            SELECT a.id_ativo AS asset_id, a.canonical_instrument_id,
                   COALESCE(ec.nome_empresarial, a.ticker) AS razao_social,
                   COALESCE(ec.subsetor, ec.setor) AS segmento, ec.cnpj, ec.site_ri,
                   df.*, ci.status AS registry_status,
                   official.valor_patrimonial_cota AS official_vpa, official.patrimonio_liquido AS official_net_worth,
                   official.data_referencia::text AS fundamentals_date, official.cotistas_total AS official_shareholders,
                   cd.preco_fechamento AS preco, cd.data_pregao::text AS quote_date,
                   cd.volume_total, cd.variacao_percentual,
                   fhv.vacancia_fisica_pct AS vf, fhv.vacancia_financeira_pct AS vfin
            FROM core.ativo a
            LEFT JOIN core.emissor_companhia ec ON ec.id_emissor = a.id_emissor
            LEFT JOIN canonical.instrument ci ON ci.instrument_id = a.canonical_instrument_id
            LEFT JOIN asset_details.detalhe_fii df ON df.id_ativo = a.id_ativo
            LEFT JOIN LATERAL (
                SELECT preco_fechamento, data_pregao, volume_total, variacao_percentual
                FROM market.cotacao_diaria WHERE id_ativo = a.id_ativo
                ORDER BY data_pregao DESC LIMIT 1
            ) cd ON TRUE
            LEFT JOIN market.fii_reference_verified official ON official.ticker = a.ticker
                  AND official.data_referencia <= COALESCE(cd.data_pregao, CURRENT_DATE)
            LEFT JOIN LATERAL (
                SELECT vacancia_fisica_pct, vacancia_financeira_pct
                FROM asset_details.fii_historico_vacancia WHERE id_ativo = a.id_ativo
                ORDER BY data_referencia DESC LIMIT 1
            ) fhv ON TRUE
            WHERE a.ticker = :ticker AND a.tipo_ativo::text = 'FII'
        """), {"ticker": t})
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail=f"FII ticker '{t}' not found")
        price = number(row.get("preco"))
        vp = number(row.get("official_vpa"))
        pvp = price / vp if price is not None and vp is not None and vp > 0 else None
        # Stored DY and last-dividend fields have no window/event provenance. Do
        # not present them as cash income or use them in reinvestment projections.
        fields = {
            "pvp": pvp, "vp_per_share": vp,
            "net_worth": number(row.get("official_net_worth")),
            "physical_vacancy_pct": number(row.get("vf")),
            "financial_vacancy_pct": number(row.get("vfin")),
            "shares_count": None, "shareholders_count": row.get("official_shareholders"),
            "market_cap": None,
            "daily_volume": number(row.get("volume_total")), "change_1d": number(row.get("variacao_percentual")),
            "quote_datetime": row.get("quote_date"),
        }
        properties_result = await db_session.execute(text("""
            SELECT fi.id_imovel, fi.nome, fi.tipo_imovel, fi.endereco, fi.cidade, fi.uf,
                   fi.abl_total_m2, fi.classe_siila, p.participacao_pct,
                   100 - p.vacancia_fisica_pct AS occupancy_pct
            FROM asset_details.fii_imovel fi
            JOIN asset_details.fii_imovel_participacao p ON p.id_imovel = fi.id_imovel
            WHERE p.id_ativo = :asset ORDER BY fi.id_imovel
        """), {"asset": row.get("asset_id", row.get("id_ativo"))})
        properties = [FIIPropertyItem(
            id=str(p["id_imovel"]), name=p["nome"], type=p["tipo_imovel"], address=p["endereco"],
            city=p["cidade"], state=p["uf"], abl_m2=p["abl_total_m2"], occupancy_pct=p["occupancy_pct"],
            siila_standard=p["classe_siila"], fund_share_pct=p["participacao_pct"],
        ) for p in properties_result.mappings().all()]
        dividends_result = await db_session.execute(text("""
            SELECT id_provento::text, tipo_provento::text, mes_referencia,
                   data_com::text, data_ex::text, data_pagamento::text, data_anuncio::text, valor_por_acao
            FROM market.provento WHERE id_ativo = :asset
              AND fonte_provento IS NOT NULL AND payload_fonte IS NOT NULL
              AND tipo_provento::text IN ('RENDIMENTO', 'RENDIMENTO_TRIBUTADO', 'DIVIDENDO', 'JCP')
              AND data_pagamento <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date
            ORDER BY data_pagamento DESC, id_provento DESC LIMIT 1000
        """), {"asset": row.get("asset_id", row.get("id_ativo"))})
        dividends = [FIIDividendItem(
            id=d["id_provento"], type=d["tipo_provento"], reference_month=d["mes_referencia"],
            date_approval=d["data_anuncio"], date_com=d["data_com"], date_ex=d["data_ex"],
            date_payment=d["data_pagamento"], value_per_share=d["valor_por_acao"],
            yield_pct=float(d["valor_por_acao"]) / price * 100 if price else None, status="PAGO",
        ) for d in dividends_result.mappings().all()]
        # A bounded event list does not prove complete 12-month coverage.
        # Keep sourced payments in history, but do not infer annual yield or a
        # recurring monthly amount from whichever events happen to be present.
        fields["dividend_yield_12m"] = None
        disclosures_result = await db_session.execute(text("""
            SELECT document_id::text AS id, document_type, title, document_date::text,
                   published_at::text, source_url, external_id
            FROM canonical.disclosure_document
            WHERE instrument_id = :instrument AND :instrument IS NOT NULL
            ORDER BY document_date DESC LIMIT 50
        """), {"instrument": row["canonical_instrument_id"]})
        disclosures = [FIIDisclosureItem(
            document_id=d["id"], document_type=d["document_type"], title=d["title"],
            document_date=d["document_date"], published_at=d["published_at"],
            source_url=d["source_url"], external_id=d["external_id"],
        ) for d in disclosures_result.mappings().all()]
        return FIIDetailResponse(
            ticker=t, name=row["razao_social"], segment=row.get("segmento") or "Imobiliário",
            current_price=price, pvp=pvp, dividend_yield_12m=None, net_worth=fields["net_worth"],
            physical_vacancy_pct=fields["physical_vacancy_pct"], financial_vacancy_pct=fields["financial_vacancy_pct"],
            source="B3 / COTAHIST" if price is not None else None,
            quote_date=row.get("quote_date"),
            fundamentals_source="CVM / Informe mensal FII" if row.get("fundamentals_date") else None,
            fundamentals_date=row.get("fundamentals_date"), trading=trading_status(t, row.get("registry_status")),
            indicators=FIIIndicatorsData(**fields), properties=properties, disclosures=disclosures, dividends=dividends,
            cadastral=FIICadastralData(
                trading_code=t, legal_name=row["razao_social"], cnpj=format_cnpj(row.get("cnpj")),
                administrator_name=row.get("administrador"), manager_name=row.get("gestor"),
                administrator_site=row.get("site_ri"), duration_term=row.get("prazo_duracao"),
                shares_count=fields["shares_count"], shareholders_count=fields["shareholders_count"],
            ),
        )

    async def get_fiis_ranking(
        self, sort_by: str = "dy", limit: int = 50, offset: int = 0,
        search: Optional[str] = None, segment: Optional[str] = None,
        min_dy: Optional[float] = None, max_pvp: Optional[float] = None,
        max_vacancia: Optional[float] = None, db_session: Optional[AsyncSession] = None,
    ) -> tuple[List[FIIRankingItem], int]:
        if db_session is None:
            raise HTTPException(status_code=503, detail="FII ranking unavailable")
        if min_dy is not None:
            raise HTTPException(status_code=422, detail="DY filter unavailable without verified 12-month coverage")
        # All filters must be applied before LIMIT/OFFSET. Derive metrics from the
        # detail's quote and documented-payment basis, never cached legacy ratios.
        query = """
            WITH metrics AS (
                SELECT a.ticker, COALESCE(ec.nome_empresarial,a.ticker) AS name,
                    COALESCE(ec.subsetor,ec.setor,'Imobiliário') AS segment,
                    cd.preco_fechamento AS price, cd.data_pregao::text AS quote_date,
                    ci.status AS registry_status, cd.volume_total AS liquidity_daily,
                    CASE WHEN official.valor_patrimonial_cota > 0 THEN cd.preco_fechamento / official.valor_patrimonial_cota END AS pvp,
                    NULL::numeric AS dy_12m,
                    official.patrimonio_liquido AS net_worth,
                    fh.vacancia_fisica_pct AS physical_vacancy_pct,
                    fh.vacancia_financeira_pct AS financial_vacancy_pct
                FROM core.ativo a
                LEFT JOIN core.emissor_companhia ec ON ec.id_emissor=a.id_emissor
                LEFT JOIN canonical.instrument ci ON ci.instrument_id=a.canonical_instrument_id
                LEFT JOIN asset_details.detalhe_fii df ON df.id_ativo=a.id_ativo
                LEFT JOIN LATERAL (
                    SELECT * FROM market.cotacao_diaria WHERE id_ativo=a.id_ativo ORDER BY data_pregao DESC LIMIT 1
                ) cd ON TRUE
                LEFT JOIN market.fii_reference_verified official ON official.ticker = a.ticker
                  AND official.data_referencia <= COALESCE(cd.data_pregao, CURRENT_DATE)
                LEFT JOIN LATERAL (
                    SELECT * FROM asset_details.fii_historico_vacancia WHERE id_ativo=a.id_ativo ORDER BY data_referencia DESC LIMIT 1
                ) fh ON TRUE
                WHERE a.tipo_ativo::text='FII'
            ), filtered AS (
                SELECT * FROM metrics
                WHERE (CAST(:search AS text) IS NULL OR ticker ILIKE :search OR name ILIKE :search)
                  AND (CAST(:segment AS text) IS NULL OR segment ILIKE :segment)
                  AND (CAST(:max_pvp AS numeric) IS NULL OR pvp <= :max_pvp)
                  AND (CAST(:max_vacancia AS numeric) IS NULL OR physical_vacancy_pct <= :max_vacancia)
            )
        """
        params = {"search": f"%{search.strip()}%" if search and search.strip() else None,
                  "segment": f"%{segment.strip()}%" if segment and segment != "TODOS" else None,
                  "max_pvp": max_pvp, "max_vacancia": max_vacancia, "limit": limit, "offset": offset}
        total = (await db_session.execute(text(query + " SELECT count(*) FROM filtered"), params)).scalar() or 0
        order = {"dy": "ticker ASC", "pvp": "pvp ASC", "vacancia": "physical_vacancy_pct ASC", "liquidez": "liquidity_daily DESC"}.get(sort_by.lower(), "ticker ASC")
        result = await db_session.execute(text(query + " SELECT * FROM filtered ORDER BY " + order + " NULLS LAST, ticker LIMIT :limit OFFSET :offset"), params)
        rows = result.mappings().all()
        items = []
        for i, row in enumerate(rows):
            values = {k: v for k, v in dict(row).items() if k not in ("total", "registry_status")}
            values["rank"] = offset + i + 1
            values["source"] = "B3 / COTAHIST" if values.get("price") is not None else None
            values["trading"] = trading_status(row["ticker"], row.get("registry_status"))
            items.append(FIIRankingItem(**values))
        return items, total

    async def get_fii_vacancy_history(self, ticker: str, db_session: Optional[AsyncSession] = None) -> FIIVacancyHistoryResponse:
        if db_session is None:
            raise HTTPException(status_code=503, detail="Vacancy history unavailable")
        result = await db_session.execute(text("""
            SELECT data_referencia::text, vacancia_fisica_pct, vacancia_financeira_pct, abl_propria_m2, area_ocupada_m2
            FROM asset_details.fii_historico_vacancia h JOIN core.ativo a ON a.id_ativo = h.id_ativo
            WHERE a.ticker = :ticker ORDER BY data_referencia
        """), {"ticker": ticker.upper()})
        return FIIVacancyHistoryResponse(ticker=ticker.upper(), history=[FIIVacancyPoint(**dict(r)) for r in result.mappings().all()])
