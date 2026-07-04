"""Zero-based budgeting math.

Model: every dollar of income becomes "To Be Budgeted" (TBB) and is assigned to
category envelopes month by month. A category's *available* balance carries
forward across months (allocated minus spending, cumulative). TBB for a month is
cumulative income minus cumulative allocations up to and including that month —
budget to zero by allocating until TBB reads 0.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from . import credit


def month_of(d) -> str:
    return d.strftime("%Y-%m")


def _split_activity_by_category(session: Session, up_to_month: str, income: bool):
    """Sum of split amounts per category for splits dated in months <= up_to_month,
    restricted to income or non-income categories. On-budget accounts only.
    Raw split sums — credit-card earmark adjustments are applied by callers."""
    month_expr = func.strftime("%Y-%m", models.Transaction.date)
    q = (
        select(models.Split.category_id, func.coalesce(func.sum(models.Split.amount_cents), 0))
        .join(models.Transaction, models.Split.transaction_id == models.Transaction.id)
        .join(models.Account, models.Transaction.account_id == models.Account.id)
        .join(models.Category, models.Split.category_id == models.Category.id)
        .where(month_expr <= up_to_month)
        .where(models.Account.on_budget.is_(True))
        .where(models.Category.is_income.is_(income))
        .group_by(models.Split.category_id)
    )
    return dict(session.execute(q).all())


def _activity_for_month(session: Session, month: str, income: bool):
    month_expr = func.strftime("%Y-%m", models.Transaction.date)
    q = (
        select(models.Split.category_id, func.coalesce(func.sum(models.Split.amount_cents), 0))
        .join(models.Transaction, models.Split.transaction_id == models.Transaction.id)
        .join(models.Account, models.Transaction.account_id == models.Account.id)
        .join(models.Category, models.Split.category_id == models.Category.id)
        .where(month_expr == month)
        .where(models.Account.on_budget.is_(True))
        .where(models.Category.is_income.is_(income))
        .group_by(models.Split.category_id)
    )
    return dict(session.execute(q).all())


def _allocations_by_category(session: Session, up_to_month: str):
    q = (
        select(
            models.BudgetAllocation.category_id,
            func.coalesce(func.sum(models.BudgetAllocation.amount_cents), 0),
        )
        .where(models.BudgetAllocation.month <= up_to_month)
        .group_by(models.BudgetAllocation.category_id)
    )
    return dict(session.execute(q).all())


def month_summary(session: Session, month: str) -> schemas.MonthBudgetOut:
    categories = (
        session.execute(
            select(models.Category)
            .join(models.CategoryGroup)
            .order_by(models.CategoryGroup.sort_order, models.CategoryGroup.name,
                      models.Category.sort_order, models.Category.name)
        )
        .scalars()
        .all()
    )

    cum_spend = _split_activity_by_category(session, month, income=False)
    cum_alloc = _allocations_by_category(session, month)
    month_spend = _activity_for_month(session, month, income=False)
    month_income = _activity_for_month(session, month, income=True)

    # Credit-card payment envelopes: card spending earmarks money in, card
    # payments (transfers) spend it down. Applied per-category only — the
    # month totals below stay raw so "spending this month" reflects real
    # spending, not internal envelope moves.
    cum_adjust = credit.earmark_adjustments(session, up_to_month=month)
    month_adjust = credit.earmark_adjustments(session, month=month)
    display_cum_spend = dict(cum_spend)
    display_month_spend = dict(month_spend)
    for category_id, adjustment in cum_adjust.items():
        display_cum_spend[category_id] = display_cum_spend.get(category_id, 0) + adjustment
    for category_id, adjustment in month_adjust.items():
        display_month_spend[category_id] = display_month_spend.get(category_id, 0) + adjustment

    month_alloc = dict(
        session.execute(
            select(
                models.BudgetAllocation.category_id,
                func.coalesce(func.sum(models.BudgetAllocation.amount_cents), 0),
            )
            .where(models.BudgetAllocation.month == month)
            .group_by(models.BudgetAllocation.category_id)
        ).all()
    )

    # Cumulative income (all income-category splits) up to this month.
    cum_income_total = sum(_split_activity_by_category(session, month, income=True).values())
    cum_alloc_total = sum(cum_alloc.values())

    rows: list[schemas.CategoryBudgetOut] = []
    for cat in categories:
        if cat.is_archived:
            continue
        if cat.is_income:
            rows.append(
                schemas.CategoryBudgetOut(
                    category_id=cat.id,
                    name=cat.name,
                    group=cat.group.name,
                    is_income=True,
                    allocated_cents=0,
                    activity_cents=month_income.get(cat.id, 0),
                    available_cents=0,
                )
            )
            continue
        available = cum_alloc.get(cat.id, 0) + display_cum_spend.get(cat.id, 0)
        rows.append(
            schemas.CategoryBudgetOut(
                category_id=cat.id,
                name=cat.name,
                group=cat.group.name,
                is_income=False,
                allocated_cents=month_alloc.get(cat.id, 0),
                activity_cents=display_month_spend.get(cat.id, 0),
                available_cents=available,
            )
        )

    return schemas.MonthBudgetOut(
        month=month,
        income_cents=sum(month_income.values()),
        allocated_cents=sum(month_alloc.values()),
        activity_cents=sum(month_spend.values()),
        to_be_budgeted_cents=cum_income_total - cum_alloc_total,
        categories=rows,
    )


def set_allocation(session: Session, data: schemas.AllocationIn) -> models.BudgetAllocation:
    alloc = session.execute(
        select(models.BudgetAllocation).where(
            models.BudgetAllocation.month == data.month,
            models.BudgetAllocation.category_id == data.category_id,
        )
    ).scalar_one_or_none()
    if alloc is None:
        alloc = models.BudgetAllocation(
            month=data.month, category_id=data.category_id, amount_cents=data.amount_cents
        )
        session.add(alloc)
    else:
        alloc.amount_cents = data.amount_cents
    session.commit()
    return alloc


def category_available(session: Session, category_id: int, up_to_month: str) -> int:
    """Envelope balance for one category through the given month."""
    spend = _split_activity_by_category(session, up_to_month, income=False).get(category_id, 0)
    alloc = _allocations_by_category(session, up_to_month).get(category_id, 0)
    adjustment = credit.earmark_adjustments(session, up_to_month=up_to_month).get(category_id, 0)
    return alloc + spend + adjustment
