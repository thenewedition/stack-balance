def test_sinking_fund_progress(seeded):
    client = seeded["client"]
    group = client.post("/api/category-groups", json={"name": "Goals"}).json()
    category = client.post("/api/categories", json={
        "group_id": group["id"], "name": "New Car",
    }).json()
    fund = client.post("/api/sinking-funds", json={
        "name": "New Car", "category_id": category["id"],
        "target_cents": 1_000_000, "target_date": "2027-07-01",
    }).json()
    assert fund["saved_cents"] == 0
    assert fund["remaining_cents"] == 1_000_000

    # Fund it by allocating to the linked category over two months.
    for month in ("2026-06", "2026-07"):
        client.put("/api/budget/allocations", json={
            "month": month, "category_id": category["id"], "amount_cents": 125_000,
        })
    fund = client.get(f"/api/sinking-funds/{fund['id']}").json()
    assert fund["saved_cents"] == 250_000
    assert fund["percent_complete"] == 25.0
    assert fund["suggested_monthly_cents"] > 0

    # Spending from the fund's category reduces progress.
    client.post("/api/transactions", json={
        "account_id": seeded["account"]["id"], "date": "2026-07-02",
        "payee": "Down payment", "amount_cents": -50_000, "category_id": category["id"],
    })
    fund = client.get(f"/api/sinking-funds/{fund['id']}").json()
    assert fund["saved_cents"] == 200_000


def test_cash_flow_report(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-06-01",
        "amount_cents": 500_000, "category_id": seeded["salary"]["id"],
    })
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-06-10", "amount_cents": -120_000,
    })
    report = client.get("/api/reports/cash-flow",
                        params={"months": 3, "as_of": "2026-07-03"}).json()
    assert [m["month"] for m in report["months"]] == ["2026-05", "2026-06", "2026-07"]
    june = report["months"][1]
    assert june["income_cents"] == 500_000
    assert june["expense_cents"] == -120_000
    assert june["net_cents"] == 380_000


def test_burn_rate_and_runway(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]  # opening balance 100_000
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-07-01", "amount_cents": -15_000,
    })
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-06-20", "amount_cents": -15_000,
    })
    report = client.get("/api/reports/burn-rate",
                        params={"window_days": 30, "as_of": "2026-07-03"}).json()
    assert report["total_outflow_cents"] == -30_000
    assert report["daily_burn_cents"] == 1000
    assert report["liquid_balance_cents"] == 70_000
    assert report["runway_days"] == 70


def test_spending_by_category(seeded):
    client = seeded["client"]
    client.post("/api/transactions", json={
        "account_id": seeded["account"]["id"], "date": "2026-07-01",
        "amount_cents": -10_000,
        "splits": [
            {"category_id": seeded["groceries"]["id"], "amount_cents": -7_000},
            {"category_id": seeded["dining"]["id"], "amount_cents": -3_000},
        ],
    })
    rows = client.get("/api/reports/spending/2026-07").json()
    assert [(r["name"], r["spent_cents"]) for r in rows] == [
        ("Groceries", -7_000), ("Dining Out", -3_000),
    ]
