"""Recategorize misclassified transfer and credit card payment transactions."""

from backend.database import SessionLocal
from backend.models import Transaction, Category

db = SessionLocal()

# 1. Recategorize 'From Savings' and 'From Checking' as Transfer
transfer_cat = db.query(Category).filter(Category.short_desc == "transfer").first()
print(f"Transfer category ID: {transfer_cat.id}")

updated = db.query(Transaction).filter(
    Transaction.description.ilike("%From Savings%"),
    Transaction.category_id != transfer_cat.id,
).update({Transaction.category_id: transfer_cat.id}, synchronize_session="fetch")
print(f"Recategorized {updated} 'From Savings' txns as Transfer")

updated2 = db.query(Transaction).filter(
    Transaction.description.ilike("%From Checking%"),
    Transaction.category_id != transfer_cat.id,
).update({Transaction.category_id: transfer_cat.id}, synchronize_session="fetch")
print(f"Recategorized {updated2} 'From Checking' txns as Transfer")

# 2. Recategorize Discover payment receipts as Credit Card Payment
cc_cat = db.query(Category).filter(Category.short_desc == "credit_card_payment").first()
updated3 = db.query(Transaction).filter(
    Transaction.description.ilike("%INTERNET PAYMENT%THANK YOU%"),
).update({Transaction.category_id: cc_cat.id}, synchronize_session="fetch")
print(f"Recategorized {updated3} Discover payment receipts as Credit Card Payment")

db.commit()
db.close()
print("Done.")
