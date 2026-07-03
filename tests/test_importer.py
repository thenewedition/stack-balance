import io
import json

import pytest

from stackbalance.services.importer import map_columns, parse_amount, parse_date


@pytest.mark.parametrize("raw,cents", [
    ("12.34", 1234),
    ("-12.34", -1234),
    ("$1,234.56", 123456),
    ("(45.00)", -4500),
    ("1.234,56", 123456),      # European
    ("12,34", 1234),           # European decimal comma
    ("1,234", 123400),         # thousands separator
    (" €99,10 ", 9910),
    ("100", 10000),
    (10.5, 1050),
    ("45.00-", -4500),
])
def test_parse_amount(raw, cents):
    assert parse_amount(raw) == cents


def test_parse_amount_rejects_garbage():
    with pytest.raises(ValueError):
        parse_amount("not money")


@pytest.mark.parametrize("raw,expected", [
    ("2026-07-01", (2026, 7, 1)),
    ("07/15/2026", (2026, 7, 15)),
    ("15.07.2026", (2026, 7, 15)),
    ("31/01/2026", (2026, 1, 31)),   # DD/MM disambiguated by day > 12
    ("Jul 4, 2026", (2026, 7, 4)),
    ("2026-07-01T09:30:00Z", (2026, 7, 1)),
    ("20260701", (2026, 7, 1)),
])
def test_parse_date(raw, expected):
    parsed = parse_date(raw)
    assert (parsed.year, parsed.month, parsed.day) == expected


def test_map_columns_synonyms():
    mapping = map_columns(["Posted Date", "Description", "Money Out", "Money In", "Notes"])
    assert mapping["date"] == "Posted Date"
    assert mapping["payee"] == "Description"
    assert mapping["debit"] == "Money Out"
    assert mapping["credit"] == "Money In"
    assert mapping["memo"] == "Notes"


def _upload(client, account_id, name, content, **form):
    return client.post(
        "/api/import",
        data={"account_id": account_id, **form},
        files={"file": (name, io.BytesIO(content), "text/csv")},
    )


def test_csv_import_with_debit_credit_columns(seeded):
    client = seeded["client"]
    csv_data = (
        "Posted Date,Description,Money Out,Money In\n"
        "07/01/2026,ACME PAYROLL,,\"2,500.00\"\n"
        "07/02/2026,GROCER #12,45.67,\n"
        "07/03/2026,COFFEE,(4.50),\n"
    ).encode()
    result = _upload(client, seeded["account"]["id"], "bank.csv", csv_data).json()
    assert result["format"] == "csv"
    assert result["imported"] == 3
    assert result["errors"] == []

    txns = client.get("/api/transactions").json()
    amounts = sorted(t["amount_cents"] for t in txns)
    assert amounts == [-4567, -450, 250000]


def test_import_deduplicates_on_reimport(seeded):
    client = seeded["client"]
    csv_data = b"Date,Description,Amount\n2026-07-01,Store,-10.00\n2026-07-02,Cafe,-5.00\n"
    first = _upload(client, seeded["account"]["id"], "a.csv", csv_data).json()
    assert first["imported"] == 2
    second = _upload(client, seeded["account"]["id"], "a.csv", csv_data).json()
    assert second["imported"] == 0
    assert second["skipped_duplicates"] == 2
    assert len(client.get("/api/transactions").json()) == 2


def test_json_import_with_category_matching(seeded):
    client = seeded["client"]
    payload = json.dumps({"transactions": [
        {"date": "2026-07-01", "description": "Grocer", "amount": "-20.00",
         "category": "Groceries"},
        {"date": "2026-07-02", "description": "Cafe", "amount": -7.5},
    ]}).encode()
    result = _upload(client, seeded["account"]["id"], "export.json", payload).json()
    assert result["format"] == "json"
    assert result["imported"] == 2

    txns = client.get("/api/transactions", params={
        "category_id": seeded["groceries"]["id"]}).json()
    assert len(txns) == 1
    assert txns[0]["amount_cents"] == -2000


def test_dry_run_imports_nothing(seeded):
    client = seeded["client"]
    csv_data = b"Date,Description,Amount\n2026-07-01,Store,-10.00\n"
    result = _upload(client, seeded["account"]["id"], "a.csv", csv_data, dry_run=True).json()
    assert result["dry_run"] is True
    assert result["preview"][0]["amount_cents"] == -1000
    assert client.get("/api/transactions").json() == []


def test_semicolon_delimiter_and_bad_rows_reported(seeded):
    client = seeded["client"]
    csv_data = (
        "Date;Description;Amount\n"
        "2026-07-01;Shop;-12,50\n"
        "garbage;;\n"
    ).encode()
    result = _upload(client, seeded["account"]["id"], "euro.csv", csv_data).json()
    assert result["imported"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 2
