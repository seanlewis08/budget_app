"""
Rollback the Care Credit fixes: flip all amounts back to original
and restore original categories for "Payment - Thank You" transactions.

This undoes both fix_care_credit.py steps:
  1. Re-flips all amounts (undo the blanket flip)
  2. Does NOT touch categories — user will handle those separately

Usage: uv run python -m backend.scripts.rollback_care_credit
"""

from backend.database import SessionLocal
from backend.models import Transaction, Account

db = SessionLocal()

acct = db.query(Account).filter(Account.name.ilike("%care%credit%")).first()
if not acct:
    print("No Care Credit account found!")
    db.close()
    exit(1)

print(f"Account: {acct.name} (id={acct.id})")

txns = db.query(Transaction).filter(Transaction.account_id == acct.id).all()
print(f"Flipping {len(txns)} transaction amounts back to original...")

for t in txns:
    t.amount = -t.amount

db.commit()
db.close()

print("Done. All Care Credit amounts restored to original values.")
print('Verify with: uv run python -m backend.scripts.inspect_account "care credit"')
