from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.macro.schemas import GovernmentAccountsResponse, CreditSystemResponse
from app.macro.service import MacroService

router = APIRouter(prefix="/macro", tags=["Macroeconomic & Public Credit Engine"])


@router.get("/government-accounts", response_model=GovernmentAccountsResponse)
async def get_government_accounts(
    limit: int = Query(36, ge=1, le=120),
    db: AsyncSession = Depends(get_async_session),
):
    """Retorna a série histórica das contas públicas do Governo Central (Receitas, Despesas, Primário e Dívida/PIB)."""
    return await MacroService.get_government_accounts(db, limit=limit)


@router.get("/credit-system", response_model=CreditSystemResponse)
async def get_credit_system(
    limit: int = Query(36, ge=1, le=120),
    db: AsyncSession = Depends(get_async_session),
):
    """Retorna os indicadores do Sistema Financeiro Nacional: Poupança, Inadimplência PF/PJ, Estoque de Crédito e TCR."""
    return await MacroService.get_credit_system(db, limit=limit)
