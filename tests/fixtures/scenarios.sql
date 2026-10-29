-- Synthetic scenarios ONLY for the disposable fin_ci database.
-- These are test inputs, not market facts and must never be loaded into production.

-- Cover industrial/bank financial rendering even when the public source has no snapshots.
INSERT INTO analytics.demonstrativo_snapshot_fundamentus
(id_emissor, data_balanco_processado, is_instituicao_financeira, ativo_total,
 patrimonio_liquido, receita_liquida_12m, ebit_12m, carteira_credito,
 depositos_totais, resultado_intermediacao_12m)
SELECT id_emissor, DATE '2026-09-30', ticker = 'ITUB4', 1000000, 300000,
       200000, 50000, 600000, 500000, 70000
FROM core.ativo WHERE ticker IN ('PETR4', 'ITUB4');

UPDATE analytics.indicador_fundamentalista SET ev_ebitda = 4.5
WHERE id_ativo IN (SELECT id_ativo FROM core.ativo WHERE ticker = 'PETR4');

-- Domain regression: an equity lost 18.82% over the last year, with valid OHLC.
UPDATE market.cotacao_diaria SET
    preco_abertura = CASE WHEN data_pregao >= DATE '2026-10-01' THEN 81.18 ELSE 100 END,
    preco_maximo = CASE WHEN data_pregao >= DATE '2026-10-01' THEN 81.18 ELSE 100 END,
    preco_minimo = CASE WHEN data_pregao >= DATE '2026-10-01' THEN 81.18 ELSE 100 END,
    preco_fechamento = CASE WHEN data_pregao >= DATE '2026-10-01' THEN 81.18 ELSE 100 END,
    preco_ajustado = CASE WHEN data_pregao >= DATE '2026-10-01' THEN 81.18 ELSE 100 END
WHERE id_ativo IN (SELECT id_ativo FROM core.ativo WHERE ticker = 'RENT3');

-- Backtest contract: four assets have full, deterministic history on CDI dates.
DELETE FROM market.cotacao_diaria
WHERE id_ativo IN (SELECT id_ativo FROM core.ativo WHERE ticker IN ('BLFT11','DEBB11','BOVA11','IVVB11'));
INSERT INTO market.cotacao_diaria
(id_ativo, data_pregao, preco_abertura, preco_maximo, preco_minimo, preco_fechamento, preco_ajustado, volume_total)
SELECT a.id_ativo, s.data_referencia,
       100 + (s.data_referencia - DATE '2024-01-01')::numeric / 100,
       101 + (s.data_referencia - DATE '2024-01-01')::numeric / 100,
        99 + (s.data_referencia - DATE '2024-01-01')::numeric / 100,
       100 + (s.data_referencia - DATE '2024-01-01')::numeric / 100,
       100 + (s.data_referencia - DATE '2024-01-01')::numeric / 100, 1000000
FROM core.ativo a CROSS JOIN market.benchmark_serie s
WHERE a.ticker IN ('BLFT11','DEBB11','BOVA11','IVVB11')
  AND s.id_benchmark = 1 AND s.data_referencia BETWEEN DATE '2024-01-02' AND DATE '2026-10-26';
