from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.cms.schemas import (
    GlossaryResponse,
    GlossaryDetail,
    BookItem,
    ArticleItem,
    SupportTicketCreate,
    SupportTicketResponse,
)
from app.cms.service import CMSService

router = APIRouter(prefix="/cms", tags=["CMS"])


def get_cms_service() -> CMSService:
    return CMSService()


@router.get("/glossary", response_model=GlossaryResponse)
async def get_glossary(
    letter: Optional[str] = None,
    q: Optional[str] = None,
    service: CMSService = Depends(get_cms_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_glossary(db_session=db, letter=letter, q=q)


@router.get("/glossary/{slug}", response_model=GlossaryDetail)
async def get_glossary_term(
    slug: str,
    service: CMSService = Depends(get_cms_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_glossary_term(db_session=db, slug=slug)


@router.get("/books", response_model=List[BookItem])
async def get_books(
    category: Optional[str] = None,
    service: CMSService = Depends(get_cms_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_books(db_session=db, category=category)


@router.get("/articles", response_model=List[ArticleItem])
async def get_articles(
    limit: int = 10,
    service: CMSService = Depends(get_cms_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.get_articles(db_session=db, limit=limit)


@router.post("/support/ticket", response_model=SupportTicketResponse)
async def create_support_ticket(
    ticket: SupportTicketCreate,
    service: CMSService = Depends(get_cms_service),
    db: AsyncSession = Depends(get_async_session),
):
    return await service.create_support_ticket(db_session=db, ticket=ticket)
