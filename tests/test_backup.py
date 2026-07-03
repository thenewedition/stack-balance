import io
import zipfile


def test_backup_roundtrip(seeded):
    client = seeded["client"]
    client.post("/api/transactions", json={
        "account_id": seeded["account"]["id"], "date": "2026-07-01",
        "payee": "Grocer", "amount_cents": -4200,
        "category_id": seeded["groceries"]["id"],
    })
    client.put("/api/budget/allocations", json={
        "month": "2026-07", "category_id": seeded["groceries"]["id"], "amount_cents": 50_000,
    })

    created = client.post("/api/backups")
    assert created.status_code == 201
    filename = created.json()["filename"]

    listing = client.get("/api/backups").json()
    assert any(b["filename"] == filename for b in listing)

    download = client.get(f"/api/backups/{filename}")
    assert download.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    assert {"data.json", "stackbalance.sql", "manifest.json"} <= set(archive.namelist())

    # Wipe some data, then restore.
    txn_id = client.get("/api/transactions").json()[0]["id"]
    client.delete(f"/api/transactions/{txn_id}")
    assert client.get("/api/transactions").json() == []

    restore = client.post("/api/backups/restore", files={
        "file": ("backup.zip", io.BytesIO(download.content), "application/zip"),
    })
    assert restore.status_code == 200
    counts = restore.json()["counts"]
    assert counts["transactions"] == 1
    assert counts["splits"] == 1
    assert counts["budget_allocations"] == 1

    txns = client.get("/api/transactions").json()
    assert len(txns) == 1
    assert txns[0]["payee"] == "Grocer"
    budget = client.get("/api/budget/2026-07").json()
    assert budget["allocated_cents"] == 50_000


def test_restore_rejects_foreign_zip(seeded):
    client = seeded["client"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("random.txt", "hello")
    response = client.post("/api/backups/restore", files={
        "file": ("x.zip", io.BytesIO(buf.getvalue()), "application/zip"),
    })
    assert response.status_code == 422


def test_path_traversal_blocked(seeded):
    client = seeded["client"]
    response = client.get("/api/backups/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code == 404
