def test_create_simple_transaction(seeded):
    client = seeded["client"]
    response = client.post("/api/transactions", json={
        "account_id": seeded["account"]["id"],
        "date": "2026-07-01",
        "payee": "Grocer",
        "amount_cents": -4550,
        "category_id": seeded["groceries"]["id"],
    })
    assert response.status_code == 201
    txn = response.json()
    assert txn["amount_cents"] == -4550
    assert len(txn["splits"]) == 1
    assert txn["splits"][0]["category_id"] == seeded["groceries"]["id"]


def test_split_transaction_must_balance(seeded):
    client = seeded["client"]
    base = {
        "account_id": seeded["account"]["id"], "date": "2026-07-02",
        "payee": "Superstore", "amount_cents": -10000,
    }
    bad = client.post("/api/transactions", json={**base, "splits": [
        {"category_id": seeded["groceries"]["id"], "amount_cents": -6000},
        {"category_id": seeded["dining"]["id"], "amount_cents": -3000},
    ]})
    assert bad.status_code == 422

    good = client.post("/api/transactions", json={**base, "splits": [
        {"category_id": seeded["groceries"]["id"], "amount_cents": -6000},
        {"category_id": seeded["dining"]["id"], "amount_cents": -4000, "memo": "takeout"},
    ]})
    assert good.status_code == 201
    assert len(good.json()["splits"]) == 2


def test_account_balance_reflects_transactions(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-07-01",
        "amount_cents": -2500, "cleared": True,
    })
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-07-02", "amount_cents": -1000,
    })
    account = client.get(f"/api/accounts/{account_id}").json()
    assert account["balance_cents"] == 100_000 - 3500
    assert account["cleared_balance_cents"] == 100_000 - 2500


def test_bulk_edit(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]
    ids = []
    for day in ("01", "02", "03"):
        response = client.post("/api/transactions", json={
            "account_id": account_id, "date": f"2026-07-{day}",
            "payee": "AMZN Mktp", "amount_cents": -1500,
        })
        ids.append(response.json()["id"])

    result = client.post("/api/transactions/bulk", json={
        "ids": ids,
        "set_payee": "Amazon",
        "set_category_id": seeded["dining"]["id"],
        "set_cleared": True,
    }).json()
    assert result == {"matched": 3, "updated": 3, "deleted": 0}

    txn = client.get(f"/api/transactions/{ids[0]}").json()
    assert txn["payee"] == "Amazon"
    assert txn["cleared"] is True
    assert txn["splits"][0]["category_id"] == seeded["dining"]["id"]

    result = client.post("/api/transactions/bulk", json={"ids": ids[:2], "delete": True}).json()
    assert result["deleted"] == 2
    assert client.get(f"/api/transactions/{ids[0]}").status_code == 404


def test_filtering(seeded):
    client = seeded["client"]
    account_id = seeded["account"]["id"]
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-06-15", "payee": "Rent LLC",
        "amount_cents": -150000, "category_id": seeded["rent"]["id"],
    })
    client.post("/api/transactions", json={
        "account_id": account_id, "date": "2026-07-01", "payee": "Grocer",
        "amount_cents": -4000, "category_id": seeded["groceries"]["id"],
    })
    assert len(client.get("/api/transactions", params={"payee": "rent"}).json()) == 1
    assert len(client.get("/api/transactions", params={
        "category_id": seeded["groceries"]["id"]}).json()) == 1
    assert len(client.get("/api/transactions", params={
        "start_date": "2026-07-01"}).json()) == 1
