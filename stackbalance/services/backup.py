"""One-click portable backups.

A backup is a zip containing:
- data.json  — full export of every table, version-tagged and human-readable
- stackbalance.db — consistent snapshot of the SQLite file (via the backup API)
- manifest.json — app version, timestamp, row counts

Restore replays data.json into a wiped database, so backups stay portable
across machines and (with care) schema versions.
"""

import io
import json
import sqlite3
import zipfile
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import config, models

# Restore order respects foreign keys (accounts reference categories via
# payment_category_id, so categories come first).
_TABLES: list[tuple[str, type]] = [
    ("category_groups", models.CategoryGroup),
    ("categories", models.Category),
    ("accounts", models.Account),
    ("recurring_rules", models.RecurringRule),
    ("transactions", models.Transaction),
    ("splits", models.Split),
    ("budget_allocations", models.BudgetAllocation),
    ("sinking_funds", models.SinkingFund),
    ("categorization_rules", models.CategorizationRule),
]


def _row_to_dict(obj) -> dict:
    out = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        out[column.name] = value
    return out


def export_json(session: Session) -> dict:
    data: dict = {"app": "stack-balance", "schema_version": 1,
                  "exported_at": datetime.utcnow().isoformat()}
    for name, model in _TABLES:
        rows = session.execute(select(model)).scalars().all()
        data[name] = [_row_to_dict(r) for r in rows]
    return data


def create_backup(session: Session) -> tuple[str, bytes]:
    data = export_json(session)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"stackbalance-backup-{stamp}.zip"

    # Consistent SQLite snapshot even with WAL and open connections.
    db_snapshot = io.BytesIO()
    src = sqlite3.connect(config.db_path())
    try:
        dest = sqlite3.connect(":memory:")
        src.backup(dest)
        db_snapshot.write(b"".join(f"{line}\n".encode() for line in dest.iterdump()))
        dest.close()
    finally:
        src.close()

    manifest = {
        "app": "stack-balance",
        "schema_version": 1,
        "created_at": datetime.utcnow().isoformat(),
        "counts": {name: len(data[name]) for name, _ in _TABLES},
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(data, indent=2))
        zf.writestr("stackbalance.sql", db_snapshot.getvalue())
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    payload = buf.getvalue()
    (config.backups_dir() / filename).write_bytes(payload)
    return filename, payload


def list_backups() -> list[dict]:
    out = []
    for path in sorted(config.backups_dir().glob("*.zip"), reverse=True):
        stat = path.stat()
        out.append({
            "filename": path.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime),
        })
    return out


_DATE_FIELDS = {"date", "next_date", "end_date", "target_date"}
_DATETIME_FIELDS = {"created_at"}


def _coerce(model, row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if key not in model.__table__.columns:
            continue
        if value is not None and key in _DATE_FIELDS:
            value = date.fromisoformat(value)
        elif value is not None and key in _DATETIME_FIELDS:
            value = datetime.fromisoformat(value)
        out[key] = value
    return out


def restore_backup(session: Session, content: bytes) -> dict[str, int]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = zf.namelist()
        if "data.json" not in names:
            raise ValueError("not a stack-balance backup: data.json missing")
        data = json.loads(zf.read("data.json"))
    if data.get("app") != "stack-balance":
        raise ValueError("not a stack-balance backup")

    # Wipe in reverse dependency order, then reload with original ids.
    for _name, model in reversed(_TABLES):
        session.execute(delete(model))
    counts: dict[str, int] = {}
    transfer_links: list[tuple[int, int]] = []
    for name, model in _TABLES:
        rows = data.get(name, [])
        for row in rows:
            coerced = _coerce(model, row)
            # Transfer pairs reference each other; insert with the link
            # stripped, then restore it in a second pass so the FK holds.
            if name == "transactions" and coerced.get("transfer_peer_id") is not None:
                transfer_links.append((coerced["id"], coerced.pop("transfer_peer_id")))
            session.add(model(**coerced))
        counts[name] = len(rows)
    session.flush()
    for txn_id, peer_id in transfer_links:
        txn = session.get(models.Transaction, txn_id)
        if txn is not None:
            txn.transfer_peer_id = peer_id
    session.commit()
    # SQLite integer PKs are rowids: next id is max(id)+1, so restoring with
    # explicit ids needs no sequence fixup.
    return counts
