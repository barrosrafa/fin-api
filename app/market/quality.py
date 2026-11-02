"""Public quote boundary: a legacy row is not evidence of a market observation.

Keep original rows intact. Serve only same-identity/session/nominal-close matches
with the official landing dataset, including historical queries. Missing evidence
is NULL/empty, never a guessed price. SQL predicates stay inside lateral queries.
"""
import re
from sqlalchemy import text

VERIFIED_QUOTES = """(
    SELECT legacy.*
    FROM market.cotacao_diaria legacy
    JOIN core.ativo identity ON identity.id_ativo = legacy.id_ativo
    WHERE legacy.data_pregao <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date
      AND NOT COALESCE(legacy.is_backtest_simulado, false)
      AND legacy.preco_fechamento > 0
      AND EXISTS (
          SELECT 1 FROM market.nominal_bar official
          WHERE official.ticker = identity.ticker
            AND official.reference_date = legacy.data_pregao
            AND official.source = 'b3' AND official.currency = 'BRL'
            AND official.interval = 'day'
            AND official.close = legacy.preco_fechamento
            AND (legacy.preco_abertura IS NULL OR official.open = legacy.preco_abertura)
            AND (legacy.preco_maximo IS NULL OR official.high = legacy.preco_maximo)
            AND (legacy.preco_minimo IS NULL OR official.low = legacy.preco_minimo)
      )
)"""


def verified_market_text(statement: str):
    """Compile public read SQL through the quote evidence boundary.

    Only replace the qualified relation token, never values or bound parameters.
    Mutations must use sqlalchemy.text directly; this helper is read-only.
    """
    if not re.match(r"\s*(SELECT|WITH)\b", statement, re.I):
        raise ValueError("Verified market statements must be read-only")
    return text(re.sub(r"\bmarket\.cotacao_diaria\b", VERIFIED_QUOTES, statement))
