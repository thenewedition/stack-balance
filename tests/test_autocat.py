import io


def _rule(client, pattern, category_id, match_type="contains"):
    return client.post("/api/categorization-rules", json={
        "pattern": pattern, "match_type": match_type, "category_id": category_id,
    })


def test_rule_crud_and_upsert(seeded):
    client = seeded["client"]
    created = _rule(client, "grocer", seeded["groceries"]["id"])
    assert created.status_code == 201
    rule = created.json()

    # Same pattern+match_type repoints instead of erroring.
    repointed = _rule(client, "grocer", seeded["dining"]["id"]).json()
    assert repointed["id"] == rule["id"]
    assert repointed["category_id"] == seeded["dining"]["id"]
    assert len(client.get("/api/categorization-rules").json()) == 1

    assert client.delete(f"/api/categorization-rules/{rule['id']}").status_code == 204
    assert client.get("/api/categorization-rules").json() == []


def test_rule_validation(seeded):
    client = seeded["client"]
    assert _rule(client, "x", 99999).status_code == 404
    assert client.post("/api/categorization-rules", json={
        "pattern": "x", "match_type": "regex", "category_id": seeded["groceries"]["id"],
    }).status_code == 422
    assert client.post("/api/categorization-rules", json={
        "pattern": "   ", "category_id": seeded["groceries"]["id"],
    }).status_code == 422


def test_import_applies_rules_with_precedence(seeded):
    client = seeded["client"]
    _rule(client, "joe", seeded["dining"]["id"])                      # short contains
    _rule(client, "trader joe", seeded["groceries"]["id"])            # longer contains wins
    _rule(client, "netflix.com", seeded["rent"]["id"], "exact")       # exact beats contains
    _rule(client, "netflix", seeded["dining"]["id"])

    csv_data = (
        "Date,Description,Amount\n"
        "2026-07-01,TRADER JOE'S #42,-50.00\n"
        "2026-07-02,Joe's Diner,-20.00\n"
        "2026-07-03,netflix.com,-15.99\n"
        "2026-07-04,Mystery Shop,-9.00\n"
    ).encode()
    result = client.post("/api/import",
        data={"account_id": seeded["account"]["id"]},
        files={"file": ("bank.csv", io.BytesIO(csv_data), "text/csv")}).json()
    assert result["auto_categorized"] == 3

    txns = {t["payee"]: t for t in client.get("/api/transactions").json()}
    assert txns["TRADER JOE'S #42"]["splits"][0]["category_id"] == seeded["groceries"]["id"]
    assert txns["Joe's Diner"]["splits"][0]["category_id"] == seeded["dining"]["id"]
    assert txns["netflix.com"]["splits"][0]["category_id"] == seeded["rent"]["id"]
    assert txns["Mystery Shop"]["splits"][0]["category_id"] is None

    # Preview surfaces the auto-assigned category name.
    preview = client.post("/api/import",
        data={"account_id": seeded["account"]["id"], "dry_run": "true",
              "skip_duplicates": "false"},
        files={"file": ("bank.csv", io.BytesIO(csv_data), "text/csv")}).json()
    by_payee = {r["payee"]: r for r in preview["preview"]}
    assert by_payee["TRADER JOE'S #42"]["category"] == "Groceries"


def test_file_category_beats_rule(seeded):
    client = seeded["client"]
    _rule(client, "grocer", seeded["dining"]["id"])
    csv_data = b"Date,Description,Amount,Category\n2026-07-01,Grocer,-10.00,Rent\n"
    result = client.post("/api/import",
        data={"account_id": seeded["account"]["id"]},
        files={"file": ("bank.csv", io.BytesIO(csv_data), "text/csv")}).json()
    assert result["auto_categorized"] == 0
    txn = client.get("/api/transactions").json()[0]
    assert txn["splits"][0]["category_id"] == seeded["rent"]["id"]


def test_apply_to_existing_uncategorized(seeded):
    client = seeded["client"]
    uncategorized = client.post("/api/transactions", json={
        "account_id": seeded["account"]["id"], "date": "2026-07-01",
        "payee": "Corner Grocer", "amount_cents": -3000,
    }).json()
    categorized = client.post("/api/transactions", json={
        "account_id": seeded["account"]["id"], "date": "2026-07-02",
        "payee": "Corner Grocer", "amount_cents": -4000,
        "category_id": seeded["dining"]["id"],
    }).json()
    _rule(client, "grocer", seeded["groceries"]["id"])

    dry = client.post("/api/categorization-rules/apply", params={"dry_run": True}).json()
    assert dry == {"matched": 1, "dry_run": True}
    # Dry run changed nothing.
    assert client.get(f"/api/transactions/{uncategorized['id']}").json()["splits"][0]["category_id"] is None

    result = client.post("/api/categorization-rules/apply").json()
    assert result["matched"] == 1
    assert client.get(f"/api/transactions/{uncategorized['id']}").json()["splits"][0]["category_id"] == seeded["groceries"]["id"]
    # Already-categorized transactions are untouched.
    assert client.get(f"/api/transactions/{categorized['id']}").json()["splits"][0]["category_id"] == seeded["dining"]["id"]


def test_rules_survive_backup_roundtrip(seeded):
    client = seeded["client"]
    _rule(client, "grocer", seeded["groceries"]["id"])
    backup = client.get(
        "/api/backups/" + client.post("/api/backups").json()["filename"])
    client.delete("/api/categorization-rules/1")
    client.post("/api/backups/restore", files={
        "file": ("b.zip", io.BytesIO(backup.content), "application/zip"),
    })
    rules = client.get("/api/categorization-rules").json()
    assert len(rules) == 1
    assert rules[0]["pattern"] == "grocer"


def test_pwa_files_served(client):
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    data = manifest.json()
    assert data["display"] == "standalone"
    assert any(icon["sizes"] == "512x512" for icon in data["icons"])

    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "application/javascript" in sw.headers["content-type"]
    assert "networkFirst" in sw.text

    for icon in ("/static/icons/icon-192.png", "/static/icons/icon-512.png"):
        response = client.get(icon)
        assert response.status_code == 200
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"

    shell = client.get("/").text
    assert 'rel="manifest"' in shell
    assert "serviceWorker" in client.get("/static/js/app.js").text
