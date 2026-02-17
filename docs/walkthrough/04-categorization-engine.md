# Part 4 — Transaction Processing & Categorization

Every transaction that enters the system — whether from Plaid syncing or a CSV upload — runs through a three-tier categorization engine before it reaches the user. This part covers that engine in detail, along with the review workflow that lets users train the system over time, the CSV import pipeline, and the analytics endpoints that power the frontend charts.

By the end of this part, you'll understand the full lifecycle of a transaction: arrival → categorization → staging → confirmation → analytics.

---

## 4.1 The 3-Tier Categorization Engine

The categorization engine is a priority cascade. When a transaction arrives, it's tested against three tiers in order. The first tier that produces a match wins — subsequent tiers are skipped.

```
Transaction arrives (from Plaid sync or CSV import)
       ↓
  Tier 1: Amount Rules
    Match on description pattern + exact dollar amount
    Result: auto_confirmed (confidence 1.0)
       ↓ (no match)
  Tier 2: Merchant Mappings
    Match on merchant name pattern (regex or literal)
    Result: auto_confirmed if confidence ≥ 3, else pending_review
       ↓ (no match)
  Tier 3: Claude AI
    Send description + amount + few-shot examples to Claude Haiku
    Result: always pending_review (confidence 0.7)
       ↓ (no match or AI unavailable)
  No categorization — pending_review with no prediction
```

This cascade design is intentional. Tier 1 rules are the most specific and fastest (exact amount matches). Tier 2 mappings are broader (merchant name patterns) and grow automatically as users confirm predictions. Tier 3 AI is the most flexible but slowest and requires an API key. Each tier is independent — the app works fine with just Tiers 1 and 2 if you don't have an Anthropic API key.

### `backend/services/categorize.py`

```python
"""
Priority Cascade Categorization Engine

Tier 1: Amount Rules — Apple/Venmo disambiguation by exact amount
Tier 2: Merchant Mappings — regex patterns from merchant history
Tier 3: Claude API — Few-shot for unknown merchants (fallback)

Once a transaction matches at any tier, processing STOPS.
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
        return result

    # ── TIER 2: Merchant Mappings ──
    result = _check_merchant_mappings(desc_upper, db)
    if result:
        return result

    # ── TIER 3: Claude API (if enabled) ──
    if use_ai and os.getenv("ANTHROPIC_API_KEY"):
        result = _classify_with_ai(description, amount, db)
        if result:
            return result

    # No match at any tier
    return {
        "category_id": None,
        "short_desc": None,
        "tier": None,
        "status": "pending_review",
        "confidence": 0,
    }
```

The function signature takes a `description` and `amount` (not a Transaction object), which makes it easy to test and call from multiple contexts — both the Plaid sync and CSV import pass these in.

### Tier 1: Amount Rules

Amount rules solve a specific problem: merchants that charge different amounts for completely different services. The classic example is Apple billing. "APPLE.COM/BILL" shows up for Apple TV+ ($9.99), iCloud Storage ($2.99), Apple Music ($10.99), HBO Max ($15.89), and more. The description is identical — only the dollar amount tells them apart.

```python
def _check_amount_rules(desc_upper: str, amount: float, db: Session) -> Optional[dict]:
    """Tier 1: Check amount-based rules."""
    from ..models import AmountRule, Category

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
```

The matching logic is simple: if the description contains the pattern AND the amount is within tolerance, it's a match. The tolerance (usually $0.01–$0.50) handles minor price fluctuations like tax adjustments. Amount rules always auto-confirm with 1.0 confidence because they're the most specific match possible.

### Tier 2: Merchant Mappings

Merchant mappings match merchant names to categories using patterns. These are both pre-seeded (common merchants like Starbucks, Target, Netflix) and learned from user confirmations.

```python
def _check_merchant_mappings(desc_upper: str, db: Session) -> Optional[dict]:
    """Tier 2: Check merchant pattern mappings."""
    from ..models import MerchantMapping, Category

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
                "confidence": min(best_match.confidence / AUTO_CONFIRM_THRESHOLD, 1.0),
            }

    return None
```

