"""Módulo de coletores legado (Depreciado a partir da Etapa 2).

Conforme ADR 001 e Plano Diretor de Evolução Técnica:
O repositório `fin-ingestion` é a autoridade extratora única do ecossistema Fin.
O `fin-api` consome exclusivamente dados persistidos no PostgreSQL (schemas core, market,
analytics, asset_details) ou via snapshots estáticos distribuídos na CDN / Cloudflare R2.
Tarefas de coleta sob demanda são delegadas para a fila `ingestion.ingestion_task`.
"""

__deprecated__ = True
