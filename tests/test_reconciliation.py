def _txn(client, account_id, date, cents, cleared=False, **extra):
    return client.post("/api/transactions", json={
        "account_id": account_id, "date": date, "amount_cents": cents,
        "cleared": cleared, **extra,
    }).json()


def test_reconcile_locks_cleared_and_matches_statement(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]  # opening balance 100_000
    cleared_txn = _txn(client, account_id, "2026-07-01", -20_000, cleared=True)
    pending_txn = _txn(client, account_id, "2026-07-02", -5_000, cleared=False)

    result = client.post(f"/api/accounts/{account_id}/reconcile", json={
        "statement_balance_cents": 80_000,
    }).json()
    assert result["reconciled_count"] == 1
    assert result["adjustment_cents"] == 0
    assert result["adjustment_transaction"] is None

    assert client.get(f"/api/transactions/{cleared_txn['id']}").json()["reconciled"] is True
    assert client.get(f"/api/transactions/{pending_txn['id']}").json()["reconciled"] is False

    account = client.get(f"/api/accounts/{account_id}").json()
    assert account["last_reconciled_balance_cents"] == 80_000
    assert account["last_reconciled_at"] is not None


def test_reconcile_creates_adjustment_booked_to_income(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]
    _txn(client, account_id, "2026-07-01", -10_000, cleared=True)

    # Statement says 87_000 but cleared balance is 90_000 -> -3_000 adjustment.
    result = client.post(f"/api/accounts/{account_id}/reconcile", json={
        "statement_balance_cents": 87_000,
    }).json()
    assert result["adjustment_cents"] == -3_000
    adjustment = result["adjustment_transaction"]
    assert adjustment["payee"] == "Reconciliation Balance Adjustment"
    assert adjustment["reconciled"] is True
    assert adjustment["splits"][0]["category_id"] == seeded["salary"]["id"]  # income default

    assert client.get(f"/api/accounts/{account_id}").json()["cleared_balance_cents"] == 87_000
    # TBB absorbed the correction.
    assert client.get("/api/budget/2026-07").json()["to_be_budgeted_cents"] == -3_000


def test_reconciled_transactions_are_locked(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]
    txn = _txn(client, account_id, "2026-07-01", -10_000, cleared=True, payee="Shop")
    client.post(f"/api/accounts/{account_id}/reconcile",
                json={"statement_balance_cents": 90_000})

    # Balance-changing edits are rejected; memo/payee/category edits pass.
    assert client.patch(f"/api/transactions/{txn['id']}",
                        json={"amount_cents": -1}).status_code == 422
    assert client.patch(f"/api/transactions/{txn['id']}",
                        json={"date": "2026-07-05"}).status_code == 422
    assert client.delete(f"/api/transactions/{txn['id']}").status_code == 422
    assert client.patch(f"/api/transactions/{txn['id']}",
                        json={"payee": "Shop Inc"}).status_code == 200
    assert client.patch(f"/api/transactions/{txn['id']}",
                        json={"category_id": seeded["groceries"]["id"]}).status_code == 200

    # Bulk delete skips reconciled rows.
    other = _txn(client, account_id, "2026-07-02", -100)
    result = client.post("/api/transactions/bulk",
                         json={"ids": [txn["id"], other["id"]], "delete": True}).json()
    assert result["deleted"] == 1
    assert client.get(f"/api/transactions/{txn['id']}").status_code == 200

    # Un-reconcile, then the edit works; un-clearing also un-reconciles.
    assert client.patch(f"/api/transactions/{txn['id']}",
                        json={"reconciled": False, "amount_cents": -9_000}).status_code == 200
    assert client.get(f"/api/transactions/{txn['id']}").json()["reconciled"] is False


def test_unclearing_reconciled_transaction_unreconciles(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]
    txn = _txn(client, account_id, "2026-07-01", -10_000, cleared=True)
    client.post(f"/api/accounts/{account_id}/reconcile",
                json={"statement_balance_cents": 90_000})
    updated = client.patch(f"/api/transactions/{txn['id']}",
                           json={"cleared": False}).json()
    assert updated["cleared"] is False
    assert updated["reconciled"] is False


def test_net_worth_report(seeded):
    client = seeded["client"]
    checking_id = seeded["account"]["id"]  # opening 100_000
    card = client.post("/api/accounts", json={"name": "Visa", "type": "credit"}).json()
    _txn(client, checking_id, "2026-06-15", 50_000)
    _txn(client, card["id"], "2026-07-02", -30_000)

    report = client.get("/api/reports/net-worth",
                        params={"months": 3, "as_of": "2026-07-04"}).json()
    months = {m["month"]: m for m in report["months"]}
    assert months["2026-05"]["net_cents"] == 100_000
    assert months["2026-06"]["net_cents"] == 150_000
    assert months["2026-07"]["assets_cents"] == 150_000
    assert months["2026-07"]["debts_cents"] == -30_000
    assert months["2026-07"]["net_cents"] == 120_000


def test_category_trend_report(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]
    for date, cents in [("2026-05-10", -10_000), ("2026-06-10", -20_000), ("2026-07-01", -30_000)]:
        _txn(client, account_id, date, cents, category_id=seeded["groceries"]["id"])

    report = client.get(f"/api/reports/category-trend/{seeded['groceries']['id']}",
                        params={"months": 3, "as_of": "2026-07-04"}).json()
    assert report["name"] == "Groceries"
    assert [m["spent_cents"] for m in report["months"]] == [-10_000, -20_000, -30_000]
    assert report["average_cents"] == -20_000


def test_top_payees_report(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]
    for _ in range(3):
        _txn(client, account_id, "2026-07-01", -5_000, payee="Coffee Hut")
    _txn(client, account_id, "2026-07-02", -40_000, payee="MegaMart")
    _txn(client, account_id, "2026-07-02", 99_000, payee="Employer")  # inflow: excluded
    savings = client.post("/api/accounts", json={"name": "Savings", "type": "savings"}).json()
    client.post("/api/transfers", json={  # transfer: excluded
        "from_account_id": account_id, "to_account_id": savings["id"],
        "date": "2026-07-03", "amount_cents": 70_000,
    })

    rows = client.get("/api/reports/payees",
                      params={"months": 1, "as_of": "2026-07-04"}).json()
    assert [(r["payee"], r["count"], r["total_cents"]) for r in rows] == [
        ("MegaMart", 1, -40_000), ("Coffee Hut", 3, -15_000),
    ]
