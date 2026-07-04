import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    type: Mapped[str] = mapped_column(String(30), default="checking")  # checking|savings|cash|credit|investment|other
    opening_balance_cents: Mapped[int] = mapped_column(Integer, default=0)
    on_budget: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Credit accounts: the envelope that holds money earmarked to pay this card.
    payment_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), default=None
    )
    last_reconciled_at: Mapped[dt.datetime | None] = mapped_column(DateTime, default=None)
    last_reconciled_balance_cents: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    payment_category: Mapped["Category | None"] = relationship(foreign_keys=[payment_category_id])


class CategoryGroup(Base):
    __tablename__ = "category_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    categories: Mapped[list["Category"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("group_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("category_groups.id"))
    name: Mapped[str] = mapped_column(String(120))
    is_income: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    group: Mapped[CategoryGroup] = relationship(back_populates="categories")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    payee: Mapped[str] = mapped_column(String(200), default="")
    memo: Mapped[str] = mapped_column(Text, default="")
    # Total amount in cents: negative = outflow, positive = inflow.
    amount_cents: Mapped[int] = mapped_column(Integer)
    cleared: Mapped[bool] = mapped_column(Boolean, default=False)
    # Reconciled = confirmed against a statement; locked against edits that
    # would change the reconciled balance (amount/date/account/category).
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    import_hash: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    recurring_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_rules.id", ondelete="SET NULL"), default=None
    )
    # Transfers between own accounts are a linked pair; neither side is
    # income or spending, so reports and envelopes ignore them (except the
    # credit-card payment envelope, which they pay down).
    transfer_peer_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    account: Mapped[Account] = relationship(back_populates="transactions")
    splits: Mapped[list["Split"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )
    transfer_peer: Mapped["Transaction | None"] = relationship(
        remote_side="Transaction.id", foreign_keys=[transfer_peer_id], viewonly=True
    )

    @property
    def transfer_account_id(self) -> int | None:
        return self.transfer_peer.account_id if self.transfer_peer is not None else None


class Split(Base):
    """A slice of a transaction assigned to one category. Every transaction has
    at least one split; multi-split transactions are 'split-category' transactions."""

    __tablename__ = "splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True, default=None
    )
    amount_cents: Mapped[int] = mapped_column(Integer)
    memo: Mapped[str] = mapped_column(Text, default="")

    transaction: Mapped[Transaction] = relationship(back_populates="splits")
    category: Mapped[Category | None] = relationship()


class BudgetAllocation(Base):
    """Zero-based budgeting: money assigned to a category for a month (YYYY-MM)."""

    __tablename__ = "budget_allocations"
    __table_args__ = (UniqueConstraint("month", "category_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[str] = mapped_column(String(7), index=True)  # "2026-07"
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category] = relationship()


class RecurringRule(Base):
    __tablename__ = "recurring_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    payee: Mapped[str] = mapped_column(String(200), default="")
    memo: Mapped[str] = mapped_column(Text, default="")
    amount_cents: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), default=None
    )
    frequency: Mapped[str] = mapped_column(String(20))  # daily|weekly|biweekly|monthly|yearly
    interval: Mapped[int] = mapped_column(Integer, default=1)
    # Day-of-month anchor so "every 31st" clamps to short months without drifting.
    anchor_day: Mapped[int | None] = mapped_column(Integer, default=None)
    next_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date, default=None)
    auto_post: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    account: Mapped[Account] = relationship()
    category: Mapped[Category | None] = relationship()


class SinkingFund(Base):
    """A savings goal funded over time through a linked category envelope."""

    __tablename__ = "sinking_funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    target_cents: Mapped[int] = mapped_column(Integer)
    target_date: Mapped[dt.date | None] = mapped_column(Date, default=None)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    category: Mapped[Category] = relationship()