There are two important design decisions here:

**Longest match wins.** If both "STARBUCKS" and "STARBUCKS RESERVE" match, the longer pattern takes priority. This prevents a general "TARGET" mapping from overriding a more specific "TARGET OPTICAL" mapping.

**Confidence determines auto-confirm.** The `AUTO_CONFIRM_THRESHOLD` is 3 — meaning a merchant mapping needs to be confirmed at least 3 times before future matches skip the review queue. This prevents a single incorrect confirmation from auto-categorizing all future transactions wrong.

**Regex with literal fallback.** Patterns are tried as regex first, then as literal substrings if the regex is invalid. This means you can have simple patterns like "STARBUCKS" (literal match) and sophisticated patterns like "SAFEWAY.*#\d+" (regex match).

### Tier 3: Claude AI

For transactions that don't match any rules or mappings, the AI provides a best-guess categorization using Claude Haiku (chosen for speed and cost — categorization happens per-transaction):

```python
def _classify_with_ai(description: str, amount: float, db: Session) -> Optional[dict]:
    """Tier 3: Use Claude API for unknown merchants with few-shot examples."""
    from ..models import Category, Transaction

    try:
        import anthropic
        client = anthropic.Anthropic()

        # Build the list of valid categories
        categories = (
            db.query(Category)
            .filter(Category.parent_id.isnot(None))  # Only subcategories
            .all()
        )
        category_list = "\n".join(
            f"- {cat.short_desc} ({cat.parent.display_name if cat.parent else 'Uncategorized'})"
            for cat in categories
        )

        # Get recent confirmed transactions as few-shot examples
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
            for ex in examples if ex.category
        )

        prompt = f"""You are a personal finance categorization assistant.
Given a bank transaction description and amount, classify it into one
of the user's personal categories.

VALID CATEGORIES (respond with one of these exact short_desc values):
{category_list}

EXAMPLES FROM THIS USER'S HISTORY:
{examples_text}

TRANSACTION TO CLASSIFY:
Description: "{description}"
Amount: ${amount}

Respond with ONLY the exact short_desc value. No explanation, no quotes,
no punctuation — just the short_desc."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )

        predicted = response.content[0].text.strip().lower()
```

The prompt design has several important features:

**Constrained output.** The prompt asks for ONLY the `short_desc` value — no explanation, no punctuation. This makes parsing reliable. The model returns something like `fast_food` or `groceries`.

**Few-shot examples from user history.** Including 50 recently confirmed transactions teaches the model the user's specific categorization patterns. If you always categorize DoorDash as "food_delivery" instead of "fast_food," the examples convey that preference.

**Parent category context.** Each category in the list includes its parent (e.g., "groceries (Food)"), which helps the model understand the taxonomy structure.

**Fuzzy matching on the response.** After getting the AI's response, the code tries multiple matching strategies: exact match, underscore/space normalization, and substring matching. This handles cases where the AI returns "fast food" instead of "fast_food" or "grocery" instead of "groceries".

AI predictions are always set to `pending_review` — they're never auto-confirmed. The 0.7 confidence score distinguishes them from the higher-confidence rule-based matches.

---

## 4.2 The Review Workflow

Transactions flow through a staging pipeline before becoming permanent:

```
                              ┌─── auto_confirmed ───────────────────────┐
                              │    (high-confidence Tier 1/2 match)     │
                              │                                          ↓
arriving ─→ pending_review ─→ pending_save ─→ confirmed
               (needs review)    (staged)       (finalized)
                    ↑               │
                    └── kick_back ──┘  (user changes mind)
```

This two-phase approach (stage then commit) lets users batch-review transactions: quickly categorize a bunch, inspect the staged list for mistakes, and commit everything at once.

### Staging a Transaction

When a user picks a category for a transaction, it's staged (not immediately committed):

```python
@router.post("/{transaction_id}/stage")
def stage_transaction(transaction_id: int, action: ReviewAction, db: Session = Depends(get_db)):
    """Stage a transaction with a category (pending_save)."""
    txn = db.query(Transaction).get(transaction_id)
    category = db.query(Category).filter(
        Category.short_desc == action.category_short_desc
    ).first()

    txn.category_id = category.id
    txn.status = "pending_save"
    db.commit()
```

