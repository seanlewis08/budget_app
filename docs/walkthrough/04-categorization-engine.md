# Part 4 — Transaction Processing & Categorization

This part covers the 3-tier categorization engine, the transaction review workflow, CSV import for historical data, and the seed data that bootstraps the system.

---

## 4.1 The 3-Tier Categorization Engine

Every transaction that enters the system — whether from Plaid or CSV import — is run through a priority cascade of three categorization tiers:

```
Transaction arrives
       ↓
  Tier 1: Amount Rules (exact amount match)
       ↓ (miss)
  Tier 2: Merchant Mappings (pattern match)
       ↓ (miss)
  Tier 3: Claude AI (fallback)
```

Once a tier matches, processing stops. The tier that matched is recorded in `categorization_tier`, and the confidence level determines whether the transaction is auto-confirmed or sent to the review queue.

### `backend/services/categorize.py`

```python
"""
3-tier transaction categorization engine.

Priority:
  1. Amount Rules — exact amount match for ambiguous merchants (Apple, Venmo)
  2. Merchant Mappings — regex pattern match against known merchants
  3. Claude AI — LLM fallback for unknown merchants
"""

import re
import os
import logging
from anthropic import Anthropic
from ..models import AmountRule, MerchantMapping, Category, Transaction

logger = logging.getLogger(__name__)

AUTO_CONFIRM_THRESHOLD = 3  # Merchant mapping confidence needed for auto-confirm


def categorize_transaction(transaction, db):
    """Run the transaction through all three tiers. Mutates the transaction in place."""

    description = (transaction.description or "").lower()
    merchant = (transaction.merchant_name or transaction.description or "").lower()
    amount = transaction.amount

    # ── Tier 1: Amount Rules ──
    rules = db.query(AmountRule).all()
    for rule in rules:
        pattern = rule.description_pattern.lower()
        if pattern in description:
            if abs(amount - rule.amount) <= rule.tolerance:
                transaction.predicted_category_id = rule.category_id
                transaction.category_id = rule.category_id
                transaction.categorization_tier = "amount_rule"
                transaction.prediction_confidence = 1.0
                transaction.status = "auto_confirmed"
                logger.info(
                    f"Tier 1 match: {description} ${amount} → {rule.short_desc}"
                )
                return {
                    "category_id": rule.category_id,
                    "short_desc": rule.short_desc,
                    "tier": "amount_rule",
                    "status": "auto_confirmed",
                    "confidence": 1.0,
                }

    # ── Tier 2: Merchant Mappings ──
    mappings = (
        db.query(MerchantMapping)
        .order_by(MerchantMapping.confidence.desc())
        .all()
    )
    for mapping in mappings:
        try:
            if re.search(mapping.merchant_pattern, merchant, re.IGNORECASE):
                category = db.query(Category).get(mapping.category_id)
                confidence = mapping.confidence
                transaction.predicted_category_id = mapping.category_id
                transaction.categorization_tier = "merchant_map"
                transaction.prediction_confidence = confidence / 10.0

                if confidence >= AUTO_CONFIRM_THRESHOLD:
                    transaction.category_id = mapping.category_id
                    transaction.status = "auto_confirmed"
                else:
                    transaction.status = "pending_review"

                return {
                    "category_id": mapping.category_id,
                    "short_desc": category.short_desc if category else None,
                    "tier": "merchant_map",
                    "status": transaction.status,
                    "confidence": confidence,
                }
        except re.error:
            # Invalid regex — try as literal string
            if mapping.merchant_pattern.lower() in merchant:
                # Same logic as above...
                pass

    # ── Tier 3: Claude AI ──
    result = _categorize_with_ai(transaction, db)
    if result:
        transaction.predicted_category_id = result["category_id"]
        transaction.categorization_tier = "ai"
        transaction.prediction_confidence = 0.7
        transaction.status = "pending_review"  # AI never auto-confirms
        return result

    # No match at any tier
    transaction.status = "pending_review"
    return None
```

### Tier 1: Amount Rules

Amount rules solve the "Apple problem" — when one merchant (like Apple or Venmo) charges different amounts for different services. For example:

