"""
Fix Care Credit transactions where the sign is wrong after the blanket flip.

The original archive had MIXED sign conventions — some transactions used the
bank's perspective, some used the app's convention. The blanket flip in
fix_care_credit.py fixed some but broke others.

This script enforces the correct sign convention based on category type:
  - Expense categories → amount must be positive
  - Income/credit categories → amount must be negative
  - Excluded categories (cc_payment, payment, transfer) → payments should be negative
  - Also fixes miscategorized transactions (e.g. "don" → dental)

Usage: uv run python -m backend.scripts.fix_care_credit_signs
"""

from backend.database import SessionLocal
from backend.models import Transaction, Account, Category

db = SessionLocal()

# ── Find Care Credit account ──
acct = db.query(Account).filter(Account.name.ilike("%care%credit%")).first()
if not acct:
    print("No Care Credit account found!")
    db.close()
    exit(1)

print(f"Account: {acct.name} (id={acct.id})\n")

# ── Build category lookup ──
all_cats = db.query(Category).all()
cat_by_short = {c.short_desc: c for c in all_cats}
cat_by_id = {c.id: c for c in all_cats}

# Categories where positive = expense (correct sign is positive)
EXPENSE_CATEGORIES = {
    "vision", "dental", "surgery", "security", "medical",
    "clothing", "purchases", "groceries", "fast_food", "restaurant",
    "music_festival", "museum", "travel_food", "travel_transport",
    "public_transit", "misc_other", "gambling", "care_credit",
    "don",  # miscategorized but still expense-type
}

# Categories where negative = income/credit (correct sign is negative)
INCOME_CATEGORIES = {
    "refund", "cashback_bonus", "credits",
}

# Payment/transfer categories — payments TO a credit card should be negative
# (money flowing in to reduce the balance)
PAYMENT_CATEGORIES = {
    "credit_card_payment", "payment", "transfer",
}

# ── Step 1: Fix miscategorizations ──
print("=== Step 1: Fix miscategorizations ===\n")

txns = db.query(Transaction).filter(Transaction.account_id == acct.id).all()

dental_cat = cat_by_short.get("dental")
recat_count = 0

for t in txns:
    desc_upper = t.description.upper()
    cat = cat_by_id.get(t.category_id)
    cat_name = cat.short_desc if cat else "uncategorized"

    # "State of the Art Dental" miscategorized as "don" → dental
    if "STATE OF THE ART DENTAL" in desc_upper and cat_name == "don" and dental_cat:
        print(f"  {t.date} {t.amount:>10.2f}  don -> dental  {t.description[:55]}")
        t.category_id = dental_cat.id
        recat_count += 1

print(f"\n  Recategorized {recat_count} transactions\n")

# ── Step 2: Fix signs based on category type ──
print("=== Step 2: Fix signs ===\n")

# Refresh txns after recategorization
txns = db.query(Transaction).filter(Transaction.account_id == acct.id).all()

sign_fixes = 0
for t in txns:
    cat = cat_by_id.get(t.category_id)
    cat_name = cat.short_desc if cat else "uncategorized"

    # Get the parent category too
    parent = cat_by_id.get(cat.parent_id) if cat and cat.parent_id else None
    parent_name = parent.short_desc if parent else None

    old_amount = t.amount

    if cat_name in EXPENSE_CATEGORIES or parent_name in EXPENSE_CATEGORIES:
        # Expenses should be positive
        if t.amount < 0:
            t.amount = abs(t.amount)
            print(f"  FLIP {t.date} {old_amount:>10.2f} -> {t.amount:>10.2f}  {cat_name:20s}  {t.description[:45]}")
            sign_fixes += 1

    elif cat_name in INCOME_CATEGORIES or parent_name in INCOME_CATEGORIES:
        # Income/credits should be negative
        if t.amount > 0:
            t.amount = -abs(t.amount)
            print(f"  FLIP {t.date} {old_amount:>10.2f} -> {t.amount:>10.2f}  {cat_name:20s}  {t.description[:45]}")
            sign_fixes += 1

    elif cat_name in PAYMENT_CATEGORIES or parent_name in PAYMENT_CATEGORIES:
        # Payments to credit card reduce balance — should be negative
        # EXCEPT "ADJUSTMENT-PAYMENTS" which reverse a payment (should be positive)
        desc_upper = t.description.upper()
        if "ADJUSTMENT" in desc_upper:
            if t.amount < 0:
                t.amount = abs(t.amount)
                print(f"  FLIP {t.date} {old_amount:>10.2f} -> {t.amount:>10.2f}  {cat_name:20s}  {t.description[:45]}")
                sign_fixes += 1
        else:
            if t.amount > 0:
                t.amount = -abs(t.amount)
                print(f"  FLIP {t.date} {old_amount:>10.2f} -> {t.amount:>10.2f}  {cat_name:20s}  {t.description[:45]}")
                sign_fixes += 1

    elif cat_name == "uncategorized":
        # Can't determine sign without category — skip
        pass

print(f"\n  Fixed {sign_fixes} transaction signs\n")

# ── Commit ──
db.commit()
db.close()

print("Done. Run inspect to verify:")
print('  uv run python -m backend.scripts.inspect_account "care credit"')
