import hashlib
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas


def compute_import_hash(account_id: int, txn_date: date, amount_cents: int, payee: str) -> str:
    raw = f"{account_id}|{txn_date.isoformat()}|{amount_cents}|{payee.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _resolve_splits(data: schemas.TransactionIn | schemas.TransactionUpdate,
                    amount_cents: int) -> list[models.Split]:
    if data.splits:
        total = sum(s.amount_cents for s in data.splits)
        if total != amount_cents:
            raise HTTPException(
                status_code=422,
                detail=f"splits sum to {total} but transaction amount is {amount_cents}",
            )
        return [
            models.Split(category_id=s.category_id, amount_cents=s.amount_cents, memo=s.memo)
            for s in data.splits
        ]
    return [models.Split(category_id=data.category_id, amount_cents=amount_cents)]


def create_transaction(session: Session, data: schemas.TransactionIn,
                       import_hash: str | None = None,
                       recurring_rule_id: int | None = None) -> models.Transaction:
    if data.amount_cents is None:
        if not data.splits:
            raise HTTPException(status_code=422, detail="amount_cents or splits required")
        amount = sum(s.amount_cents for s in data.splits)
    else:
        amount = data.amount_cents

    if session.get(models.Account, data.account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")

    txn = models.Transaction(
        account_id=data.account_id,
        date=data.date,
        payee=data.payee,
        memo=data.memo,
        amount_cents=amount,
        cleared=data.cleared,
        import_hash=import_hash,
        recurring_rule_id=recurring_rule_id,
        splits=_resolve_splits(data, amount),
    )
    session.add(txn)
    session.commit()
    return txn


def update_transaction(session: Session, txn_id: int,
                       data: schemas.TransactionUpdate) -> models.Transaction:
    txn = session.get(models.Transaction, txn_id, options=[selectinload(models.Transaction.splits)])
    if txn is None:
        raise HTTPException(status_code=404, detail="transaction not found")

    for field in ("account_id", "date", "payee", "memo", "cleared"):
        value = getattr(data, field)
        if value is not None:
            setattr(txn, field, value)

    if data.amount_cents is not None:
        txn.amount_cents = data.amount_cents

    if data.splits is not None or data.category_id is not None:
        txn.splits = _resolve_splits(data, txn.amount_cents)
    elif data.amount_cents is not None and len(txn.splits) == 1:
        txn.splits[0].amount_cents = txn.amount_cents
    elif data.amount_cents is not None:
        raise HTTPException(
            status_code=422,
            detail="changing the amount of a split transaction requires new splits",
        )

    session.commit()
    return txn


def bulk_edit(session: Session, edit: schemas.BulkEdit) -> schemas.BulkEditResult:
    txns = (
        session.execute(
            select(models.Transaction)
            .where(models.Transaction.id.in_(edit.ids))
            .options(selectinload(models.Transaction.splits))
        )
        .scalars()
        .all()
    )
    matched = len(txns)

    if edit.delete:
        for txn in txns:
            session.delete(txn)
        session.commit()
        return schemas.BulkEditResult(matched=matched, updated=0, deleted=matched)

    if edit.set_account_id is not None and session.get(models.Account, edit.set_account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    if edit.set_category_id is not None and session.get(models.Category, edit.set_category_id) is None:
        raise HTTPException(status_code=404, detail="category not found")

    updated = 0
    for txn in txns:
        changed = False
        if edit.set_payee is not None:
            txn.payee, changed = edit.set_payee, True
        if edit.set_memo is not None:
            txn.memo, changed = edit.set_memo, True
        if edit.set_cleared is not None:
            txn.cleared, changed = edit.set_cleared, True
        if edit.set_account_id is not None:
            txn.account_id, changed = edit.set_account_id, True
        if edit.set_category_id is not None:
            txn.splits = [
                models.Split(category_id=edit.set_category_id, amount_cents=txn.amount_cents)
            ]
            changed = True
        if changed:
            updated += 1
    session.commit()
    return schemas.BulkEditResult(matched=matched, updated=updated, deleted=0)
