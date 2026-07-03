"""Cash flow and burn-rate analytics."""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas


def cash_flow(session: Session, months: int = 12,
              as_of: date | None = None) -> schemas.CashFlowOut:
    """Per-month income vs. expense over the trailing window (on-budget accounts)."""
    as_of = as_of or date.today()
    month_expr = func.strftime("%Y-%m", models.Transaction.date)
    start_index = as_of.year * 12 + (as_of.month - 1) - (months - 1)
    start_month = f"{start_index // 12:04d}-{start_index % 12 + 1:02d}"

    rows = session.execute(
        select(
            month_expr.label("month"),
            func.sum(
                func.max(models.Transaction.amount_cents, 0)
            ).label("income"),
            func.sum(
                func.min(models.Transaction.amount_cents, 0)
            ).label("expense"),
        )
        .join(models.Account)
        .where(models.Account.on_budget.is_(True))
        .where(month_expr >= start_month)
        .where(month_expr <= as_of.strftime("%Y-%m"))
        .group_by("month")
        .order_by("month")
    ).all()
    by_month = {r.month: r for r in rows}

    out = []
    for i in range(months):
        index = start_index + i
        key = f"{index // 12:04d}-{index % 12 + 1:02d}"
        r = by_month.get(key)
        income = int(r.income or 0) if r else 0
        expense = int(r.expense or 0) if r else 0
        out.append(schemas.CashFlowMonth(
            month=key, income_cents=income, expense_cents=expense,
            net_cents=income + expense,
        ))
    return schemas.CashFlowOut(months=out)


def burn_rate(session: Session, window_days: int = 30,
              as_of: date | None = None) -> schemas.BurnRateOut:
    """Average daily spend over the window, and how long liquid funds last at
    that pace (runway)."""
    as_of = as_of or date.today()
    start = as_of - timedelta(days=window_days - 1)

    inflow, outflow = session.execute(
        select(
            func.coalesce(func.sum(func.max(models.Transaction.amount_cents, 0)), 0),
            func.coalesce(func.sum(func.min(models.Transaction.amount_cents, 0)), 0),
        )
        .join(models.Account)
        .where(models.Account.on_budget.is_(True))
        .where(models.Transaction.date >= start)
        .where(models.Transaction.date <= as_of)
    ).one()

    liquid = session.execute(
        select(func.coalesce(
            func.sum(models.Account.opening_balance_cents), 0
        ))
        .where(models.Account.on_budget.is_(True), models.Account.is_active.is_(True))
    ).scalar_one()
    liquid += session.execute(
        select(func.coalesce(func.sum(models.Transaction.amount_cents), 0))
        .join(models.Account)
        .where(models.Account.on_budget.is_(True), models.Account.is_active.is_(True))
        .where(models.Transaction.date <= as_of)
    ).scalar_one()

    daily_burn = abs(int(outflow)) // window_days
    daily_net = (int(inflow) + int(outflow)) // window_days

    runway_days = None
    runway_date = None
    if daily_burn > 0 and liquid > 0:
        runway_days = liquid // daily_burn
        runway_date = as_of + timedelta(days=runway_days)

    return schemas.BurnRateOut(
        window_days=window_days,
        total_outflow_cents=int(outflow),
        total_inflow_cents=int(inflow),
        daily_burn_cents=daily_burn,
        daily_net_cents=daily_net,
        liquid_balance_cents=int(liquid),
        runway_days=runway_days,
        runway_date=runway_date,
    )


def spending_by_category(session: Session, month: str) -> list[schemas.SpendingByCategory]:
    month_expr = func.strftime("%Y-%m", models.Transaction.date)
    rows = session.execute(
        select(
            models.Split.category_id,
            func.coalesce(models.Category.name, "Uncategorized"),
            func.sum(models.Split.amount_cents),
        )
        .join(models.Transaction, models.Split.transaction_id == models.Transaction.id)
        .join(models.Account, models.Transaction.account_id == models.Account.id)
        .outerjoin(models.Category, models.Split.category_id == models.Category.id)
        .where(month_expr == month)
        .where(models.Account.on_budget.is_(True))
        .where(func.coalesce(models.Category.is_income, False).is_(False))
        .group_by(models.Split.category_id)
        .having(func.sum(models.Split.amount_cents) < 0)
        .order_by(func.sum(models.Split.amount_cents))
    ).all()
    return [
        schemas.SpendingByCategory(category_id=r[0], name=r[1], spent_cents=int(r[2]))
        for r in rows
    ]
