"""Recurring transaction rules and the engine that posts them."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..services import recurring as recurring_service
from .deps import get_session

router = APIRouter()


@router.get("/recurring", response_model=list[schemas.RecurringOut])
def list_rules(include_inactive: bool = False, session: Session = Depends(get_session)):
    q = select(models.RecurringRule).order_by(models.RecurringRule.next_date)
    if not include_inactive:
        q = q.where(models.RecurringRule.is_active.is_(True))
    return session.execute(q).scalars().all()


@router.post("/recurring", response_model=schemas.RecurringOut, status_code=201)
def create_rule(data: schemas.RecurringIn, session: Session = Depends(get_session)):
    if session.get(models.Account, data.account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    if data.category_id is not None and session.get(models.Category, data.category_id) is None:
        raise HTTPException(status_code=404, detail="category not found")
    rule = models.RecurringRule(**data.model_dump())
    if rule.frequency in ("monthly", "yearly"):
        rule.anchor_day = data.next_date.day
    session.add(rule)
    session.commit()
    return rule


@router.patch("/recurring/{rule_id}", response_model=schemas.RecurringOut)
def update_rule(rule_id: int, data: schemas.RecurringUpdate,
                session: Session = Depends(get_session)):
    rule = session.get(models.RecurringRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(rule, field, value)
    if "next_date" in updates and rule.frequency in ("monthly", "yearly"):
        rule.anchor_day = rule.next_date.day
    session.commit()
    return rule


@router.delete("/recurring/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(models.RecurringRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    session.delete(rule)
    session.commit()


@router.post("/recurring/run", response_model=schemas.RecurringRunResult)
def run_engine(as_of: date | None = None, rule_id: int | None = None,
               session: Session = Depends(get_session)):
    posted = recurring_service.run_due(session, as_of=as_of, rule_id=rule_id)
    return schemas.RecurringRunResult(
        posted=len(posted),
        transactions=[schemas.TransactionOut.model_validate(t) for t in posted],
    )
