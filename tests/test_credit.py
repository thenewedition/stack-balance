import io


def _make_card(client, name="Visa"):
    return client.post("/api/accounts", json={
        "name": name, "type": "credit", "opening_balance_cents": 0,
    }).json()


def test_credit_account_gets_payment_envelope(seeded):
    client = seeded["client"]
    card = _make_card(client)
    assert card["payment_category_id"] is not None

    groups = client.get("/api/category-groups").json()
    payments_group = next(g for g in groups if g["name"] == "Credit Card Payments")
    categories = client.get("/api/categories").json()
    envelope = next(c for c in categories if c["id"] == card["payment_category_id"])
    assert envelope["group_id"] == payments_group["id"]
    assert envelope["name"] == "Visa"

    # The envelope cannot be deleted while the card exists.
    assert client.delete(f"/api/categories/{envelope['id']}").status_code == 409


def test_card_spending_earmarks_payment_envelope(seeded):
    client = seeded["client"]
    card = _make_card(client)
    envelope_id = card["payment_category_id"]

    # Fund the budget and assign to groceries.
    client.post("/api/transactions", json={
        "account_id": seeded["account"]["id"], "date": "2026-07-01",
        "amount_cents": 200_000, "category_id": seeded["salary"]["id"],
    })
    client.put("/api/budget/allocations", json={
        "month": "2026-07", "category_id": seeded["groceries"]["id"], "amount_cents": 50_000,
    })

    # Spend on the card from the groceries envelope.
    client.post("/api/transactions", json={
        "account_id": card["id"], "date": "2026-07-05", "payee": "Grocer",
        "amount_cents": -12_000, "category_id": seeded["groceries"]["id"],
    })

    budget = client.get("/api/budget/2026-07").json()
    by_id = {c["category_id"]: c for c in budget["categories"]}
    assert by_id[seeded["groceries"]["id"]]["available_cents"] == 38_000   # envelope spent down
    assert by_id[envelope_id]["available_cents"] == 12_000                 # earmarked for the card
    assert by_id[envelope_id]["activity_cents"] == 12_000
    # TBB unaffected by card spending; month totals reflect real spending only.
    assert budget["to_be_budgeted_cents"] == 200_000 - 50_000
    assert budget["activity_cents"] == -12_000

    # Card balance is negative (debt); payment envelope says how much to pay.
    account = client.get(f"/api/accounts/{card['id']}").json()
    assert account["balance_cents"] == -12_000


def test_card_payment_via_transfer(seeded):
    client = seeded["client"]
    card = _make_card(client)
    envelope_id = card["payment_category_id"]
    checking_id = seeded["account"]["id"]

    client.post("/api/transactions", json={
        "account_id": card["id"], "date": "2026-07-02",
        "amount_cents": -30_000, "category_id": seeded["groceries"]["id"],
    })

    transfer = client.post("/api/transfers", json={
        "from_account_id": checking_id, "to_account_id": card["id"],
        "date": "2026-07-10", "amount_cents": 30_000, "memo": "card bill",
    })
    assert transfer.status_code == 201
    pair = transfer.json()
    assert pair["from_transaction"]["amount_cents"] == -30_000
    assert pair["to_transaction"]["amount_cents"] == 30_000
    assert pair["from_transaction"]["transfer_account_id"] == card["id"]
    assert pair["to_transaction"]["transfer_account_id"] == checking_id

    # Payment envelope drained; card paid off; checking reduced.
    budget = client.get("/api/budget/2026-07").json()
    by_id = {c["category_id"]: c for c in budget["categories"]}
    assert by_id[envelope_id]["available_cents"] == 0
    assert client.get(f"/api/accounts/{card['id']}").json()["balance_cents"] == 0
    assert client.get(f"/api/accounts/{checking_id}").json()["balance_cents"] == 100_000 - 30_000


