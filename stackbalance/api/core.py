"""Accounts, category groups, and categories."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..services import credit as credit_service
from .deps import get_session

router = APIRouter()


def _account_out(session: Session, account: models.Account) -> schemas.AccountOut:
    total, cleared = session.execute(
        select(
            func.coalesce(func.sum(models.Transaction.amount_cents), 0),
            func.coalesce(
                func.sum(models.Transaction.amount_cents).filter(
                    models.Transaction.cleared.is_(True)
                ),
                0,
            ),
        ).where(models.Transaction.account_id == account.id)
    ).one()
    out = schemas.AccountOut.model_validate(account)
    out.balance_cents = account.opening_balance_cents + int(total)
    out.cleared_balance_cents = account.opening_balance_cents + int(cleared)
    return out


@router.get("/accounts", response_model=list[schemas.AccountOut])
def list_accounts(include_inactive: bool = False, session: Session = Depends(get_session)):
    q = select(models.Account).order_by(models.Account.name)
    if not include_inactive:
        q = q.where(models.Account.is_active.is_(True))
    return [_account_out(session, a) for a in session.execute(q).scalars()]


@router.post("/accounts", response_model=schemas.AccountOut, status_code=201)
def create_account(data: schemas.AccountIn, session: Session = Depends(get_session)):
    if session.execute(select(models.Account).where(models.Account.name == data.name)).first():
        raise HTTPException(status_code=409, detail="account name already exists")
    account = models.Account(**data.model_dump())
    session.add(account)
    session.flush()
    credit_service.ensure_payment_category(session, account)
    session.commit()
    return _account_out(session, account)


@router.get("/accounts/{account_id}", response_model=schemas.AccountOut)
def get_account(account_id: int, session: Session = Depends(get_session)):
    account = session.get(models.Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return _account_out(session, account)


@router.patch("/accounts/{account_id}", response_model=schemas.AccountOut)
def update_account(account_id: int, data: schemas.AccountUpdate,
                   session: Session = Depends(get_session)):
    account = session.get(models.Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    credit_service.ensure_payment_category(session, account)
    session.commit()
    return _account_out(session, account)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, session: Session = Depends(get_session)):
    account = session.get(models.Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    has_txns = session.execute(
        select(models.Transaction.id).where(models.Transaction.account_id == account_id).limit(1)
    ).first()
    if has_txns:
        raise HTTPException(
            status_code=409,
            detail="account has transactions; deactivate it instead (PATCH is_active=false)",
        )
    session.delete(account)
    session.commit()


@router.get("/category-groups", response_model=list[schemas.CategoryGroupOut])
def list_groups(session: Session = Depends(get_session)):
    return session.execute(
        select(models.CategoryGroup).order_by(
            models.CategoryGroup.sort_order, models.CategoryGroup.name
        )
    ).scalars().all()


@router.post("/category-groups", response_model=schemas.CategoryGroupOut, status_code=201)
def create_group(data: schemas.CategoryGroupIn, session: Session = Depends(get_session)):
    if session.execute(
        select(models.CategoryGroup).where(models.CategoryGroup.name == data.name)
    ).first():
        raise HTTPException(status_code=409, detail="group name already exists")
    group = models.CategoryGroup(**data.model_dump())
    session.add(group)
    session.commit()
    return group


@router.delete("/category-groups/{group_id}", status_code=204)
def delete_group(group_id: int, session: Session = Depends(get_session)):
    group = session.get(models.CategoryGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    if group.categories:
        raise HTTPException(status_code=409, detail="group still has categories")
    session.delete(group)
    session.commit()


@router.get("/categories", response_model=list[schemas.CategoryOut])
def list_categories(include_archived: bool = False, session: Session = Depends(get_session)):
    q = select(models.Category).order_by(models.Category.group_id, models.Category.sort_order,
                                         models.Category.name)
    if not include_archived:
        q = q.where(models.Category.is_archived.is_(False))
    return session.execute(q).scalars().all()


@router.post("/categories", response_model=schemas.CategoryOut, status_code=201)
def create_category(data: schemas.CategoryIn, session: Session = Depends(get_session)):
    if session.get(models.CategoryGroup, data.group_id) is None:
        raise HTTPException(status_code=404, detail="category group not found")
    duplicate = session.execute(
        select(models.Category).where(
            models.Category.group_id == data.group_id, models.Category.name == data.name
        )
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="category already exists in this group")
    category = models.Category(**data.model_dump())
    session.add(category)
    session.commit()
    return category


@router.patch("/categories/{category_id}", response_model=schemas.CategoryOut)
def update_category(category_id: int, data: schemas.CategoryUpdate,
                    session: Session = Depends(get_session)):
    category = session.get(models.Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="category not found")
    updates = data.model_dump(exclude_unset=True)
    if "group_id" in updates and session.get(models.CategoryGroup, updates["group_id"]) is None:
        raise HTTPException(status_code=404, detail="category group not found")
    for field, value in updates.items():
        setattr(category, field, value)
    session.commit()
    return category


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, session: Session = Depends(get_session)):
    category = session.get(models.Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="category not found")
    linked_account = session.execute(
        select(models.Account).where(models.Account.payment_category_id == category_id)
    ).scalar_one_or_none()
    if linked_account:
        raise HTTPException(
            status_code=409,
            detail=f"this is the payment envelope for credit account “{linked_account.name}”",
        )
    in_use = session.execute(
        select(models.Split.id).where(models.Split.category_id == category_id).limit(1)
    ).first()
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="category has transaction activity; archive it instead (PATCH is_archived=true)",
        )
    session.delete(category)
    session.commit()
