"""Quick script to count transactions in the database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.database import SessionLocal, DB_PATH
from backend.models import Transaction, Account
from sqlalchemy import func

db = SessionLocal()

print(f"Database: {DB_PATH}")
print(f"File size: {DB_PATH.stat().st_size / (1024*1024):.1f} MB")
print()

total = db.query(func.count(Transaction.id)).scalar()
print(f"Total transactions: {total:,}")
print()

# By account
print("By account:")
rows = (
    db.query(Account.name, func.count(Transaction.id))
    .outerjoin(Transaction, Transaction.account_id == Account.id)
    .group_by(Account.id)
    .order_by(func.count(Transaction.id).desc())
    .all()
)
for name, count in rows:
    print(f"  {name}: {count:,}")

# By status
print("\nBy status:")
rows = (
    db.query(Transaction.status, func.count(Transaction.id))
    .group_by(Transaction.status)
    .all()
)
for status, count in rows:
    print(f"  {status}: {count:,}")

# By year
print("\nBy year:")
rows = (
    db.query(func.strftime('%Y', Transaction.date).label('year'), func.count(Transaction.id))
    .group_by('year')
    .order_by('year')
    .all()
)
for year, count in rows:
    print(f"  {year}: {count:,}")

db.close()