def test_transfers_excluded_from_reports(seeded):
    client = seeded["client"]
    savings = client.post("/api/accounts", json={"name": "Savings", "type": "savings"}).json()
    client.post("/api/transfers", json={
        "from_account_id": seeded["account"]["id"], "to_account_id": savings["id"],
        "date": "2026-07-01", "amount_cents": 40_000,
    })
    cash_flow = client.get("/api/reports/cash-flow",
                           params={"months": 1, "as_of": "2026-07-03"}).json()
    assert cash_flow["months"][0]["income_cents"] == 0
    assert cash_flow["months"][0]["expense_cents"] == 0
    burn = client.get("/api/reports/burn-rate", params={"as_of": "2026-07-03"}).json()
    assert burn["total_outflow_cents"] == 0
    assert burn["liquid_balance_cents"] == 100_000  # unchanged in total


def test_transfer_edit_syncs_and_delete_removes_both(seeded):
    client = seeded["client"]
    savings = client.post("/api/accounts", json={"name": "Savings", "type": "savings"}).json()
    pair = client.post("/api/transfers", json={
        "from_account_id": seeded["account"]["id"], "to_account_id": savings["id"],
        "date": "2026-07-01", "amount_cents": 10_000,
    }).json()
    out_id = pair["from_transaction"]["id"]
    in_id = pair["to_transaction"]["id"]

    # Categorizing a transfer is rejected.
    bad = client.patch(f"/api/transactions/{out_id}",
                       json={"category_id": seeded["groceries"]["id"]})
    assert bad.status_code == 422

    # Editing amount/date on one side mirrors to the other.
    client.patch(f"/api/transactions/{out_id}",
                 json={"amount_cents": -15_000, "date": "2026-07-02"})
    peer = client.get(f"/api/transactions/{in_id}").json()
    assert peer["amount_cents"] == 15_000
    assert peer["date"] == "2026-07-02"

    # Bulk recategorize skips transfers.
    client.post("/api/transactions/bulk",
                json={"ids": [out_id], "set_category_id": seeded["groceries"]["id"]})
    assert client.get(f"/api/transactions/{out_id}").json()["splits"][0]["category_id"] is None

    # Deleting one side deletes both.
    assert client.delete(f"/api/transactions/{out_id}").status_code == 204
    assert client.get(f"/api/transactions/{in_id}").status_code == 404


def test_backup_roundtrip_preserves_transfer_links(seeded):
    client = seeded["client"]
    card = _make_card(client)
    client.post("/api/transfers", json={
        "from_account_id": seeded["account"]["id"], "to_account_id": card["id"],
        "date": "2026-07-01", "amount_cents": 5_000,
    })
    backup = client.get(
        "/api/backups/" + client.post("/api/backups").json()["filename"])
    client.post("/api/backups/restore", files={
        "file": ("b.zip", io.BytesIO(backup.content), "application/zip"),
    })
    txns = client.get("/api/transactions").json()
    assert len(txns) == 2
    assert {t["transfer_peer_id"] for t in txns} == {t["id"] for t in txns}
    restored_card = client.get(f"/api/accounts/{card['id']}").json()
    assert restored_card["payment_category_id"] == card["payment_category_id"]


def test_refund_on_card_reduces_earmark(seeded):
    client = seeded["client"]
    card = _make_card(client)
    envelope_id = card["payment_category_id"]
    client.post("/api/transactions", json={
        "account_id": card["id"], "date": "2026-07-02",
        "amount_cents": -20_000, "category_id": seeded["groceries"]["id"],
    })
    client.post("/api/transactions", json={
        "account_id": card["id"], "date": "2026-07-03", "payee": "Refund",
        "amount_cents": 8_000, "category_id": seeded["groceries"]["id"],
    })
    budget = client.get("/api/budget/2026-07").json()
    by_id = {c["category_id"]: c for c in budget["categories"]}
    assert by_id[envelope_id]["available_cents"] == 12_000
    assert by_id[seeded["groceries"]["id"]]["available_cents"] == -12_000