### Bulk Staging

For efficiency, multiple transactions can be staged at once — either confirming the AI's predictions or assigning a new category to all of them:

```python
@router.post("/bulk-stage")
def bulk_stage(action: BulkReviewAction, db: Session = Depends(get_db)):
    """Bulk stage: confirm predicted categories for multiple transactions."""
    transactions = db.query(Transaction).filter(
        Transaction.id.in_(action.transaction_ids)
    ).all()

    if action.action == "confirm":
        for txn in transactions:
            if txn.predicted_category_id:
                txn.category_id = txn.predicted_category_id
                txn.status = "pending_save"
    elif action.action == "change" and action.category_short_desc:
        category = db.query(Category).filter(
            Category.short_desc == action.category_short_desc
        ).first()
        for txn in transactions:
            txn.category_id = category.id
            txn.status = "pending_save"

    db.commit()
```

### Committing Staged Transactions

The commit endpoint is where the system learns. When staged transactions are committed, the system creates or updates merchant mappings based on the user's choices:

```python
@router.post("/staged/commit")
def commit_staged(db: Session = Depends(get_db)):
    """Commit all pending_save transactions and update merchant mappings."""
    transactions = db.query(Transaction).filter(
        Transaction.status == "pending_save"
    ).all()

    seen_mappings = {}  # cache to avoid duplicate inserts in same batch

    for txn in transactions:
        txn.status = "confirmed"

        # Learn from this confirmation
        if txn.merchant_name and txn.category_id:
            pattern = txn.merchant_name.upper()
            mapping = seen_mappings.get(pattern)
            if mapping is None:
                mapping = db.query(MerchantMapping).filter(
                    MerchantMapping.merchant_pattern == pattern
                ).first()

            if mapping:
                if mapping.category_id == txn.category_id:
                    mapping.confidence += 1  # Same category = more confident
                else:
                    mapping.category_id = txn.category_id
                    mapping.confidence = 1   # Changed category = reset
                seen_mappings[pattern] = mapping
            else:
                new_mapping = MerchantMapping(
                    merchant_pattern=pattern,
                    category_id=txn.category_id,
                    confidence=1,
                )
                db.add(new_mapping)
                seen_mappings[pattern] = new_mapping

    db.commit()
```

The learning mechanism works like this: every time you confirm "STARBUCKS #12345" as "Coffee," the mapping's confidence increments. After 3 confirmations, all future Starbucks transactions are auto-confirmed without human review. If you change the category (say, from "Coffee" to "Work Lunch"), the confidence resets to 1 — you'll need to confirm 3 times again at the new category.

