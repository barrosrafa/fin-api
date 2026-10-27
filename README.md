# ⚡ fin-api — Unified Financial Backend & Background Async Worker

Repositório central do backend de alta performance do ecossistema **fin** (plataforma analítica e transacional de investimentos). Unifica a **API HTTP (FastAPI)** e o **Worker de Tarefas Assíncronas (ARQ)** em uma única base de código em Python 3.12+, conectada nativamente ao **`fin-db`** no **PostgreSQL 18 / TimescaleDB (Neon Serverless)** e **Redis 7+**.

---

## 🏛️ Arquitetura & O Princípio Sagrado

```
                              ┌────────────────────────────────────────┐
                              │            CLIENTES / FRONTEND         │
                              └────────────────────┬───────────────────┘
                                                   │ HTTPS (Bearer JWT)
                                                   ▼
                              ┌────────────────────────────────────────┐
                              │               API HTTP                 │
                              │           FastAPI (Uvicorn)            │
                              │     [market]  [portfolio]  [billing]   │
                              └───────────┬────────────────┬───────────┘
                                          │                │ Enqueue Job
                   Cache Hit / Fast Reads │                │ (Stale-while-revalidate)
                                          ▼                ▼
                              ┌────────────────────────────────────────┐
                              │                 REDIS                  │
                              │   • Cache de Cotações e Indicadores    │
                              │   • TickerCatalog O(1) (B3/CVM)        │
                              │   • Filas ARQ (high, default, batch)   │
                              │   • Circuit Breakers & Rate Limits     │
                              └───────────▲────────────────┬───────────┘
                                          │                │ Dequeue Task
                            Cache Warm-up │                ▼
                              ┌───────────┴────────────────────────────┐
                              │           WORKER ASSÍNCRONO            │
                              │                  ARQ                   │
                              │    • Cron Jobs periódicos              │
                              │    • Coletas sob demanda               │
                              │    • 12 Adaptadores REA Isolados       │
                              └────────────────────┬───────────────────┘
                                                   │
                                                   ▼
                              ┌────────────────────────────────────────┐
                              │          NEON POSTGRESQL 18            │
                              │    fin-db (12 Schemas, 303 Tabelas)    │
                              └────────────────────────────────────────┘
```

### 1. API "Garçom" vs. Worker "Cozinha"
* **A API HTTP NUNCA faz scraping inline ou chamadas externas durante a requisição.** Seu papel é responder em milissegundos (< 20ms) lendo do cache Redis.
* **Leitura com *Stale-While-Revalidate*:** Se o dado estiver vencido, entrega a versão antiga imediatamente e dispara um job para a fila `high_priority` do ARQ no Redis sem bloquear o usuário.
* **Worker "Coletor e Faxineiro":** Processa as coletas, gerencia os 12 adaptadores REA, circuit breakers, rate limits, e renovação de tokens (ex.: JWT do Clube FII).

### 2. Cold-Start Híbrido em 3 Camadas
* **Camada 1 (Porteiro $O(1)$):** Valida o ticker contra o `TickerCatalog` no Redis (sincronizado diariamente com a B3/CVM). Tickers desconhecidos recebem `404 Not Found` imediato.
* **Camada 2 (Caminho Reativo):** Tickers válidos sem cache retornam `202 Accepted` com `sync_id`, enfileiram o job e permitem acompanhar o progresso via `GET /api/v1/market/{ticker}/sync-status` ou streaming SSE em `/stream`.
* **Camada 3 (Proteções):** Rate limit estrito e cache negativo (10 min) caso 3 tentativas falhem em todas as fontes.

### 3. Padrão Strategy em Billing e Auth
* **Billing:** Interface `PaymentProvider` com implementação transparente para **PIX** (QR Code base64 + Copia-e-Cola) e **Boleto** no Asaas, e checkout hospedado para **Cartão de Crédito** no MVP.
* **Auth:** Interface `AuthProvider` com `SupabaseAuthAdapter` (JWKS/HS256), sincronização *Just-In-Time* (JIT) na tabela `core.usuario` e cache de permissões no Redis (TTL 1h).

---

## 🌐 Os 12 Adaptadores REA de Ingestão

| # | Fonte | Classe / Adaptador | Especialidade & Dados Extraídos |
|---|---|---|---|
| 1 | **Status Invest** | `StatusInvestCollector` | Cotações, DRE contábil, fluxo de caixa, aluguel BTC, remuneração executiva |
| 2 | **Investidor10** | `Investidor10Collector` | Histórico de indicadores, balanços, mapa de dividendos, checklist Buy & Hold |
| 3 | **Fundamentei** | `FundamenteiCollector` | GraphQL state, segmentos geográficos e de negócio, KPIs, Reclame Aqui |
| 4 | **Fundamentus** | `FundamentusCollector` | Parser HTML leve, proventos, recompras, múltiplos clássicos |
| 5 | **Clube FII** | `ClubeFiiCollector` | GraphQL CR Data com JWT 12h, imóveis físicos, contratos, vacância, SiiLA |
| 6 | **Funds Explorer** | `FundsExplorerCollector` | Ranking 30 colunas de FIIs, DY histórico, liquidez diária |
| 7 | **FIIs.com.br** | `FiisComBrCollector` | Vue islands, agenda de proventos, competência mensal |
| 8 | **Mais Retorno** | `MaisRetornoCollector` | Fundos CVM 175 (Fundo/Classe/Subclasse), carteiras CDA, 10 métricas de risco |
| 9 | **Análise de Ações** | `AnaliseDeAcoesCollector` | Checklist dos 5 pilares, histórico, dias habituais de data-com |
| 10 | **Brick360** | `Brick360Collector` | REST v2 com score de 6 eixos, resumos de comitê IA, auditoria de gestoras |
| 11 | **ADVFN Brasil** | `AdvfnCollector` | Suportes e resistências, candlesticks, gregas e fluxo de opções |
| 12 | **ETFs Brasil** | `EtfsBrasilCollector` | ETFs B3 e EUA, taxa primária/secundária, spread NAV, 68 índices Teva/B3 |

---

## 🚀 Como Executar

### Pré-requisitos
* Python 3.12+ (gerenciado via [`uv`](https://github.com/astral-sh/uv))
* Instância do Redis 7+ rodando localmente (`redis://localhost:6379/0`) ou via Docker
* Banco de Dados PostgreSQL 18 / TimescaleDB (`fin-db`)

### 1. Instalação com `uv`
```bash
git clone https://github.com/barrosrafa/fin-api.git
cd fin-api
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env
```

### 2. Validação de Conectividade
```bash
python -m app.cli check
```

### 3. Sincronização Inicial do Catálogo de Tickers
```bash
python -m app.cli catalog-sync
```

### 4. Executando o Servidor HTTP (API)
```bash
python -m app.cli serve --port 8000 --reload
# Acesse a documentação interativa em http://localhost:8000/docs
```

### 5. Executando o Worker Assíncrono (Segundo Plano)
```bash
python -m app.cli worker
```

### 6. Execução com Docker Compose
```bash
docker compose up --build
```

---

## 🧪 Suíte de Testes Automatizados (TDD)

```bash
uv run --extra dev pytest tests/ -v
```
