"""Auto-categorization rules: payee -> category memory."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..services import autocat as autocat_service
from .deps import get_session

router = APIRouter()


@router.get("/categorization-rules", response_model=list[schemas.CategorizationRuleOut])
def list_rules(session: Session = Depends(get_session)):
    return session.execute(
        select(models.CategorizationRule).order_by(models.CategorizationRule.pattern)
    ).scalars().all()


@router.post("/categorization-rules", response_model=schemas.CategorizationRuleOut,
             status_code=201)
def create_rule(data: schemas.CategorizationRuleIn, session: Session = Depends(get_session)):
    """Creates the rule; an existing rule with the same pattern and match type
    is repointed to the new category instead of erroring."""
    if session.get(models.Category, data.category_id) is None:
        raise HTTPException(status_code=404, detail="category not found")
    return autocat_service.upsert_rule(session, data.pattern, data.match_type, data.category_id)


@router.patch("/categorization-rules/{rule_id}", response_model=schemas.CategorizationRuleOut)
def update_rule(rule_id: int, data: schemas.CategorizationRuleUpdate,
                session: Session = Depends(get_session)):
    rule = session.get(models.CategorizationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    updates = data.model_dump(exclude_unset=True)
    if "match_type" in updates and updates["match_type"] not in ("exact", "contains"):
        raise HTTPException(status_code=422, detail="match_type must be 'exact' or 'contains'")
    if "category_id" in updates and session.get(models.Category, updates["category_id"]) is None:
        raise HTTPException(status_code=404, detail="category not found")
    for field, value in updates.items():
        setattr(rule, field, value)
    session.commit()
    return rule


@router.delete("/categorization-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(models.CategorizationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    session.delete(rule)
    session.commit()


@router.post("/categorization-rules/apply", response_model=schemas.ApplyRulesResult)
def apply_rules(dry_run: bool = False, session: Session = Depends(get_session)):
    """Backfill: categorize existing uncategorized transactions by payee."""
    matched = autocat_service.apply_to_existing(session, dry_run=dry_run)
    return schemas.ApplyRulesResult(matched=matched, dry_run=dry_run)