The `seen_mappings` cache prevents a subtle bug: if you commit 10 Starbucks transactions in one batch, without the cache, each would try to INSERT a new mapping (the previous ones aren't committed to the DB yet), hitting the unique constraint. The cache ensures we update the same mapping object for all 10.

### Kick-Back and Revert

Users can undo staging, either for a single transaction or all at once:

```python
@router.post("/{transaction_id}/kick-back")
def kick_back_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Revert a staged transaction back to pending_review."""
    txn = db.query(Transaction).get(transaction_id)
    if txn.category_id and not txn.predicted_category_id:
        txn.predicted_category_id = txn.category_id
    txn.category_id = None
    txn.status = "pending_review"
    db.commit()


@router.post("/staged/revert-all")
def revert_all_staged(db: Session = Depends(get_db)):
    """Revert ALL staged transactions back to pending_review."""
    transactions = db.query(Transaction).filter(
        Transaction.status == "pending_save"
    ).all()
    for txn in transactions:
        if txn.category_id and not txn.predicted_category_id:
            txn.predicted_category_id = txn.category_id
        txn.category_id = None
        txn.status = "pending_review"
    db.commit()
```

Notice the `predicted_category_id` preservation: when kicking back, the previously assigned category is saved as the prediction, so it shows up as the default suggestion when the user reviews it again.

---

## 4.3 Batch Categorization

When you import a large CSV or want to re-categorize transactions, the batch endpoint processes them in chunks:

```python
@router.post("/batch-categorize")
def batch_categorize(limit: int = Query(default=500, le=5000), db: Session = Depends(get_db)):
    """Run the categorization cascade on uncategorized transactions."""
    from ..services.categorize import categorize_transaction

    transactions = (
        db.query(Transaction)
        .filter(Transaction.status == "pending_review")
        .filter(Transaction.predicted_category_id.is_(None))
        .filter(Transaction.category_id.is_(None))
        .filter(
            (Transaction.categorization_tier.is_(None))
            | (Transaction.categorization_tier != "unmatched")
        )
        .order_by(Transaction.date.desc())
        .limit(limit)
        .all()
    )

    stats = {"processed": 0, "auto_staged": 0, "predicted": 0, "unmatched": 0}

    for txn in transactions:
        result = categorize_transaction(txn.description, txn.amount, db, use_ai=True)

        if result["category_id"]:
            txn.categorization_tier = result["tier"]
            txn.prediction_confidence = result.get("confidence", 0)

            if result["status"] == "auto_confirmed":
                txn.category_id = result["category_id"]
                txn.status = "pending_save"
                stats["auto_staged"] += 1
            else:
                txn.predicted_category_id = result["category_id"]
                stats["predicted"] += 1
        else:
            txn.categorization_tier = "unmatched"
            stats["unmatched"] += 1

        # Commit every 50 to avoid long SQLite locks
        if stats["processed"] % 50 == 0:
            db.commit()

    db.commit()
    return stats
```

Two important details here:

**Unmatched filtering.** Transactions that don't match any tier get tagged with `categorization_tier = "unmatched"`. On the next batch run, these are skipped — the query explicitly excludes them. This prevents the engine from wasting AI API calls on the same unrecognizable transactions every time.

**Periodic commits.** The loop commits every 50 transactions to avoid holding a long SQLite write lock, which would block the UI from reading data.

---

## 4.4 CSV Import (`backend/routers/import_csv.py`)

Before connecting Plaid, you can import historical transactions from bank CSV downloads. The importer handles the tricky part: each bank has a different CSV format with different column names, date formats, and sign conventions.

```python
PARSERS = {
    "discover": parse_discover_csv,
    "sofi_checking": parse_sofi_csv,
    "sofi_savings": parse_sofi_csv,
    "wellsfargo": parse_wellsfargo_csv,
}

@router.post("/csv")
async def import_csv(
    file: UploadFile = File(...),
    bank: str = Query(..., description="Bank name"),
    db: Session = Depends(get_db),
):
    """Import a CSV file from a specific bank."""
    content = await file.read()
    text = content.decode("utf-8")

    # Find the matching account
    account = db.query(Account).filter(
        Account.institution == institution_map[bank],
        Account.account_type == account_type_map[bank],
    ).first()

    # Parse CSV into standardized rows
    rows = PARSERS[bank](text)

    imported = 0
    skipped = 0

    for row in rows:
        # Dedup: skip if same account + date + description + amount exists
        existing = db.query(Transaction).filter(
            Transaction.account_id == account.id,
            Transaction.date == row["date"],
            Transaction.description == row["description"],
            Transaction.amount == row["amount"],
        ).first()

        if existing:
            skipped += 1
            continue

        # Categorize and create
        cat_result = categorize_transaction(
            description=row["description"],
            amount=row["amount"],
            db=db,
        )

        txn = Transaction(
            account_id=account.id,
            date=row["date"],
            description=row["description"],
            merchant_name=row.get("merchant_name"),
            amount=row["amount"],
            category_id=cat_result.get("category_id") if cat_result["status"] == "auto_confirmed" else None,
            predicted_category_id=cat_result.get("category_id"),
            status=cat_result.get("status", "pending_review"),
            source="csv_import",
            categorization_tier=cat_result.get("tier"),
        )
        db.add(txn)
        imported += 1

    db.commit()
    return {"imported": imported, "skipped_duplicates": skipped}
```

### Bank-Specific Parsers

Each bank parser lives in `backend/services/csv_parsers/` and normalizes the bank's CSV format into a standard list of dicts with `date`, `description`, `amount`, and optionally `merchant_name`. The key challenge is sign conventions — each bank is different:

**Discover:** Positive amounts are expenses (debits), negative are payments (credits). This already matches our convention.

**SoFi:** Negative amounts are expenses, positive are income. Signs need to be flipped.

**Wells Fargo:** No header row, date is in a different format, and the amount columns are split between debit and credit.

The parsers handle all these differences so the rest of the system works with a uniform format.

### Auto-Detection

The auto-detect endpoint tries to identify the bank from the CSV headers:

```python
@router.post("/csv/auto-detect")
async def import_csv_auto(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Auto-detect bank format and import."""
    content = await file.read()
    text = content.decode("utf-8")
    first_line = text.split("\n")[0].strip()

    if "Trans. Date" in first_line and "Post Date" in first_line:
        bank = "discover"
    elif "Current balance" in first_line and "Status" in first_line:
        bank = "sofi_checking" if "Roundup" in text[:2000] else "sofi_savings"
    elif not any(c.isalpha() for c in first_line.split(",")[0]):
        bank = "wellsfargo"  # No header, starts with date
    else:
        raise HTTPException(status_code=400, detail="Could not auto-detect bank format")
```

---

## 4.5 Soft Delete and Restore

When you delete a transaction, it's not immediately gone. The deletion is logged to the `deleted_transactions` audit table so it can be undone:

```python
@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    txn = db.query(Transaction).get(transaction_id)

    # Copy to audit log
    log_entry = DeletedTransaction(
        original_id=txn.id,
        account_id=txn.account_id,
        account_name=txn.account.name if txn.account else None,
        date=txn.date,
        description=txn.description,
        merchant_name=txn.merchant_name,
        amount=txn.amount,
        category_name=txn.category.display_name if txn.category else None,
        status=txn.status,
        source=txn.source,
    )
    db.add(log_entry)
    db.delete(txn)
    db.commit()
```

Restoration recreates the transaction from the audit log. Since the audit log stores names (not foreign key IDs), restoration uses a best-effort category lookup:

```python
@router.post("/restore/{deleted_id}")
def restore_transaction(deleted_id: int, db: Session = Depends(get_db)):
    entry = db.query(DeletedTransaction).get(deleted_id)

    # Best-effort category resolution from stored name
    category_id = None
    if entry.category_name:
        cat = db.query(Category).filter(Category.display_name == entry.category_name).first()
        if cat:
            category_id = cat.id

    txn = Transaction(
        account_id=entry.account_id,
        date=entry.date,
        description=entry.description,
        merchant_name=entry.merchant_name,
        amount=entry.amount,
        category_id=category_id,
        status="confirmed",
        source=entry.source,
    )
    db.add(txn)
    db.delete(entry)
    db.commit()
```

Bulk delete and bulk restore endpoints work the same way, processing lists of IDs.

---

## 4.6 Analytics Endpoints

The transactions router also provides the data behind the frontend charts. These endpoints all share a pattern: they query confirmed transactions, exclude internal transfers, and aggregate by time or category.

### Transfer Exclusion

Internal transfers (moving money between your own accounts) and credit card payments create double-counting in spending reports. A $500 credit card payment looks like a $500 expense on the checking account, even though you already counted the individual purchases on the credit card. The app excludes these:

```python
EXCLUDED_CATEGORIES = {
    "transfer", "credit_card_payment", "payment",
    "discover", "roundups",
}

def _exclude_transfers(query, db):
    """Exclude transfer/payment categories AND their children."""
    excluded_parents = db.query(Category.id).filter(
        Category.short_desc.in_(EXCLUDED_CATEGORIES)
    ).all()
    excluded_ids = {row[0] for row in excluded_parents}

    # Also exclude child categories of excluded parents
    child_ids = db.query(Category.id).filter(
        Category.parent_id.in_(excluded_ids)
    ).all()
    excluded_ids.update(row[0] for row in child_ids)

    return query.filter(~Transaction.category_id.in_(excluded_ids))
```

### Spending by Category

Returns spending totals grouped by subcategory for pie charts, with parent category information for color-coding:

```python
@router.get("/spending-by-category")
def spending_by_category(month: Optional[str] = None, db: Session = Depends(get_db)):
    """Monthly spending by subcategory, with parent info."""
    # Joins Category → Transaction, groups by Category.id
    # Filters: confirmed/auto_confirmed, amount > 0 (expenses only), excludes transfers
    # Returns: [{id, short_desc, display_name, color, parent_display_name, total, count}]
```

### Monthly Trend

Returns monthly spending totals for the trend line chart:

```python
@router.get("/monthly-trend")
def monthly_trend(months: int = 6, db: Session = Depends(get_db)):
    """Monthly spending totals, most recent months first."""
    # Uses strftime("%Y-%m") to group by month
    # Returns: [{month: "2025-01", total: 4523.12, count: 142}]
```

### Cash Flow

The most complex analytics endpoint. Returns biweekly income vs. expense data with cumulative running totals and a full category breakdown:

```python
@router.get("/cash-flow")
def cash_flow(year: int = None, db: Session = Depends(get_db)):
    """Biweekly cash flow with income/expense breakdown and category detail."""
    # Builds 2-week period buckets for the year
    # Groups transactions by period: income (amount < 0) vs expenses (amount > 0)
    # Builds parent → children hierarchy with per-period totals
    # Returns: {
    #   summary: {total_income, total_expenses, net},
    #   weeks: [{week_start, week_end, income, expenses, net, cumulative}],
    #   categories: [{name, color, total, weekly_totals, children: [...]}],
    #   excluded_categories: [{name, total, count}]
    # }
```

The excluded categories list is included in the response so the frontend can show the user what's being filtered out — transparency about why their numbers might not match the raw transaction list.

### Recurring Monitor

Shows a year-long grid of recurring expenses (subscriptions, rent, utilities) by month:

```python
@router.get("/recurring-monitor")
def recurring_monitor(year: int = None, db: Session = Depends(get_db)):
    """Monthly grid of recurring subcategories for the year."""
    # Only includes categories where is_recurring = True
    # Returns one row per category with 12-element monthly array
    # Returns: {
    #   year, active_months,
    #   rows: [{category_id, display_name, parent_name, monthly: [null, 45.00, 45.00, ...]}],
    #   totals: [monthly sum, ...]
    # }
```

The `active_months` field tells the frontend which months have any data, so it can visually distinguish "no subscription that month" from "no data imported yet."

### Available Years

Returns which years have transaction data, used by the year selector in the UI:

```python
@router.get("/years")
def get_available_years(db: Session = Depends(get_db)):
    """Years with data and their pending counts."""
    # Returns: [{year: 2024, total: 1234, pending: 56}]
```

---

## 4.7 Maintenance Endpoints

The transactions router includes several maintenance endpoints for data cleanup:

**`POST /deduplicate`** — Finds and removes duplicate transactions (same account + date + amount + description). Keeps the one with the best status (confirmed > pending_save > auto_confirmed > pending_review). Has a `dry_run` mode that previews changes without applying them.

**`POST /fix-archive-signs`** — Fixes sign convention for archive-imported bank transactions. Some bank exports use positive=deposit while the app uses positive=expense. This flips the signs on affected transactions.

**`POST /fix-archive-descriptions`** — Fixes merchant names that were incorrectly set to category labels instead of actual transaction descriptions during archive import.

**`POST /clear-predictions`** — Resets all AI predictions on pending transactions, useful for re-running categorization from scratch after updating merchant mappings or amount rules.

These endpoints all support `dry_run=true` (the default), which shows what would change without actually changing anything. This is important for data integrity — you can preview the impact before committing.

---

## What's Next

With the backend fully operational — syncing, categorizing, and storing transactions — Part 5 builds the entire React frontend: the layout system, routing, all the pages (Spending, Budgets, Accounts, Review Queue, Cash Flow, Recurring Monitor, and more), and the CSS styling.

→ [Part 5: Frontend & React UI](05-frontend-react.md)
