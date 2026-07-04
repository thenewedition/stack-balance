"""Transaction CRUD, filtering, and bulk editing."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..services import transactions as txn_service
from ..services import transfers as transfer_service
from .deps import get_session

router = APIRouter()


@router.get("/transactions", response_model=list[schemas.TransactionOut])
def list_transactions(
    account_id: int | None = None,
    category_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    payee: str | None = None,
    cleared: bool | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    session: Session = Depends(get_session),
):
    q = (
        select(models.Transaction)
        .options(selectinload(models.Transaction.splits),
                 selectinload(models.Transaction.transfer_peer))
        .order_by(models.Transaction.date.desc(), models.Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if account_id is not None:
        q = q.where(models.Transaction.account_id == account_id)
    if category_id is not None:
        q = q.where(
            models.Transaction.id.in_(
                select(models.Split.transaction_id).where(models.Split.category_id == category_id)
            )
        )
    if start_date is not None:
        q = q.where(models.Transaction.date >= start_date)
    if end_date is not None:
        q = q.where(models.Transaction.date <= end_date)
    if payee:
        q = q.where(models.Transaction.payee.ilike(f"%{payee}%"))
    if cleared is not None:
        q = q.where(models.Transaction.cleared.is_(cleared))
    return session.execute(q).scalars().all()


@router.post("/transactions", response_model=schemas.TransactionOut, status_code=201)
def create_transaction(data: schemas.TransactionIn, session: Session = Depends(get_session)):
    return txn_service.create_transaction(session, data)


@router.get("/transactions/{txn_id}", response_model=schemas.TransactionOut)
def get_transaction(txn_id: int, session: Session = Depends(get_session)):
    txn = session.get(models.Transaction, txn_id,
                      options=[selectinload(models.Transaction.splits)])
    if txn is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return txn


@router.patch("/transactions/{txn_id}", response_model=schemas.TransactionOut)
def update_transaction(txn_id: int, data: schemas.TransactionUpdate,
                       session: Session = Depends(get_session)):
    return txn_service.update_transaction(session, txn_id, data)


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, session: Session = Depends(get_session)):
    """Deleting one side of a transfer removes both sides."""
    txn = session.get(models.Transaction, txn_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    transfer_service.delete_with_peer(session, txn)
    session.commit()


@router.post("/transactions/bulk", response_model=schemas.BulkEditResult)
def bulk_edit(edit: schemas.BulkEdit, session: Session = Depends(get_session)):
    return txn_service.bulk_edit(session, edit)


@router.post("/transfers", response_model=schemas.TransferOut, status_code=201)
def create_transfer(data: schemas.TransferIn, session: Session = Depends(get_session)):
    """Move money between your own accounts. Not income, not spending —
    reports ignore transfers, and a transfer into a credit account pays
    down that card's payment envelope."""
    out_txn, in_txn = transfer_service.create_transfer(session, data)
    return schemas.TransferOut(
        from_transaction=schemas.TransactionOut.model_validate(out_txn),
        to_transaction=schemas.TransactionOut.model_validate(in_txn),
    )
