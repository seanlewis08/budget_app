"""
Priority Cascade Categorization Engine

Tier 1: Amount Rules — Apple/Venmo disambiguation by exact amount
Tier 2: Merchant Mappings — 200+ regex patterns from notebook history
Tier 3: Claude API — Few-shot for unknown merchants (fallback)

Once a transaction matches at any tier, processing STOPS.
No overwrites possible — this fixes the flat-loop bug from the notebooks.
"""

import os
import re
import logging
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

AUTO_CONFIRM_THRESHOLD = 3  # Merchant mapping confidence needed for auto-confirm


def categorize_transaction(
    description: str,
    amount: float,
    db: Session,
    use_ai: bool = True,
) -> dict:
    """
    Run a transaction through the priority cascade.

    Returns:
        {
            "category_id": int or None,
            "short_desc": str or None,
            "tier": "amount_rule" | "merchant_map" | "ai" | None,
            "status": "auto_confirmed" | "pending_review",
            "confidence": float,
        }
    """
    from ..models import AmountRule, MerchantMapping, Category

    desc_upper = description.upper().strip()

    # ── TIER 1: Amount Rules ──
    result = _check_amount_rules(desc_upper, amount, db)
    if result:
        logger.info(f"Tier 1 match: {description} → {result['short_desc']}")
        return result

    # ── TIER 2: Merchant Mappings ──
    result = _check_merchant_mappings(desc_upper, db)
    if result:
        logger.info(f"Tier 2 match: {description} → {result['short_desc']} (conf={result['confidence']})")
        return result

    # ── TIER 3: Claude API (if enabled) ──
    if use_ai and os.getenv("ANTHROPIC_API_KEY"):
        result = _classify_with_ai(description, amount, db)
        if result:
            logger.info(f"Tier 3 AI: {description} → {result['short_desc']}")
            return result

    # No match at any tier
    logger.info(f"No match: {description}")
    return {
        "category_id": None,
        "short_desc": None,
        "tier": None,
        "status": "pending_review",
        "confidence": 0,
    }


def _check_amount_rules(desc_upper: str, amount: float, db: Session) -> Optional[dict]:
    """Tier 1: Check amount-based rules (Apple/Venmo disambiguation)."""
    from ..models import AmountRule, Category

    # Get all amount rules
    rules = db.query(AmountRule).all()

    for rule in rules:
        pattern = rule.description_pattern.upper()
        if pattern in desc_upper:
            if abs(amount - rule.amount) <= rule.tolerance:
                category = db.query(Category).get(rule.category_id)
                if category:
                    return {
                        "category_id": category.id,
                        "short_desc": category.short_desc,
                        "tier": "amount_rule",
                        "status": "auto_confirmed",
                        "confidence": 1.0,
                    }

    return None


def _check_merchant_mappings(desc_upper: str, db: Session) -> Optional[dict]:
    """Tier 2: Check merchant pattern mappings."""
    from ..models import MerchantMapping, Category

    # Get all mappings, ordered by pattern length (longest = most specific first)
    mappings = (
        db.query(MerchantMapping)
        .order_by(MerchantMapping.merchant_pattern.desc())
        .all()
    )

    best_match = None
    best_match_len = 0

    for mapping in mappings:
        pattern = mapping.merchant_pattern.upper()
        try:
            if re.search(pattern, desc_upper):
                # Prefer longest (most specific) match
                if len(pattern) > best_match_len:
                    best_match = mapping
                    best_match_len = len(pattern)
        except re.error:
            # If pattern isn't valid regex, try literal match
            if pattern in desc_upper:
                if len(pattern) > best_match_len:
                    best_match = mapping
                    best_match_len = len(pattern)

    if best_match:
        category = db.query(Category).get(best_match.category_id)
        if category:
            status = (
                "auto_confirmed"
                if best_match.confidence >= AUTO_CONFIRM_THRESHOLD
                else "pending_review"
            )
            return {
                "category_id": category.id,
                "short_desc": category.short_desc,
                "tier": "merchant_map",
                "status": status,
                "confidence": best_match.confidence,
            }

    return None


def _classify_with_ai(description: str, amount: float, db: Session) -> Optional[dict]:
    """Tier 3: Use Claude API for unknown merchants with few-shot examples."""
    from ..models import Category

    try:
        import anthropic

        client = anthropic.Anthropic()

        # Build the list of valid categories for the prompt
        categories = (
            db.query(Category)
            .filter(Category.parent_id.isnot(None))  # Only subcategories
            .all()
        )

        category_list = "\n".join(
            f"- {cat.short_desc} ({cat.parent.display_name if cat.parent else 'Uncategorized'})"
            for cat in categories
        )

        # Get some recent confirmed transactions as few-shot examples
        from ..models import Transaction
        examples = (
            db.query(Transaction)
            .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
            .filter(Transaction.category_id.isnot(None))
            .order_by(Transaction.created_at.desc())
            .limit(50)
            .all()
        )

        examples_text = "\n".join(
            f'"{ex.description}" ${ex.amount} → {ex.category.short_desc}'
            for ex in examples
            if ex.category
        )

        prompt = f"""You are a personal finance categorization assistant. Given a bank transaction description and amount, classify it into one of the user's personal categories.

VALID CATEGORIES:
{category_list}

EXAMPLES FROM THIS USER'S HISTORY:
{examples_text}

TRANSACTION TO CLASSIFY:
Description: "{description}"
Amount: ${amount}

Respond with ONLY the short_desc category name, nothing else. If unsure, respond with your best guess."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )

        predicted = response.content[0].text.strip().lower()

        # Validate the prediction is a real category
        category = db.query(Category).filter(Category.short_desc == predicted).first()
        if category:
            return {
                "category_id": category.id,
                "short_desc": category.short_desc,
                "tier": "ai",
                "status": "pending_review",  # AI predictions always need review
                "confidence": 0.7,
            }

    except Exception as e:
        logger.warning(f"AI categorization failed: {e}")

    return None
