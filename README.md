# Stack Balance

Self-hosted, **local-first** zero-based budgeting. One Python process, one
SQLite file, no cloud, no accounts, no telemetry. A REST API drives everything,
and a built-in web GUI (framework-free, no build step, zero external assets —
works fully offline) covers daily use: Dashboard, Budget, Transactions, Import,
and Settings.

## Features

- **Zero-based budgeting** — every dollar of income lands in "To Be Budgeted";
  assign it to category envelopes month by month until TBB reads zero. Unspent
  envelope money carries forward automatically.
- **Custom split-categories** — any transaction can be split across multiple
  categories (`splits` must sum to the transaction total; the API enforces it).
- **Recurring transaction engine** — daily/weekly/biweekly/monthly/yearly rules
  with intervals, end dates, and day-of-month anchoring ("the 31st" clamps to
  short months without drifting). Catch-up safe: a rule three periods overdue
  posts three transactions.
- **Local-first database** — a single SQLite file (`data/stackbalance.db`, WAL
  mode). Your data never leaves your machine.
- **Universal CSV/JSON parser** — imports arbitrary bank exports: auto-detects
  delimiter, header synonyms (date/amount/debit/credit/payee/memo/category),
  US & European number formats, parenthesized negatives, a dozen date formats,
  and deduplicates re-imports by content hash. Dry-run preview supported.
- **One-click portable backups** — a zip containing a human-readable
  `data.json`, a SQL dump of the database, and a manifest. Restore replays the
  JSON, so backups move cleanly between machines.
- **REST API** — everything the app does is an endpoint. Interactive docs at
  `/docs` (OpenAPI/Swagger).
- **Bulk transaction editing** — re-categorize, re-title, clear, move, or
  delete many transactions in one call.
- **Sinking funds tracker** — savings goals linked to category envelopes, with
  progress, suggested monthly contribution, and on-track status.
- **Cash flow & burn rate** — 12-month income vs. spending, average daily burn,
  and runway ("at this pace, funds last until …"), charted on the dashboard.
- **Reconciliation workflow** — check the register off against a real
  statement: mark transactions cleared until the cleared balance matches,
  then finish to lock them (`reconciled`). Any leftover difference books a
  balance-adjustment transaction that To Be Budgeted absorbs. Reconciled
  transactions refuse edits that would change the reconciled balance
  (amount/date/account) until explicitly unlocked.
- **Reports page** — net worth over time (all accounts, assets vs. debts),
  per-category monthly spending trend with average, and top payees by period.
- **Credit card payment handling** — every credit account gets a payment
  envelope (in the auto-created "Credit Card Payments" group). Budgeted
  spending on the card moves that money into the envelope, so its Available
  always answers "how much can I safely pay?". Payments are **account
  transfers** (checking → card): linked transaction pairs that are neither
  income nor spending, excluded from all reports.

## Quick start

```bash
pip install -r requirements.txt
python run.py                 # serves http://127.0.0.1:8321
```

Open <http://127.0.0.1:8321> for the app, <http://127.0.0.1:8321/docs>
for the API.

### The GUI

| Page | What you can do |
|---|---|
| **Dashboard** | To-Be-Budgeted / balance / burn / runway tiles, 12-month cash-flow chart, spending by category, sinking-fund progress, quick actions |
| **Budget** | Navigate months, edit assignments inline, copy last month's assignments, see overspent envelopes, record credit-card payments from the payment envelope |
| **Transactions** | Filter/search, add/edit with a split-category editor, record transfers between accounts, toggle cleared, select many and bulk recategorize/move/clear/delete |
| **Import** | Drag-and-drop a CSV/JSON export, review the dry-run preview, correct the auto-detected column mapping, commit |
| **Reports** | Net worth trend, category spending trend with average, top payees by period |
| **Settings** | Manage accounts, category groups/categories, recurring rules, sinking funds, and backups (create/download/restore) |

To reconcile an account: filter Transactions to that account, click
**Reconcile**, and follow the modal. Reconciled rows show a 🔒.

First-run setup happens entirely in the GUI: create an account and your
category groups under **Settings**, then import or add transactions.

### First-run setup (via the API, optional)

