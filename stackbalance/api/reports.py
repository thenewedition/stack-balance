"""Cash flow, burn rate, and category spending reports."""

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import schemas
from ..services import reports as reports_service
from .deps import get_session

router = APIRouter()


@router.get("/reports/cash-flow", response_model=schemas.CashFlowOut)
def cash_flow(months: int = Query(default=12, ge=1, le=60),
              as_of: date | None = None,
              session: Session = Depends(get_session)):
    return reports_service.cash_flow(session, months=months, as_of=as_of)


@router.get("/reports/burn-rate", response_model=schemas.BurnRateOut)
def burn_rate(window_days: int = Query(default=30, ge=7, le=365),
              as_of: date | None = None,
              session: Session = Depends(get_session)):
    return reports_service.burn_rate(session, window_days=window_days, as_of=as_of)


@router.get("/reports/spending/{month}", response_model=list[schemas.SpendingByCategory])
def spending(month: str, session: Session = Depends(get_session)):
    if not re.fullmatch(schemas.MONTH_PATTERN, month):
        raise HTTPException(status_code=422, detail="month must look like 2026-07")
    return reports_service.spending_by_category(session, month)
