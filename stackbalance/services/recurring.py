"""Recurring transaction engine.

Rules hold a schedule (frequency + interval + next_date). Running the engine
materializes real transactions for every occurrence that is due (next_date <=
today), advancing next_date as it goes. Monthly/yearly rules keep an anchor day
so "the 31st" clamps to short months without permanently drifting to the 28th.
"""

import calendar
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from . import transactions as txn_service


def add_months(d: date, months: int, anchor_day: int | None = None) -> date:
    month_index = d.year * 12 + (d.month - 1) + months
    year, month = divmod(month_index, 12)
    month += 1
    day = anchor_day or d.day
    day = min(day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def advance(rule: models.RecurringRule, current: date) -> date:
    if rule.frequency == "daily":
        return current + timedelta(days=rule.interval)
    if rule.frequency == "weekly":
        return current + timedelta(weeks=rule.interval)
    if rule.frequency == "biweekly":
        return current + timedelta(weeks=2 * rule.interval)
    if rule.frequency == "monthly":
        return add_months(current, rule.interval, rule.anchor_day)
    if rule.frequency == "yearly":
        return add_months(current, 12 * rule.interval, rule.anchor_day)
    raise ValueError(f"unknown frequency {rule.frequency!r}")


def run_due(session: Session, as_of: date | None = None,
            rule_id: int | None = None) -> list[models.Transaction]:
    """Post transactions for all due occurrences. Catch-up safe: a rule that is
    three periods overdue posts three transactions."""
    as_of = as_of or date.today()
    q = select(models.RecurringRule).where(
        models.RecurringRule.is_active.is_(True),
        models.RecurringRule.next_date <= as_of,
    )
    if rule_id is not None:
        q = q.where(models.RecurringRule.id == rule_id)

    posted: list[models.Transaction] = []
    for rule in session.execute(q).scalars().all():
        # Hard stop guards a pathological rule from looping forever.
        for _ in range(1000):
            if rule.next_date > as_of:
                break
            if rule.end_date and rule.next_date > rule.end_date:
                rule.is_active = False
                break
            if rule.auto_post:
                txn = txn_service.create_transaction(
                    session,
                    schemas.TransactionIn(
                        account_id=rule.account_id,
                        date=rule.next_date,
                        payee=rule.payee or rule.name,
                        memo=rule.memo,
                        amount_cents=rule.amount_cents,
                        category_id=rule.category_id,
                    ),
                    recurring_rule_id=rule.id,
                )
                posted.append(txn)
            rule.next_date = advance(rule, rule.next_date)
    session.commit()
    return posted
