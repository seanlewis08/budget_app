"""
Recategorize Discover "INTERNET PAYMENT - THANK YOU" transactions
from 'internet' (utilities) to 'credit_card_payment'.

These are credit card payments TO Discover, not internet charges.
They were auto-categorized as 'internet' due to the word "INTERNET"
in the description.

Usage: uv run python -m backend.scripts.fix_discover_payments
"""

from backend.database import SessionLocal
from backend.models import Transaction, Account, Category

db = SessionLocal()

# Find the credit_card_payment category
cc_cat = db.query(Category).filter(Category.short_desc == "credit_card_payment").first()
if not cc_cat:
    print("ERROR: credit_card_payment category not found!")
    db.close()
    exit(1)

# Find all "INTERNET PAYMENT - THANK YOU" transactions not already categorized correctly
updated = db.query(Transaction).filter(
    Transaction.description.ilike("%INTERNET PAYMENT%THANK YOU%"),
    Transaction.category_id != cc_cat.id,
).all()

print(f"Found {len(updated)} Discover payment transactions to recategorize:\n")

for t in updated:
    old_cat = db.get(Category, t.category_id) if t.category_id else None
    old_name = old_cat.short_desc if old_cat else "uncategorized"
    print(f"  {t.date}  {t.amount:>10.2f}  {old_name:>20s} -> credit_card_payment  {t.description[:50]}")
    t.category_id = cc_cat.id

db.commit()
db.close()

print(f"\nRecategorized {len(updated)} transactions.")
print("These will now be excluded from Cash Flow income/expense totals.")
