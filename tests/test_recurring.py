from datetime import date

from stackbalance.services.recurring import add_months


def test_add_months_clamps_and_recovers_anchor():
    assert add_months(date(2026, 1, 31), 1, anchor_day=31) == date(2026, 2, 28)
    assert add_months(date(2026, 2, 28), 1, anchor_day=31) == date(2026, 3, 31)
    assert add_months(date(2026, 11, 30), 3, anchor_day=30) == date(2027, 2, 28)


def test_recurring_catch_up_posts_every_missed_occurrence(seeded):
    client = seeded["client"]
    rule = client.post("/api/recurring", json={
        "name": "Rent", "account_id": seeded["account"]["id"], "payee": "Landlord",
        "amount_cents": -150_000, "category_id": seeded["rent"]["id"],
        "frequency": "monthly", "next_date": "2026-04-01",
    }).json()

    result = client.post("/api/recurring/run", params={"as_of": "2026-07-03"}).json()
    assert result["posted"] == 4  # Apr, May, Jun, Jul
    dates = sorted(t["date"] for t in result["transactions"])
    assert dates == ["2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01"]
    assert all(t["recurring_rule_id"] == rule["id"] for t in result["transactions"])

    rules = client.get("/api/recurring").json()
    assert rules[0]["next_date"] == "2026-08-01"

    # Running again posts nothing new.
    assert client.post("/api/recurring/run", params={"as_of": "2026-07-03"}).json()["posted"] == 0


def test_recurring_respects_end_date(seeded):
    client = seeded["client"]
    client.post("/api/recurring", json={
        "name": "Trial sub", "account_id": seeded["account"]["id"],
        "amount_cents": -999, "frequency": "weekly",
        "next_date": "2026-06-01", "end_date": "2026-06-15",
    })
    result = client.post("/api/recurring/run", params={"as_of": "2026-07-03"}).json()
    assert result["posted"] == 3  # Jun 1, 8, 15
    rules = client.get("/api/recurring", params={"include_inactive": True}).json()
    assert rules[0]["is_active"] is False


def test_biweekly_schedule(seeded):
    client = seeded["client"]
    client.post("/api/recurring", json={
        "name": "Paycheck", "account_id": seeded["account"]["id"],
        "amount_cents": 200_000, "category_id": seeded["salary"]["id"],
        "frequency": "biweekly", "next_date": "2026-06-05",
    })
    result = client.post("/api/recurring/run", params={"as_of": "2026-07-03"}).json()
    assert sorted(t["date"] for t in result["transactions"]) == [
        "2026-06-05", "2026-06-19", "2026-07-03",
    ]
