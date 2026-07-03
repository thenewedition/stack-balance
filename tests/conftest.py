import os

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKBALANCE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STACKBALANCE_DB", str(tmp_path / "test.db"))

    from stackbalance import database

    database.reset_engine()
    database.init_db()

    from fastapi.testclient import TestClient

    from stackbalance.main import app

    with TestClient(app) as test_client:
        yield test_client
    database.reset_engine()


@pytest.fixture()
def seeded(client):
    """Account + a couple of category groups/categories; returns useful ids."""
    account = client.post("/api/accounts", json={
        "name": "Checking", "type": "checking", "opening_balance_cents": 100_000,
    }).json()
    income_group = client.post("/api/category-groups", json={"name": "Income"}).json()
    bills_group = client.post("/api/category-groups", json={"name": "Bills"}).json()
    fun_group = client.post("/api/category-groups", json={"name": "Everyday"}).json()

    salary = client.post("/api/categories", json={
        "group_id": income_group["id"], "name": "Salary", "is_income": True,
    }).json()
    rent = client.post("/api/categories", json={
        "group_id": bills_group["id"], "name": "Rent",
    }).json()
    groceries = client.post("/api/categories", json={
        "group_id": fun_group["id"], "name": "Groceries",
    }).json()
    dining = client.post("/api/categories", json={
        "group_id": fun_group["id"], "name": "Dining Out",
    }).json()
    return {
        "client": client,
        "account": account,
        "salary": salary,
        "rent": rent,
        "groceries": groceries,
        "dining": dining,
    }
