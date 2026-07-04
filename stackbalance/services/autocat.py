"""Auto-categorization: payee -> category rules.

Used in two places: the importer consults the rules for rows whose file
carries no usable category, and POST /categorization-rules/apply backfills
existing uncategorized transactions.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models


def load_rules(session: Session) -> list[models.CategorizationRule]:
    return session.execute(select(models.CategorizationRule)).scalars().all()


def match(rules: list[models.CategorizationRule], payee: str) -> int | None:
    """Return the winning rule's category id, or None.

    Exact match (case-insensitive) beats contains; among contains matches the
    longest pattern wins so "trader joe's #5" beats "joe".
    """
    needle = payee.strip().lower()
    if not needle:
        return None
    best_contains: models.CategorizationRule | None = None
    for rule in rules:
        pattern = rule.pattern.strip().lower()
        if not pattern:
            continue
        if rule.match_type == "exact":
            if pattern == needle:
                return rule.category_id
        elif pattern in needle:
            if best_contains is None or len(pattern) > len(best_contains.pattern.strip()):
                best_contains = rule
    return best_contains.category_id if best_contains else None


def upsert_rule(session: Session, pattern: str, match_type: str,
                category_id: int) -> models.CategorizationRule:
    """Create the rule, or repoint an existing identical pattern."""
    existing = session.execute(
        select(models.CategorizationRule).where(
            models.CategorizationRule.pattern == pattern,
            models.CategorizationRule.match_type == match_type,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.category_id = category_id
        session.commit()
        return existing
    rule = models.CategorizationRule(
        pattern=pattern, match_type=match_type, category_id=category_id)
    session.add(rule)
    session.commit()
    return rule


def apply_to_existing(session: Session, dry_run: bool = False) -> int:
    """Categorize existing transactions that are fully uncategorized
    (single null-category split, not a transfer, payee present)."""
    rules = load_rules(session)
    if not rules:
        return 0
    txns = session.execute(
        select(models.Transaction)
        .options(selectinload(models.Transaction.splits))
        .where(models.Transaction.transfer_peer_id.is_(None))
        .where(models.Transaction.payee != "")
    ).scalars().all()

    changed = 0
    for txn in txns:
        if len(txn.splits) != 1 or txn.splits[0].category_id is not None:
            continue
        category_id = match(rules, txn.payee)
        if category_id is None:
            continue
        if not dry_run:
            txn.splits[0].category_id = category_id
        changed += 1
    if not dry_run:
        session.commit()
    return changed
