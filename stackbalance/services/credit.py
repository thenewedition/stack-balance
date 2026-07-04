"""Credit card payment handling.

Every credit account gets a payment envelope (a category in the "Credit Card
Payments" group). The envelope's available balance answers "how much can I
safely pay toward this card?":

- Spending on the card from a budgeted envelope moves that money into the
  payment envelope (the cash is still in your checking account, but it is now
  earmarked for the card bill). A refund on the card moves money back out.
- Recording a payment (a transfer checking -> card) spends the envelope down.
- You can also assign to the payment envelope directly, e.g. to pay down a
  pre-existing balance.

Uncategorized card transactions move nothing — there is no envelope to take
the money from — matching the rule that only budgeted spending is covered.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models

PAYMENT_GROUP_NAME = "Credit Card Payments"


def ensure_payment_category(session: Session, account: models.Account) -> None:
    """Give a credit account its payment envelope (idempotent)."""
    if account.type != "credit" or account.payment_category_id is not None:
        return
    group = session.execute(
        select(models.CategoryGroup).where(models.CategoryGroup.name == PAYMENT_GROUP_NAME)
    ).scalar_one_or_none()
    if group is None:
        group = models.CategoryGroup(name=PAYMENT_GROUP_NAME, sort_order=-1)
        session.add(group)
        session.flush()
    category = session.execute(
        select(models.Category).where(
            models.Category.group_id == group.id, models.Category.name == account.name
        )
    ).scalar_one_or_none()
    if category is None:
        category = models.Category(group_id=group.id, name=account.name)
        session.add(category)
        session.flush()
    account.payment_category_id = category.id


def ensure_all_payment_categories(session: Session) -> None:
    """Startup hook: provision envelopes for credit accounts created before
    this feature existed."""
    accounts = session.execute(
        select(models.Account).where(
            models.Account.type == "credit",
            models.Account.payment_category_id.is_(None),
        )
    ).scalars().all()
    for account in accounts:
        ensure_payment_category(session, account)
    if accounts:
        session.commit()


def payment_category_ids(session: Session) -> dict[int, int]:
    """{payment_category_id: account_id} for all linked credit accounts."""
    rows = session.execute(
        select(models.Account.payment_category_id, models.Account.id)
        .where(models.Account.payment_category_id.is_not(None))
    ).all()
    return {category_id: account_id for category_id, account_id in rows}


def _month_filter(column_expr, up_to_month: str | None, month: str | None):
    if month is not None:
        return column_expr == month
    return column_expr <= up_to_month


def earmark_adjustments(session: Session, up_to_month: str | None = None,
                        month: str | None = None) -> dict[int, int]:
    """Activity adjustments for payment envelopes, keyed by category id.

    adjustment = -(categorized, non-transfer split amounts on the card)
                 - (transfer amounts on the card)

    Card spending splits are negative, so the first term is positive
    (money earmarked in). A payment is a positive transfer amount on the
    card, so the second term subtracts it back out.
    """
    month_expr = func.strftime("%Y-%m", models.Transaction.date)

    spend_q = (
        select(
            models.Account.payment_category_id,
            func.coalesce(func.sum(models.Split.amount_cents), 0),
        )
        .join(models.Transaction, models.Split.transaction_id == models.Transaction.id)
        .join(models.Account, models.Transaction.account_id == models.Account.id)
        .join(models.Category, models.Split.category_id == models.Category.id)
        .where(models.Account.payment_category_id.is_not(None))
        .where(models.Account.on_budget.is_(True))
        .where(models.Transaction.transfer_peer_id.is_(None))
        .where(models.Category.is_income.is_(False))
        .where(models.Split.category_id != models.Account.payment_category_id)
        .where(_month_filter(month_expr, up_to_month, month))
        .group_by(models.Account.payment_category_id)
    )

    transfer_q = (
        select(
            models.Account.payment_category_id,
            func.coalesce(func.sum(models.Transaction.amount_cents), 0),
        )
        .join(models.Account, models.Transaction.account_id == models.Account.id)
        .where(models.Account.payment_category_id.is_not(None))
        .where(models.Account.on_budget.is_(True))
        .where(models.Transaction.transfer_peer_id.is_not(None))
        .where(_month_filter(month_expr, up_to_month, month))
        .group_by(models.Account.payment_category_id)
    )

    adjustments: dict[int, int] = {}
    for category_id, total in session.execute(spend_q):
        adjustments[category_id] = adjustments.get(category_id, 0) - int(total)
    for category_id, total in session.execute(transfer_q):
        adjustments[category_id] = adjustments.get(category_id, 0) - int(total)
    return adjustments