| Merchant | Amount | Category |
|----------|--------|----------|
| APPLE.COM/BILL | $15.89 | HBO Max |
| APPLE.COM/BILL | $6.99 | iCloud Storage |
| APPLE.COM/BILL | $9.99 | Apple TV+ |
| VENMO | $816.87 | Rent |

The rule matches by description pattern AND exact amount (within a tolerance of $0.01). When matched, the transaction is auto-confirmed with 1.0 confidence — there's no ambiguity.

### Tier 2: Merchant Mappings

Merchant mappings are regex patterns that match merchant names to categories. They're ordered by confidence (highest first), and the confidence level determines auto-confirm behavior:

- **Confidence >= 3**: Auto-confirmed (reliable pattern seen multiple times)
- **Confidence < 3**: Sent to review queue (newer pattern, needs verification)

When a user confirms a transaction in the review queue, the system creates or updates a merchant mapping, incrementing its confidence. Over time, frequently-seen merchants accumulate enough confidence to be auto-confirmed.

### Tier 3: Claude AI Fallback

For merchants not matched by rules or mappings, Claude AI provides a best-guess categorization:

```python
def _categorize_with_ai(transaction, db):
    """Use Claude to categorize an unknown transaction."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    client = Anthropic(api_key=api_key)

    # Get available categories
    categories = db.query(Category).filter(Category.parent_id.isnot(None)).all()
    category_list = "\n".join(
        f"- {cat.short_desc} ({cat.display_name})" for cat in categories
    )

    # Get recent confirmed transactions as few-shot examples
    recent = (
        db.query(Transaction)
        .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
        .order_by(Transaction.date.desc())
        .limit(20)
        .all()
    )
    examples = "\n".join(
        f"- {t.merchant_name or t.description} → {t.category.short_desc}"
        for t in recent if t.category
    )

    prompt = f"""Categorize this bank transaction into one of these categories.

Transaction:
  Description: {transaction.description}
  Merchant: {transaction.merchant_name}
  Amount: ${transaction.amount}

Available categories:
{category_list}

Recent examples:
{examples}

Respond with ONLY the short_desc value. Nothing else."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=50,
        messages=[{"role": "user", "content": prompt}],
    )

    predicted = response.content[0].text.strip().lower()

    # Look up the predicted category
    category = (
        db.query(Category)
        .filter(Category.short_desc == predicted)
        .first()
    )

    if category:
        return {
            "category_id": category.id,
            "short_desc": category.short_desc,
            "tier": "ai",
            "status": "pending_review",
            "confidence": 0.7,
        }
    return None
```

Key design decisions:

- Uses **Claude Haiku** for speed and cost efficiency (categorization happens per-transaction)
- **Few-shot examples**: Includes 20 recently confirmed transactions so the model learns from the user's actual labeling patterns
- **Always pending_review**: AI predictions are never auto-confirmed — the user must verify
- **0.7 confidence**: A reasonable default that distinguishes AI predictions from rule-based certainty

---

## 4.2 Transaction Review Workflow

The transaction status lifecycle is:

```
pending_review → pending_save (staged) → confirmed
                       ↑                      ↑
                 auto_confirmed ──────────────┘
```

### Reviewing a Transaction

When a user confirms a category in the review queue, the backend:

1. Sets `category_id` to the chosen category
2. Updates `status` to `"pending_save"` (staged)
3. Creates or updates a merchant mapping for future auto-categorization

```python
@router.post("/{transaction_id}/review")
def review_transaction(transaction_id: int, body: dict, db: Session = Depends(get_db)):
    txn = db.query(Transaction).get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404)

    category_id = body.get("category_id")
    category = db.query(Category).get(category_id)

    txn.category_id = category_id
    txn.status = "pending_save"

    # Learn from this review: create/update merchant mapping
    merchant = (txn.merchant_name or txn.description or "").strip()
    if merchant:
        existing = db.query(MerchantMapping).filter(
            MerchantMapping.merchant_pattern == merchant.lower()
        ).first()
        if existing:
            existing.category_id = category_id
            existing.confidence = min(existing.confidence + 1, 10)
        else:
            db.add(MerchantMapping(
                merchant_pattern=merchant.lower(),
                category_id=category_id,
                confidence=1,
            ))

    db.commit()
    return {"status": "reviewed", "category": category.short_desc}
```

