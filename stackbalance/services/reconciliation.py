"""Account reconciliation: confirm the register against a real statement.

Workflow: the user checks off transactions as *cleared* until the account's
cleared balance matches the statement. Finishing a reconciliation locks every
cleared transaction (reconciled=True). If a difference remains, an adjustment
transaction is created so the books match reality; it is booked to an income
category so To Be Budgeted absorbs the correction (found money raises it,
missing money lowers it).
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from . import transactions as txn_service


def cleared_balance(session: Session, account: models.Account) -> int:
    total = session.execute(
        select(func.coalesce(func.sum(models.Transaction.amount_cents), 0))
        .where(models.Transaction.account_id == account.id)
        .where(models.Transaction.cleared.is_(True))
    ).scalar_one()
    return account.opening_balance_cents + int(total)


def _default_adjustment_category(session: Session) -> int | None:
    category = session.execute(
        select(models.Category)
        .where(models.Category.is_income.is_(True), models.Category.is_archived.is_(False))
        .order_by(models.Category.id)
        .limit(1)
    ).scalar_one_or_none()
    return category.id if category else None


def reconcile(session: Session, account: models.Account,
              data: schemas.ReconcileIn) -> schemas.ReconcileResult:
    balance = cleared_balance(session, account)
    difference = data.statement_balance_cents - balance

    adjustment = None
    if difference != 0:
        category_id = data.adjustment_category_id
        if category_id is not None:
            if session.get(models.Category, category_id) is None:
                raise HTTPException(status_code=404, detail="adjustment category not found")
        else:
            category_id = _default_adjustment_category(session)
        adjustment = txn_service.create_transaction(
            session,
            schemas.TransactionIn(
                account_id=account.id,
                date=date.today(),
                payee="Reconciliation Balance Adjustment",
                memo=f"statement balance {data.statement_balance_cents} vs cleared {balance}",
                amount_cents=difference,
                cleared=True,
                category_id=category_id,
            ),
        )

    # Lock everything cleared (including the adjustment just created).
    reconciled_count = 0
    txns = session.execute(
        select(models.Transaction).where(
            models.Transaction.account_id == account.id,
            models.Transaction.cleared.is_(True),
            models.Transaction.reconciled.is_(False),
        )
    ).scalars().all()
    for txn in txns:
        txn.reconciled = True
        reconciled_count += 1

    account.last_reconciled_at = models.utcnow()
    account.last_reconciled_balance_cents = data.statement_balance_cents
    session.commit()

    return schemas.ReconcileResult(
        reconciled_count=reconciled_count,
        adjustment_cents=difference,
        adjustment_transaction=(
            schemas.TransactionOut.model_validate(adjustment) if adjustment else None
        ),
    )
