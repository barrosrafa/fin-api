from typing import Annotated
from uuid import UUID
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_async_session
from app.ingestion.commands import enqueue_refresh, get_task

router = APIRouter(prefix='/ingestion', tags=['Ingestion'])


class RefreshCommand(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)


class TaskAccepted(BaseModel):
    task_id: UUID
    status: Literal['PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED']
    attempts: int
    created_at: datetime
    updated_at: datetime


class TaskStatus(TaskAccepted):
    dataset_name: str
    target_entity: str | None
    max_attempts: int
    locked_until: datetime | None


@router.post('/refresh', status_code=202, response_model=TaskAccepted)
async def refresh(command: RefreshCommand, response: Response,
                  db: Annotated[AsyncSession, Depends(get_async_session)]):
    task = await enqueue_refresh(db, command.ticker)
    response.headers['Location'] = f"/api/v1/ingestion/tasks/{task['task_id']}"
    return task


@router.get('/tasks/{task_id}', response_model=TaskStatus)
async def task_status(task_id: UUID, db: Annotated[AsyncSession, Depends(get_async_session)]):
    return await get_task(db, task_id)
