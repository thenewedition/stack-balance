"""Universal CSV/JSON transaction importer.

Design goals:
- Accept exports from arbitrary banks without pre-built profiles.
- Auto-detect format (JSON vs CSV), CSV delimiter, and which columns hold the
  date / amount / payee / memo / category, using header-name synonyms.
- Handle debit+credit column pairs, negative-in-parentheses, currency symbols,
  thousands separators, and both US and European decimal notation.
- Parse the common date formats, disambiguating DD/MM vs MM/DD when possible.
- Deduplicate against previously imported rows via a content hash.
"""

import csv
import io
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from . import transactions as txn_service

COLUMN_SYNONYMS: dict[str, list[str]] = {
    "date": ["date", "transaction date", "posted date", "posting date", "post date",
             "trans date", "value date", "datetime", "booking date", "posted"],
    "amount": ["amount", "transaction amount", "amt", "value", "total"],
    "debit": ["debit", "withdrawal", "withdrawals", "outflow", "money out",
              "paid out", "spent", "debit amount"],
    "credit": ["credit", "deposit", "deposits", "inflow", "money in",
               "paid in", "received", "credit amount"],
    "payee": ["payee", "description", "merchant", "name", "details",
              "narrative", "transaction description", "vendor"],
    "memo": ["memo", "notes", "note", "comment", "comments", "reference"],
    "category": ["category", "tag", "budget category", "type"],
}


def _normalize_header(h: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", h.strip().lower()).strip()


def map_columns(headers: list[str]) -> dict[str, str]:
    """Map semantic fields to actual header names. Exact synonym match wins;
    substring match is the fallback."""
    normalized = {_normalize_header(h): h for h in headers}
    mapping: dict[str, str] = {}
    for field, synonyms in COLUMN_SYNONYMS.items():
        for syn in synonyms:
            if syn in normalized and normalized[syn] not in mapping.values():
                mapping[field] = normalized[syn]
                break
        if field not in mapping:
            for norm, original in normalized.items():
                if original in mapping.values():
                    continue
                if any(syn in norm for syn in synonyms):
                    mapping[field] = original
                    break
    return mapping


_CURRENCY_JUNK = re.compile(r"[^\d,.\-()]")


def parse_amount(raw) -> int:
    """Parse a currency string to integer cents. Raises ValueError if hopeless."""
    if raw is None:
        raise ValueError("empty amount")
    if isinstance(raw, (int, float, Decimal)):
        return int(round(Decimal(str(raw)) * 100))

    s = str(raw).strip()
    if not s:
        raise ValueError("empty amount")

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s.endswith("-"):
        negative, s = True, s[:-1]
    if s.lstrip().startswith("-"):
        negative, s = True, s.lstrip()[1:]

    s = _CURRENCY_JUNK.sub("", s).strip("-")
    if not s or not re.search(r"\d", s):
        raise ValueError(f"cannot parse amount {raw!r}")

    if "," in s and "." in s:
        # Whichever separator appears last is the decimal point.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        # "12,34" is a European decimal; "1,234" / "1,234,567" are thousands.
        if len(parts) == 2 and len(parts[1]) != 3:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    try:
        value = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"cannot parse amount {raw!r}") from exc
    cents = int(round(value * 100))
    return -cents if negative else cents


_DATE_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d",
    "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y",
    "%d.%m.%Y", "%d %b %Y", "%d %B %Y",
    "%b %d, %Y", "%b %d %Y", "%B %d, %Y",
]


def parse_date(raw) -> date:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    s = str(raw).strip()
    if not s:
        raise ValueError("empty date")
    # ISO datetime ("2026-07-01T10:00:00Z", with/without offset)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # DD/MM/YYYY when the first number can't be a month.
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 and b <= 12:
            return date(y, b, a)
    raise ValueError(f"cannot parse date {raw!r}")


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("cannot decode file")


def _rows_from_json(text: str) -> tuple[list[dict], list[str]]:
    data = json.loads(text)
    if isinstance(data, dict):
        # Accept {"transactions": [...]} style wrappers.
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                data = value
                break
        else:
            raise ValueError("JSON must be a list of objects or contain one")
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError("JSON must be a list of objects")
    headers = list({k: None for row in data for k in row})
    return [{str(k): v for k, v in row.items()} for row in data], headers


