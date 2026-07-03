"""Sinking funds tracker."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..services import sinking as sinking_service
from .deps import get_session

router = APIRouter()


@router.get("/sinking-funds", response_model=list[schemas.SinkingFundOut])
def list_funds(session: Session = Depends(get_session)):
    funds = session.execute(
        select(models.SinkingFund).order_by(models.SinkingFund.name)
    ).scalars().all()
    return [sinking_service.fund_status(session, f) for f in funds]


@router.post("/sinking-funds", response_model=schemas.SinkingFundOut, status_code=201)
def create_fund(data: schemas.SinkingFundIn, session: Session = Depends(get_session)):
    category = session.get(models.Category, data.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="category not found")
    if category.is_income:
        raise HTTPException(status_code=422, detail="link a spending category, not income")
    if session.execute(
        select(models.SinkingFund).where(models.SinkingFund.name == data.name)
    ).first():
        raise HTTPException(status_code=409, detail="fund name already exists")
    fund = models.SinkingFund(**data.model_dump())
    session.add(fund)
    session.commit()
    return sinking_service.fund_status(session, fund)


@router.get("/sinking-funds/{fund_id}", response_model=schemas.SinkingFundOut)
def get_fund(fund_id: int, session: Session = Depends(get_session)):
    fund = session.get(models.SinkingFund, fund_id)
    if fund is None:
        raise HTTPException(status_code=404, detail="fund not found")
    return sinking_service.fund_status(session, fund)


@router.patch("/sinking-funds/{fund_id}", response_model=schemas.SinkingFundOut)
def update_fund(fund_id: int, data: schemas.SinkingFundUpdate,
                session: Session = Depends(get_session)):
    fund = session.get(models.SinkingFund, fund_id)
    if fund is None:
        raise HTTPException(status_code=404, detail="fund not found")
    updates = data.model_dump(exclude_unset=True)
    if "category_id" in updates and session.get(models.Category, updates["category_id"]) is None:
        raise HTTPException(status_code=404, detail="category not found")
    for field, value in updates.items():
        setattr(fund, field, value)
    session.commit()
    return sinking_service.fund_status(session, fund)


@router.delete("/sinking-funds/{fund_id}", status_code=204)
def delete_fund(fund_id: int, session: Session = Depends(get_session)):
    fund = session.get(models.SinkingFund, fund_id)
    if fund is None:
        raise HTTPException(status_code=404, detail="fund not found")
    session.delete(fund)
    session.commit()
