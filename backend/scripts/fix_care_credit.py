"""
Fix Care Credit transactions from archive import:
  1. Flip all amounts (archive used bank's perspective: charges negative, payments positive)
  2. Recategorize "Payment - Thank You" variants as credit_card_payment
  3. Recategorize "ADJUSTMENT-PAYMENTS" as credit_card_payment

Usage: uv run python -m backend.scripts.fix_care_credit
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

print(f"Account: {acct.name} (id={acct.id})")

# ── Step 1: Flip all amounts ──
txns = db.query(Transaction).filter(Transaction.account_id == acct.id).all()
print(f"\nFlipping {len(txns)} transaction amounts...")

for t in txns:
    old = t.amount
    t.amount = -old

print(f"  Flipped {len(txns)} amounts")

# ── Step 2: Recategorize "Payment - Thank You" variants as credit_card_payment ──
cc_cat = db.query(Category).filter(Category.short_desc == "credit_card_payment").first()
if not cc_cat:
    print("WARNING: credit_card_payment category not found, skipping recategorization")
else:
    # Match all payment-thank-you patterns regardless of current category
    payment_count = 0
    for t in txns:
        desc = t.description.upper()
        if ("PAYMENT" in desc and "THANK YOU" in desc) or "ADJUSTMENT-PAYMENT" in desc:
            if t.category_id != cc_cat.id:
                old_cat = db.get(Category, t.category_id) if t.category_id else None
                old_name = old_cat.short_desc if old_cat else "uncategorized"
                print(f"  {t.date} {t.amount:>10.2f} {old_name:>25s} -> credit_card_payment  {t.description[:50]}")
                t.category_id = cc_cat.id
                payment_count += 1
    print(f"\n  Recategorized {payment_count} payment transactions as credit_card_payment")

# ── Commit ──
db.commit()
db.close()

print("\nDone. Run inspect_account to verify:")
print('  uv run python -m backend.scripts.inspect_account "care credit"')