def _rows_from_csv(text: str) -> tuple[list[dict], list[str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    rows = [row for row in reader if any((v or "").strip() for v in row.values())]
    return rows, [h for h in reader.fieldnames if h]


def parse_file(content: bytes, filename: str = "") -> tuple[str, list[dict], list[str]]:
    """Returns (format, rows, headers)."""
    text = _decode(content)
    stripped = text.lstrip()
    if filename.lower().endswith(".json") or stripped.startswith(("[", "{")):
        rows, headers = _rows_from_json(text)
        return "json", rows, headers
    rows, headers = _rows_from_csv(text)
    return "csv", rows, headers


def _extract_amount(row: dict, mapping: dict[str, str]) -> int:
    if "amount" in mapping:
        return parse_amount(row.get(mapping["amount"]))
    debit = row.get(mapping["debit"]) if "debit" in mapping else None
    credit = row.get(mapping["credit"]) if "credit" in mapping else None
    debit_ok = debit is not None and str(debit).strip() not in ("", "0", "0.00")
    credit_ok = credit is not None and str(credit).strip() not in ("", "0", "0.00")
    if debit_ok:
        return -abs(parse_amount(debit))
    if credit_ok:
        return abs(parse_amount(credit))
    raise ValueError("no amount, debit, or credit value")


def import_rows(
    session: Session,
    account_id: int,
    content: bytes,
    filename: str = "",
    dry_run: bool = False,
    skip_duplicates: bool = True,
    column_mapping: dict[str, str] | None = None,
) -> schemas.ImportResult:
    fmt, rows, headers = parse_file(content, filename)
    mapping = dict(column_mapping) if column_mapping else map_columns(headers)
    if "date" not in mapping:
        raise ValueError(f"could not find a date column among {headers}")
    if "amount" not in mapping and not ("debit" in mapping or "credit" in mapping):
        raise ValueError(f"could not find an amount (or debit/credit) column among {headers}")

    existing_hashes = set(
        session.execute(
            select(models.Transaction.import_hash).where(
                models.Transaction.account_id == account_id,
                models.Transaction.import_hash.is_not(None),
            )
        ).scalars()
    )

    # Category names -> ids for auto-assignment when the file has a category column.
    categories = {
        c.name.strip().lower(): c.id
        for c in session.execute(select(models.Category)).scalars()
    }

    errors: list[schemas.ImportRowError] = []
    preview: list[schemas.ImportPreviewRow] = []
    imported = skipped = 0
    seen_in_file: set[str] = set()

    for i, row in enumerate(rows, start=1):
        try:
            txn_date = parse_date(row.get(mapping["date"]))
            amount = _extract_amount(row, mapping)
            payee = str(row.get(mapping["payee"], "") or "").strip() if "payee" in mapping else ""
            memo = str(row.get(mapping["memo"], "") or "").strip() if "memo" in mapping else ""
            cat_name = (
                str(row.get(mapping["category"], "") or "").strip()
                if "category" in mapping else ""
            )
        except (ValueError, TypeError) as exc:
            errors.append(schemas.ImportRowError(row=i, error=str(exc)))
            continue

        h = txn_service.compute_import_hash(account_id, txn_date, amount, payee)
        duplicate = h in existing_hashes or h in seen_in_file
        seen_in_file.add(h)

        if len(preview) < 20:
            preview.append(schemas.ImportPreviewRow(
                date=txn_date, payee=payee, memo=memo, amount_cents=amount,
                category=cat_name or None, duplicate=duplicate,
            ))

        if duplicate and skip_duplicates:
            skipped += 1
            continue

        if not dry_run:
            txn_service.create_transaction(
                session,
                schemas.TransactionIn(
                    account_id=account_id,
                    date=txn_date,
                    payee=payee,
                    memo=memo,
                    amount_cents=amount,
                    category_id=categories.get(cat_name.lower()) if cat_name else None,
                ),
                import_hash=h,
            )
        imported += 1

    return schemas.ImportResult(
        format=fmt,
        total_rows=len(rows),
        imported=imported,
        skipped_duplicates=skipped,
        errors=errors,
        column_mapping=mapping,
        preview=preview,
        dry_run=dry_run,
    )
