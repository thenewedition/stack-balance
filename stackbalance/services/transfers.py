"""Account-to-account transfers: a linked pair of transactions.

Neither side is income or spending — both stay uncategorized and reports skip
them. Paying a credit card is simply a transfer checking -> card; the credit
service picks it up to draw down the card's payment envelope.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas


def create_transfer(session: Session, data: schemas.TransferIn) -> tuple[models.Transaction, models.Transaction]:
    from_account = session.get(models.Account, data.from_account_id)
    to_account = session.get(models.Account, data.to_account_id)
    if from_account is None or to_account is None:
        raise HTTPException(status_code=404, detail="account not found")
    if from_account.id == to_account.id:
        raise HTTPException(status_code=422, detail="cannot transfer to the same account")

    out_txn = models.Transaction(
        account_id=from_account.id,
        date=data.date,
        payee=f"Transfer to {to_account.name}",
        memo=data.memo,
        amount_cents=-data.amount_cents,
        cleared=data.cleared,
        splits=[models.Split(category_id=None, amount_cents=-data.amount_cents)],
    )
    in_txn = models.Transaction(
        account_id=to_account.id,
        date=data.date,
        payee=f"Transfer from {from_account.name}",
        memo=data.memo,
        amount_cents=data.amount_cents,
        cleared=data.cleared,
        splits=[models.Split(category_id=None, amount_cents=data.amount_cents)],
    )
    session.add_all([out_txn, in_txn])
    session.flush()
    out_txn.transfer_peer_id = in_txn.id
    in_txn.transfer_peer_id = out_txn.id
    session.commit()
    return out_txn, in_txn


def sync_peer(session: Session, txn: models.Transaction) -> None:
    """Mirror date and amount onto the other side after an edit."""
    peer = session.get(models.Transaction, txn.transfer_peer_id)
    if peer is None:
        return
    peer.date = txn.date
    peer.amount_cents = -txn.amount_cents
    if len(peer.splits) == 1:
        peer.splits[0].amount_cents = -txn.amount_cents


def delete_with_peer(session: Session, txn: models.Transaction) -> None:
    if txn.transfer_peer_id is not None:
        peer = session.get(models.Transaction, txn.transfer_peer_id)
        if peer is not None:
            session.delete(peer)
    session.delete(txn)
