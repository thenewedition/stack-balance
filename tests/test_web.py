def test_spa_shell_served_at_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Stack Balance" in response.text
    assert "/static/js/app.js" in response.text


def test_static_assets_served(client):
    for path in ("/static/css/app.css", "/static/js/app.js", "/static/js/api.js",
                 "/static/js/views/dashboard.js", "/static/js/views/budget.js",
                 "/static/js/views/transactions.js", "/static/js/views/import.js",
                 "/static/js/views/settings.js"):
        assert client.get(path).status_code == 200, path


def test_import_result_includes_headers(seeded):
    import io

    client = seeded["client"]
    response = client.post(
        "/api/import",
        data={"account_id": seeded["account"]["id"], "dry_run": "true"},
        files={"file": ("a.csv", io.BytesIO(b"Date,Description,Amount\n2026-07-01,X,-1.00\n"), "text/csv")},
    )
    assert response.json()["headers"] == ["Date", "Description", "Amount"]