### Staging and Committing

The two-phase review (pending_review → pending_save → confirmed) lets users batch-review transactions, inspect their choices in the "staged" section, and then commit everything at once. The commit endpoint simply updates all staged transactions:

```python
@router.post("/commit")
def commit_staged(db: Session = Depends(get_db)):
    staged = db.query(Transaction).filter(
        Transaction.status == "pending_save"
    ).all()
    for txn in staged:
        txn.status = "confirmed"
    db.commit()
    return {"committed": len(staged)}
```

---

## 4.3 CSV Import (`backend/routers/import_csv.py`)

Before Plaid is connected, historical transactions can be imported from bank CSV downloads. The importer supports multiple bank formats:

```python
@router.post("")
async def import_csv(
    file: UploadFile,
    bank: str,  # "discover", "sofi_checking", "sofi_savings", "wellsfargo"
    db: Session = Depends(get_db),
):
    df = pd.read_csv(file.file)

    # Normalize columns based on bank format
    if bank == "discover":
        df = df.rename(columns={
            "Trans. Date": "date",
            "Description": "description",
            "Amount": "amount",
        })
        # Discover: positive = expense (debit), negative = payment (credit)
    elif bank == "sofi_checking":
        df = df.rename(columns={
            "Date": "date",
            "Description": "description",
            "Amount": "amount",
        })
        # SoFi: negative = expense, positive = income
        df["amount"] = -df["amount"]  # Flip to match Plaid convention
    # ... similar for other banks

    # Find the matching account
    account = db.query(Account).filter(
        Account.institution == bank.split("_")[0]
    ).first()

    imported = 0
    skipped = 0
    for _, row in df.iterrows():
        # Dedup check
        existing = db.query(Transaction).filter(
            Transaction.account_id == account.id,
            Transaction.date == row["date"],
            Transaction.description == row["description"],
            Transaction.amount == row["amount"],
        ).first()
        if existing:
            skipped += 1
            continue

        txn = Transaction(
            account_id=account.id,
            date=row["date"],
            description=row["description"],
            merchant_name=row["description"],
            amount=row["amount"],
            source="csv_import",
            status="pending_review",
        )
        db.add(txn)
        db.flush()

        # Auto-categorize
        categorize_transaction(txn, db)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}
```

The auto-detect endpoint identifies the bank format from CSV headers:

```python
@router.post("/auto-detect")
async def auto_detect_bank(file: UploadFile):
    content = await file.read()
    header = content.decode().split("\n")[0].lower()

    if "trans. date" in header:
        return {"bank": "discover"}
    elif "sofi" in header or ("date" in header and "amount" in header):
        return {"bank": "sofi_checking"}
    elif "wells fargo" in header:
        return {"bank": "wellsfargo"}
    return {"bank": "unknown"}
```

---

## 4.4 Seed Data (`backend/services/seed_data.py`)

The seed function populates the database with default categories, accounts, amount rules, and high-confidence merchant mappings on first startup. It's idempotent — calling it multiple times has no effect.

### Parent Categories (18)

```python
PARENT_CATEGORIES = [
    {"short_desc": "Food", "display_name": "Food", "color": "#FF6B6B"},
    {"short_desc": "Housing", "display_name": "Housing", "color": "#4ECDC4"},
    {"short_desc": "Transportation", "display_name": "Transportation", "color": "#45B7D1"},
    {"short_desc": "Insurance", "display_name": "Insurance", "color": "#96CEB4"},
    {"short_desc": "Utilities", "display_name": "Utilities", "color": "#FFEAA7"},
    {"short_desc": "Medical", "display_name": "Medical", "color": "#DDA0DD"},
    {"short_desc": "Government", "display_name": "Government", "color": "#778899"},
    {"short_desc": "Savings", "display_name": "Savings", "color": "#98D8C8"},
    {"short_desc": "Personal_Spending", "display_name": "Personal Spending", "color": "#F7DC6F"},
    {"short_desc": "Recreation_Entertainment", "display_name": "Recreation & Entertainment", "color": "#BB8FCE"},
    {"short_desc": "Streaming_Services", "display_name": "Streaming Services", "color": "#E74C3C"},
    {"short_desc": "Education", "display_name": "Education", "color": "#3498DB"},
    {"short_desc": "Travel", "display_name": "Travel", "color": "#E67E22"},
    {"short_desc": "Misc", "display_name": "Miscellaneous", "color": "#95A5A6"},
    {"short_desc": "People", "display_name": "People", "color": "#1ABC9C"},
    {"short_desc": "Payment_and_Interest", "display_name": "Payment & Interest", "color": "#7F8C8D"},
    {"short_desc": "Income", "display_name": "Income", "color": "#2ECC71", "is_income": True},
    {"short_desc": "Balance", "display_name": "Balance Adjustments", "color": "#BDC3C7"},
]
```

