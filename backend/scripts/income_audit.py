"""
Audit 2025 income: Break down ALL negative (income) transactions to explain
why Cash Flow shows $143k in inflows vs $94k in the Income category.

Usage: uv run python -m backend.scripts.income_audit
"""

from datetime import date
from backend.database import SessionLocal
from backend.models import Transaction, Account, Category

db = SessionLocal()

# Get all confirmed/auto_confirmed transactions for 2025 with negative amounts
# (Same filters as Cash Flow page)
EXCLUDED_CATEGORIES = {"transfer", "credit_card_payment", "payment", "discover"}

excluded_cat_ids = set(
    r[0] for r in db.query(Category.id).filter(Category.short_desc.in_(EXCLUDED_CATEGORIES)).all()
)

txns = (
    db.query(Transaction)
    .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
    .filter(Transaction.date >= date(2025, 1, 1))
    .filter(Transaction.date <= date(2025, 12, 31))
    .filter(~Transaction.category_id.in_(excluded_cat_ids))
    .all()
)

# Separate into income (negative) and expense (positive)
income_txns = [t for t in txns if t.amount < 0]
expense_txns = [t for t in txns if t.amount > 0]

total_income = sum(abs(t.amount) for t in income_txns)
total_expenses = sum(t.amount for t in expense_txns)

print(f"=== 2025 Cash Flow Summary ===")
print(f"Total inflows (negative amounts):  ${total_income:>12,.2f}  ({len(income_txns)} transactions)")
print(f"Total outflows (positive amounts): ${total_expenses:>12,.2f}  ({len(expense_txns)} transactions)")
print(f"Net:                               ${total_income - total_expenses:>+12,.2f}")
print()

# ── Group income transactions by PARENT category ──
print(f"=== Income Breakdown by Parent Category ===\n")

parent_groups = {}
for t in income_txns:
    cat = db.get(Category, t.category_id) if t.category_id else None
    if cat and cat.parent_id:
        parent = db.get(Category, cat.parent_id)
        parent_name = parent.display_name if parent else "Unknown"
        parent_short = parent.short_desc if parent else "unknown"
    elif cat:
        parent_name = cat.display_name
        parent_short = cat.short_desc
    else:
        parent_name = "Uncategorized"
        parent_short = "uncategorized"

    child_name = cat.short_desc if cat else "uncategorized"

    if parent_short not in parent_groups:
        parent_groups[parent_short] = {
            "name": parent_name,
            "total": 0.0,
            "count": 0,
            "children": {},
        }
    parent_groups[parent_short]["total"] += abs(t.amount)
    parent_groups[parent_short]["count"] += 1

    if child_name not in parent_groups[parent_short]["children"]:
        parent_groups[parent_short]["children"][child_name] = {"total": 0.0, "count": 0}
    parent_groups[parent_short]["children"][child_name]["total"] += abs(t.amount)
    parent_groups[parent_short]["children"][child_name]["count"] += 1

# Sort by total descending
for parent_short, data in sorted(parent_groups.items(), key=lambda x: -x[1]["total"]):
    print(f"  {data['name']:30s}  ${data['total']:>12,.2f}  ({data['count']} txns)")
    for child, cdata in sorted(data["children"].items(), key=lambda x: -x[1]["total"]):
        print(f"    └─ {child:28s}  ${cdata['total']:>12,.2f}  ({cdata['count']} txns)")
    print()

# ── Show NON-income negative transactions (the gap) ──
print(f"{'='*70}")
print(f"=== Non-Income Negative Transactions (THE GAP) ===\n")

income_parent = db.query(Category).filter(
    Category.short_desc == "income",
    Category.parent_id.is_(None),
).first()

income_child_ids = set()
if income_parent:
    income_children = db.query(Category.id).filter(Category.parent_id == income_parent.id).all()
    income_child_ids = {r[0] for r in income_children}
    income_child_ids.add(income_parent.id)

non_income_txns = [t for t in income_txns if t.category_id not in income_child_ids]
actual_income_txns = [t for t in income_txns if t.category_id in income_child_ids]

actual_income_total = sum(abs(t.amount) for t in actual_income_txns)
non_income_total = sum(abs(t.amount) for t in non_income_txns)

print(f"Actual Income category total:      ${actual_income_total:>12,.2f}  ({len(actual_income_txns)} txns)")
print(f"Non-Income negative txns total:    ${non_income_total:>12,.2f}  ({len(non_income_txns)} txns)")
print(f"Sum (should match Cash Flow in):   ${actual_income_total + non_income_total:>12,.2f}")
print()

# Group non-income by account
print(f"--- Non-Income Negatives by Account ---\n")
acct_groups = {}
for t in non_income_txns:
    acct = db.get(Account, t.account_id) if t.account_id else None
    acct_name = acct.name if acct else "Unknown"
    if acct_name not in acct_groups:
        acct_groups[acct_name] = {"total": 0.0, "count": 0, "txns": []}
    acct_groups[acct_name]["total"] += abs(t.amount)
    acct_groups[acct_name]["count"] += 1
    acct_groups[acct_name]["txns"].append(t)

for acct_name, data in sorted(acct_groups.items(), key=lambda x: -x[1]["total"]):
    print(f"  {acct_name:30s}  ${data['total']:>12,.2f}  ({data['count']} txns)")

print()

# Show ALL non-income negative transactions sorted by amount
print(f"--- All Non-Income Negative Transactions (sorted by amount) ---\n")
print(f"{'Date':12s} {'Amount':>10s}  {'Account':20s} {'Category':20s} {'Parent':20s}  Description")
print("-" * 130)

for t in sorted(non_income_txns, key=lambda x: x.amount):
    cat = db.get(Category, t.category_id) if t.category_id else None
    cat_name = cat.short_desc if cat else "?"
    parent = db.get(Category, cat.parent_id) if cat and cat.parent_id else None
    parent_name = parent.short_desc if parent else ""
    acct = db.get(Account, t.account_id) if t.account_id else None
    acct_name = acct.name if acct else "?"
    print(f"{str(t.date):12s} {t.amount:>10.2f}  {acct_name:20s} {cat_name:20s} {parent_name:20s}  {t.description[:40]}")

db.close()
print(f"\nDone.")