```bash
BASE=http://127.0.0.1:8321/api

# an account
curl -X POST $BASE/accounts -H 'Content-Type: application/json' \
  -d '{"name": "Checking", "opening_balance_cents": 250000}'

# category structure
curl -X POST $BASE/category-groups -H 'Content-Type: application/json' -d '{"name": "Income"}'
curl -X POST $BASE/categories -H 'Content-Type: application/json' \
  -d '{"group_id": 1, "name": "Salary", "is_income": true}'

# import your bank's CSV (any bank — columns are auto-detected)
curl -X POST $BASE/import -F account_id=1 -F file=@statement.csv -F dry_run=true   # preview
curl -X POST $BASE/import -F account_id=1 -F file=@statement.csv                    # commit
```

All money amounts are **integer cents** (`amount_cents`); outflows are
negative, inflows positive.

## API surface

| Area | Endpoints |
|---|---|
| Accounts | `GET/POST /api/accounts`, `GET/PATCH/DELETE /api/accounts/{id}`, `POST /api/accounts/{id}/reconcile` |
| Categories | `GET/POST /api/category-groups`, `GET/POST/PATCH/DELETE /api/categories` |
| Transactions | `GET/POST /api/transactions` (filter by account/category/date/payee/cleared), `GET/PATCH/DELETE /api/transactions/{id}`, `POST /api/transactions/bulk`, `POST /api/transfers` |
| Budget | `GET /api/budget/{YYYY-MM}`, `PUT /api/budget/allocations` |
| Recurring | `GET/POST /api/recurring`, `PATCH/DELETE /api/recurring/{id}`, `POST /api/recurring/run` |
| Sinking funds | `GET/POST /api/sinking-funds`, `GET/PATCH/DELETE /api/sinking-funds/{id}` |
| Import | `POST /api/import` (multipart: `file`, `account_id`, `dry_run`, `skip_duplicates`, `column_mapping`) |
| Backups | `POST/GET /api/backups`, `GET/DELETE /api/backups/{filename}`, `POST /api/backups/restore` |
| Reports | `GET /api/reports/cash-flow`, `GET /api/reports/burn-rate`, `GET /api/reports/spending/{YYYY-MM}`, `GET /api/reports/net-worth`, `GET /api/reports/category-trend/{id}`, `GET /api/reports/payees` |

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `STACKBALANCE_DATA_DIR` | `./data` | Where the database and backups live |
| `STACKBALANCE_DB` | `$DATA_DIR/stackbalance.db` | Override the database path |

## Development

```bash
pip install -r requirements.txt pytest httpx
python -m pytest
```

## Notes on the budgeting model

- A category's **Available** = everything ever assigned to it + all activity,
  cumulative through the viewed month (envelopes carry forward, including
  overspending — a negative envelope stays negative until you cover it).
- **To Be Budgeted** for a month = cumulative income − cumulative assignments
  through that month.
- Off-budget accounts (`on_budget: false`) are excluded from budget math and
  reports but still track balances.
- **Credit cards**: categorized spending on a credit account earmarks that
  amount into the card's payment envelope (uncategorized card spending moves
  nothing — only budgeted spending is covered). Transfers into the card
  (payments) draw the envelope down. Assign directly to the payment envelope
  to budget for a pre-existing card balance.
- **Transfers** are linked pairs: editing one side's date or amount syncs the
  other; deleting one side deletes both; they can't be categorized or moved
  to a different account.

## Roadmap

- **Auto-categorization rules** — remember payee → category pairings and
  apply them during import, so recurring merchants land in the right
  envelope automatically.
- **Category targets & goals** — monthly funding targets per envelope with
  underfunded indicators on the Budget page.
- **Debt payoff planner** — interest rates on credit/loan accounts with
  payoff projections and avalanche/snowball comparisons.
- **Installable PWA** — offline-capable mobile UI (add-to-home-screen) for
  entering transactions on the go.
- **Automatic backups** — scheduled backup creation with retention rules,
  on top of the existing one-click backups.
- **CSV export** — download any filtered register or report view.
- **Optional authentication** — a PIN/password layer for hosting on a
  shared network.
- **Multi-currency** — accounts in different currencies with a reporting
  currency.