### Subcategories (80+)

Each parent has multiple children. For example, "Food" has:

- Groceries, Fast Food, Restaurant, Coffee, Alcohol, Snacks/Convenience

And "Streaming Services" has individual services as subcategories:

- Netflix, Spotify, Hulu, Disney Plus, YouTube Premium, HBO, Apple TV, iCloud, etc.

Each subcategory can have `is_recurring=True` for the recurring monitor.

### Default Accounts (4)

```python
DEFAULT_ACCOUNTS = [
    {"name": "Discover Card", "institution": "discover", "account_type": "credit"},
    {"name": "SoFi Checking", "institution": "sofi", "account_type": "checking"},
    {"name": "SoFi Savings", "institution": "sofi", "account_type": "savings"},
    {"name": "Wells Fargo Checking", "institution": "wellsfargo", "account_type": "checking"},
]
```

### Initial Merchant Mappings (50+)

High-confidence mappings imported from analysis notebooks:

```python
SEED_MAPPINGS = [
    ("safeway", "groceries", 5),
    ("trader joe", "groceries", 5),
    ("target", "groceries", 4),
    ("netflix", "netflix", 5),
    ("spotify", "spotify", 5),
    ("shell oil", "gas_station", 5),
    ("chevron", "gas_station", 5),
    ("uber", "rideshare", 4),
    # ... 40+ more
]
```

The confidence values start at 4–5 (well above the auto-confirm threshold of 3), so these common merchants are auto-categorized from day one.

---

## 4.5 Transaction Analysis Endpoints

The transactions router also provides several analysis endpoints for the frontend charts:

### Spending by Category

```python
@router.get("/spending-by-category")
def spending_by_category(month: str, db: Session = Depends(get_db)):
    """Monthly spending grouped by subcategory, excluding transfers."""
    # Groups by category, sums amounts, excludes income and balance categories
```

### Monthly Trend

```python
@router.get("/monthly-trend")
def monthly_trend(months: int = 12, db: Session = Depends(get_db)):
    """Monthly spending totals for the trend line chart."""
```

### Cash Flow

```python
@router.get("/cash-flow")
def cash_flow(year: int, db: Session = Depends(get_db)):
    """Biweekly cash flow with income and expense breakdowns."""
```

### Recurring Monitor

```python
@router.get("/recurring-monitor")
def recurring_monitor(year: int, db: Session = Depends(get_db)):
    """Monthly grid of recurring transactions for tracking subscriptions."""
```

These endpoints are consumed by the corresponding frontend pages covered in Part 5.

---

## 4.6 Soft Delete and Restore

Deleting a transaction copies it to the `deleted_transactions` audit log before removing it:

```python
@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    txn = db.query(Transaction).get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404)

    # Archive to deleted_transactions
    db.add(DeletedTransaction(
        original_id=txn.id,
        account_id=txn.account_id,
        account_name=txn.account.name if txn.account else None,
        date=txn.date,
        description=txn.description,
        merchant_name=txn.merchant_name,
        amount=txn.amount,
        category_name=txn.category.short_desc if txn.category else None,
        status=txn.status,
        source=txn.source,
    ))
    db.delete(txn)
    db.commit()
    return {"status": "deleted"}
```

The deleted transactions page can restore entries back to the main table or permanently purge them.

---

## What's Next

With the backend fully operational — syncing, categorizing, and storing transactions — Part 5 builds the entire React frontend: 13+ pages, routing, charts, and styles.

→ [Part 5: Frontend & React UI](05-frontend-react.md)
