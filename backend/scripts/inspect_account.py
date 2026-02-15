"""
Inspect all transactions for a given account.
Usage: uv run python -m backend.scripts.inspect_account <account_name_pattern>

Example: uv run python -m backend.scripts.inspect_account "care credit"
"""
import sys
from backend.database import SessionLocal
from backend.models import Transaction, Account, Category

def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python -m backend.scripts.inspect_account <account_name_pattern>")
        print('Example: uv run python -m backend.scripts.inspect_account "care credit"')
        sys.exit(1)

    pattern = sys.argv[1]
    db = SessionLocal()

    acct = db.query(Account).filter(Account.name.ilike(f"%{pattern}%")).first()
    if not acct:
        print(f"No account found matching '{pattern}'")
        db.close()
        sys.exit(1)

    print(f"Account: {acct.name} (id={acct.id})")
    print()

    txns = (
        db.query(Transaction, Category)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .filter(Transaction.account_id == acct.id)
        .order_by(Transaction.date.desc())
        .all()
    )

    print(f"Total transactions: {len(txns)}")
    pos = [t for t, c in txns if t.amount > 0]
    neg = [t for t, c in txns if t.amount < 0]
    print(f"Positive (expenses):  {len(pos):>4d}   ${sum(t.amount for t in pos):>12,.2f}")
    print(f"Negative (credits):   {len(neg):>4d}   ${sum(t.amount for t in neg):>12,.2f}")
    print(f"Net:                  {len(txns):>4d}   ${sum(t.amount for t, c in txns):>12,.2f}")
    print()

    # Group by category
    cat_totals = {}
    for t, c in txns:
        key = c.short_desc if c else "uncategorized"
        if key not in cat_totals:
            parent = db.get(Category, c.parent_id) if c and c.parent_id else None
            cat_totals[key] = {
                "parent": parent.short_desc if parent else None,
                "total": 0.0,
                "count": 0,
            }
        cat_totals[key]["total"] += t.amount
        cat_totals[key]["count"] += 1

    print("--- By Category ---")
    for key, v in sorted(cat_totals.items(), key=lambda x: -abs(x[1]["total"])):
        parent_str = f"[{v['parent']}]" if v["parent"] else ""
        print(f"  {key:25s} {parent_str:25s}  {v['count']:>4d} txns   ${v['total']:>12,.2f}")
    print()

    print("--- All Transactions ---")
    print(f"{'Date':12s} {'Amount':>10s}  {'Category':25s} {'Parent':20s}  Description")
    print("-" * 120)
    for t, c in txns:
        cat = c.short_desc if c else "?"
        parent = ""
        if c and c.parent_id:
            p = db.get(Category, c.parent_id)
            parent = p.short_desc if p else ""
        print(f"{str(t.date):12s} {t.amount:>10.2f}  {cat:25s} {parent:20s}  {t.description[:50]}")

    db.close()


if __name__ == "__main__":
    main()
