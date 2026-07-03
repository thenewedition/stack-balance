"""Sinking funds: long-horizon savings goals funded through a category envelope.

The fund's saved balance is the linked category's envelope balance (everything
ever allocated to it plus activity). Progress, pace, and a suggested monthly
contribution are derived from the target amount and date.
"""

from datetime import date

from sqlalchemy.orm import Session

from .. import models, schemas
from . import budget


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def fund_status(session: Session, fund: models.SinkingFund,
                as_of: date | None = None) -> schemas.SinkingFundOut:
    as_of = as_of or date.today()
    saved = budget.category_available(session, fund.category_id, budget.month_of(as_of))
    remaining = max(fund.target_cents - saved, 0)
    percent = min(saved / fund.target_cents, 1.0) if fund.target_cents else 0.0

    months_remaining = None
    suggested = None
    on_track = None
    if fund.target_date:
        months_remaining = max(_months_between(as_of, fund.target_date), 0)
        if remaining == 0:
            suggested, on_track = 0, True
        elif months_remaining == 0:
            suggested, on_track = remaining, False
        else:
            suggested = -(-remaining // months_remaining)  # ceil division
            total_months = max(_months_between(fund.created_at.date(), fund.target_date), 1)
            elapsed = min(max(_months_between(fund.created_at.date(), as_of), 0), total_months)
            expected = fund.target_cents * elapsed // total_months
            on_track = saved >= expected

    return schemas.SinkingFundOut(
        id=fund.id,
        name=fund.name,
        category_id=fund.category_id,
        target_cents=fund.target_cents,
        target_date=fund.target_date,
        notes=fund.notes,
        saved_cents=saved,
        remaining_cents=remaining,
        percent_complete=round(percent * 100, 1),
        months_remaining=months_remaining,
        suggested_monthly_cents=suggested,
        on_track=on_track,
    )
