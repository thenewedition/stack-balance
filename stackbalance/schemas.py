import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Accounts ----------

class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = "checking"
    opening_balance_cents: int = 0
    on_budget: bool = True

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str) -> str:
        allowed = {"checking", "savings", "cash", "credit", "investment", "other"}
        if v not in allowed:
            raise ValueError(f"type must be one of {sorted(allowed)}")
        return v


class AccountUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    opening_balance_cents: int | None = None
    on_budget: bool | None = None
    is_active: bool | None = None


class AccountOut(ORMModel):
    id: int
    name: str
    type: str
    opening_balance_cents: int
    on_budget: bool
    is_active: bool
    balance_cents: int = 0
    cleared_balance_cents: int = 0


# ---------- Categories ----------

class CategoryGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class CategoryGroupOut(ORMModel):
    id: int
    name: str
    sort_order: int


class CategoryIn(BaseModel):
    group_id: int
    name: str = Field(min_length=1, max_length=120)
    is_income: bool = False
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    group_id: int | None = None
    name: str | None = None
    is_income: bool | None = None
    is_archived: bool | None = None
    sort_order: int | None = None


class CategoryOut(ORMModel):
    id: int
    group_id: int
    name: str
    is_income: bool
    is_archived: bool
    sort_order: int


# ---------- Transactions & splits ----------

class SplitIn(BaseModel):
    category_id: int | None = None
    amount_cents: int
    memo: str = ""


class SplitOut(ORMModel):
    id: int
    category_id: int | None
    amount_cents: int
    memo: str


class TransactionIn(BaseModel):
    account_id: int
    date: dt.date
    payee: str = ""
    memo: str = ""
    amount_cents: int | None = None
    cleared: bool = False
    # Either a single category_id (one implicit split) or explicit splits.
    category_id: int | None = None
    splits: list[SplitIn] | None = None


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    date: dt.date | None = None
    payee: str | None = None
    memo: str | None = None
    amount_cents: int | None = None
    cleared: bool | None = None
    category_id: int | None = None
    splits: list[SplitIn] | None = None


class TransactionOut(ORMModel):
    id: int
    account_id: int
    date: dt.date
    payee: str
    memo: str
    amount_cents: int
    cleared: bool
    import_hash: str | None
    recurring_rule_id: int | None
    created_at: dt.datetime
    splits: list[SplitOut]


class BulkEdit(BaseModel):
    """Apply the same edits to many transactions at once."""

    ids: list[int] = Field(min_length=1)
    set_payee: str | None = None
    set_memo: str | None = None
    set_cleared: bool | None = None
    set_account_id: int | None = None
    # Re-categorize: collapses each transaction to a single split in this category.
    set_category_id: int | None = None
    delete: bool = False


class BulkEditResult(BaseModel):
    matched: int
    updated: int
    deleted: int


# ---------- Budget (zero-based) ----------

class AllocationIn(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN)
    category_id: int
    amount_cents: int


class CategoryBudgetOut(BaseModel):
    category_id: int
    name: str
    group: str
    is_income: bool
    allocated_cents: int
    activity_cents: int
    available_cents: int


class MonthBudgetOut(BaseModel):
    month: str
    income_cents: int
    allocated_cents: int
    activity_cents: int
    to_be_budgeted_cents: int
    categories: list[CategoryBudgetOut]


# ---------- Recurring ----------

class RecurringIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    account_id: int
    payee: str = ""
    memo: str = ""
    amount_cents: int
    category_id: int | None = None
    frequency: str
    interval: int = Field(default=1, ge=1)
    next_date: dt.date
    end_date: dt.date | None = None
    auto_post: bool = True

    @field_validator("frequency")
    @classmethod
    def check_frequency(cls, v: str) -> str:
        allowed = {"daily", "weekly", "biweekly", "monthly", "yearly"}
        if v not in allowed:
            raise ValueError(f"frequency must be one of {sorted(allowed)}")
        return v


class RecurringUpdate(BaseModel):
    name: str | None = None
    account_id: int | None = None
    payee: str | None = None
    memo: str | None = None
    amount_cents: int | None = None
    category_id: int | None = None
    frequency: str | None = None
    interval: int | None = Field(default=None, ge=1)
    next_date: dt.date | None = None
    end_date: dt.date | None = None
    auto_post: bool | None = None
    is_active: bool | None = None


class RecurringOut(ORMModel):
    id: int
    name: str
    account_id: int
    payee: str
    memo: str
    amount_cents: int
    category_id: int | None
    frequency: str
    interval: int
    next_date: dt.date
    end_date: dt.date | None
    auto_post: bool
    is_active: bool


class RecurringRunResult(BaseModel):
    posted: int
    transactions: list[TransactionOut]


# ---------- Sinking funds ----------

class SinkingFundIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category_id: int
    target_cents: int = Field(gt=0)
    target_date: dt.date | None = None
    notes: str = ""


class SinkingFundUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    target_cents: int | None = Field(default=None, gt=0)
    target_date: dt.date | None = None
    notes: str | None = None


class SinkingFundOut(ORMModel):
    id: int
    name: str
    category_id: int
    target_cents: int
    target_date: dt.date | None
    notes: str
    saved_cents: int = 0
    remaining_cents: int = 0
    percent_complete: float = 0.0
    months_remaining: int | None = None
    suggested_monthly_cents: int | None = None
    on_track: bool | None = None


# ---------- Import ----------

class ImportRowError(BaseModel):
    row: int
    error: str


class ImportPreviewRow(BaseModel):
    date: dt.date
    payee: str
    memo: str
    amount_cents: int
    category: str | None = None
    duplicate: bool = False


class ImportResult(BaseModel):
    format: str
    total_rows: int
    imported: int
    skipped_duplicates: int
    errors: list[ImportRowError]
    column_mapping: dict[str, str]
    preview: list[ImportPreviewRow]
    dry_run: bool


# ---------- Backups ----------

class BackupOut(BaseModel):
    filename: str
    size_bytes: int
    created_at: dt.datetime


class RestoreResult(BaseModel):
    restored: bool
    counts: dict[str, int]


# ---------- Reports ----------

class CashFlowMonth(BaseModel):
    month: str
    income_cents: int
    expense_cents: int
    net_cents: int


class CashFlowOut(BaseModel):
    months: list[CashFlowMonth]


class BurnRateOut(BaseModel):
    window_days: int
    total_outflow_cents: int
    total_inflow_cents: int
    daily_burn_cents: int
    daily_net_cents: int
    liquid_balance_cents: int
    runway_days: int | None
    runway_date: dt.date | None


class SpendingByCategory(BaseModel):
    category_id: int | None
    name: str
    spent_cents: int
