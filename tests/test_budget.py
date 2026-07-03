def test_zero_based_budget_flow(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]

    # Paycheck in July
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-07-01", "payee": "Employer",
        "amount_cents": 300_000, "category_id": seeded["salary"]["id"],
    })
    budget = client.get("/api/budget/2026-07").json()
    assert budget["income_cents"] == 300_000
    assert budget["to_be_budgeted_cents"] == 300_000

    # Assign every dollar
    client.put("/api/budget/allocations", json={
        "month": "2026-07", "category_id": seeded["rent"]["id"], "amount_cents": 150_000,
    })
    budget = client.put("/api/budget/allocations", json={
        "month": "2026-07", "category_id": seeded["groceries"]["id"], "amount_cents": 150_000,
    }).json()
    assert budget["to_be_budgeted_cents"] == 0
    assert budget["allocated_cents"] == 300_000

    # Spend against groceries
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-07-05", "payee": "Grocer",
        "amount_cents": -40_000, "category_id": seeded["groceries"]["id"],
    })
    budget = client.get("/api/budget/2026-07").json()
    groceries_row = next(
        c for c in budget["categories"] if c["category_id"] == seeded["groceries"]["id"]
    )
    assert groceries_row["allocated_cents"] == 150_000
    assert groceries_row["activity_cents"] == -40_000
    assert groceries_row["available_cents"] == 110_000

    # Unspent money carries into August; TBB doesn't double-count it.
    august = client.get("/api/budget/2026-08").json()
    groceries_august = next(
        c for c in august["categories"] if c["category_id"] == seeded["groceries"]["id"]
    )
    assert groceries_august["allocated_cents"] == 0
    assert groceries_august["available_cents"] == 110_000
    assert august["to_be_budgeted_cents"] == 0


def test_cannot_allocate_to_income_category(seeded):
    client = seeded["client"]
    response = client.put("/api/budget/allocations", json={
        "month": "2026-07", "category_id": seeded["salary"]["id"], "amount_cents": 1,
    })
    assert response.status_code == 422


def test_reallocation_overwrites(seeded):
    client = seeded["client"]
    for amount in (10_000, 25_000):
        budget = client.put("/api/budget/allocations", json={
            "month": "2026-07", "category_id": seeded["rent"]["id"], "amount_cents": amount,
        }).json()
    assert budget["allocated_cents"] == 25_000
