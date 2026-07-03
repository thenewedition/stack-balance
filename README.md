# Stack Balance

Self-hosted, **local-first** zero-based budgeting. One Python process, one
SQLite file, no cloud, no accounts, no telemetry. A REST API drives everything;
a built-in dashboard (zero external assets — works fully offline) visualizes it.

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

## Quick start

```bash
pip install -r requirements.txt
python run.py                 # serves http://127.0.0.1:8321
```

Open <http://127.0.0.1:8321> for the dashboard, <http://127.0.0.1:8321/docs>
for the API.

### First-run setup (via the API)

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
| Accounts | `GET/POST /api/accounts`, `GET/PATCH/DELETE /api/accounts/{id}` |
| Categories | `GET/POST /api/category-groups`, `GET/POST/PATCH/DELETE /api/categories` |
| Transactions | `GET/POST /api/transactions` (filter by account/category/date/payee/cleared), `GET/PATCH/DELETE /api/transactions/{id}`, `POST /api/transactions/bulk` |
| Budget | `GET /api/budget/{YYYY-MM}`, `PUT /api/budget/allocations` |
| Recurring | `GET/POST /api/recurring`, `PATCH/DELETE /api/recurring/{id}`, `POST /api/recurring/run` |
| Sinking funds | `GET/POST /api/sinking-funds`, `GET/PATCH/DELETE /api/sinking-funds/{id}` |
| Import | `POST /api/import` (multipart: `file`, `account_id`, `dry_run`, `skip_duplicates`, `column_mapping`) |
| Backups | `POST/GET /api/backups`, `GET/DELETE /api/backups/{filename}`, `POST /api/backups/restore` |
| Reports | `GET /api/reports/cash-flow`, `GET /api/reports/burn-rate`, `GET /api/reports/spending/{YYYY-MM}` |

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

## Roadmap

Planned for later: scheduled auto-run of recurring rules, multi-currency,
credit-card payment handling, budget templates/quick-budget, reconciliation
workflow, and richer reports.
