"""Zero-based budget: monthly view and allocations."""

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..services import budget as budget_service
from .deps import get_session

router = APIRouter()


def _check_month(month: str) -> str:
    if not re.fullmatch(schemas.MONTH_PATTERN, month):
        raise HTTPException(status_code=422, detail="month must look like 2026-07")
    return month


@router.get("/budget/{month}", response_model=schemas.MonthBudgetOut)
def month_budget(month: str, session: Session = Depends(get_session)):
    return budget_service.month_summary(session, _check_month(month))


@router.put("/budget/allocations", response_model=schemas.MonthBudgetOut)
def set_allocation(data: schemas.AllocationIn, session: Session = Depends(get_session)):
    category = session.get(models.Category, data.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="category not found")
    if category.is_income:
        raise HTTPException(status_code=422, detail="cannot allocate to an income category")
    budget_service.set_allocation(session, data)
    return budget_service.month_summary(session, data.month)
