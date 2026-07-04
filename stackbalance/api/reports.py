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


@router.get("/reports/net-worth", response_model=schemas.NetWorthOut)
def net_worth(months: int = Query(default=12, ge=1, le=60),
              as_of: date | None = None,
              session: Session = Depends(get_session)):
    return reports_service.net_worth(session, months=months, as_of=as_of)


@router.get("/reports/category-trend/{category_id}", response_model=schemas.CategoryTrendOut)
def category_trend(category_id: int, months: int = Query(default=12, ge=1, le=60),
                   as_of: date | None = None,
                   session: Session = Depends(get_session)):
    return reports_service.category_trend(session, category_id, months=months, as_of=as_of)


@router.get("/reports/payees", response_model=list[schemas.PayeeReportRow])
def payees(months: int = Query(default=1, ge=1, le=60),
           as_of: date | None = None,
           limit: int = Query(default=15, ge=1, le=100),
           session: Session = Depends(get_session)):
    return reports_service.top_payees(session, months=months, as_of=as_of, limit=limit)
