-- Public serving contract for official CVM references. Ambiguous identities must
-- not silently choose one fund's balance sheet for another ticker.
CREATE OR REPLACE VIEW market.fii_reference_verified AS
WITH latest AS (
    SELECT *, dense_rank() OVER (
        PARTITION BY ticker ORDER BY data_referencia DESC, versao DESC
    ) AS recency
    FROM public_staging.stg_cvm_fii_mensal
    WHERE ticker IS NOT NULL
      AND data_referencia <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date
)
SELECT ticker, min(data_referencia) AS data_referencia, min(versao) AS versao,
       min(cnpj_fundo) AS cnpj_fundo, min(razao_social) AS razao_social,
       min(patrimonio_liquido) AS patrimonio_liquido,
       min(valor_patrimonial_cota) AS valor_patrimonial_cota,
       min(cotistas_total) AS cotistas_total
FROM latest WHERE recency = 1
GROUP BY ticker
HAVING count(DISTINCT cnpj_fundo) = 1
   AND count(DISTINCT valor_patrimonial_cota) <= 1
   AND count(DISTINCT patrimonio_liquido) <= 1;
COMMENT ON VIEW market.fii_reference_verified IS
'Latest official CVM monthly reference; ambiguous fund-to-ticker mappings excluded. Underlying publication stays in public_staging.';
DO $grants$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='fin_api_rw') THEN
        GRANT SELECT ON market.fii_reference_verified TO fin_api_rw;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='fin_ingestion_rw') THEN
        GRANT SELECT ON market.fii_reference_verified TO fin_ingestion_rw;
    END IF;
END $grants$;
