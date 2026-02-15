"""
Inspect "roundups" category transactions to check for pairing issues.

Roundups should come in opposite-sign pairs:
- When you spend $10.50, roundup charge of +0.50 (expense)
- When roundup credits back, -0.50 (income)

These should cancel out. This script identifies:
1. Unpaired roundup transactions
2. Transactions with incorrect signs
3. Summary of what's wrong

Usage: uv run python -m backend.scripts.inspect_roundups
"""

from datetime import date, timedelta
from backend.database import SessionLocal
from backend.models import Transaction, Category

def main():
    db = SessionLocal()

    # Find the "roundups" category
    roundups_cat = db.query(Category).filter(
        Category.short_desc == "roundups"
    ).first()

    if not roundups_cat:
        print("ERROR: 'roundups' category not found")
        db.close()
        return

    print(f"Category: {roundups_cat.display_name} (id={roundups_cat.id})")
    print(f"Parent Category ID: {roundups_cat.parent_id}")
    if roundups_cat.parent_id:
        parent = db.get(Category, roundups_cat.parent_id)
        print(f"Parent Category: {parent.display_name if parent else 'Unknown'}")
    print()

    # Get all roundups transactions
    txns = (
        db.query(Transaction)
        .filter(Transaction.category_id == roundups_cat.id)
        .order_by(Transaction.date.desc())
        .all()
    )

    print(f"Total roundups transactions: {len(txns)}")
    print()

    # Calculate totals by sign
    pos_txns = [t for t in txns if t.amount > 0]
    neg_txns = [t for t in txns if t.amount < 0]
    zero_txns = [t for t in txns if t.amount == 0]

    total_pos = sum(t.amount for t in pos_txns)
    total_neg = sum(t.amount for t in neg_txns)
    net = total_pos + total_neg

    print(f"Positive (roundup charges):  {len(pos_txns):>4d} txns   ${total_pos:>12,.2f}")
    print(f"Negative (roundup credits):  {len(neg_txns):>4d} txns   ${total_neg:>12,.2f}")
    print(f"Zero-amount:                 {len(zero_txns):>4d} txns")
    print(f"Net total:                                 ${net:>12,.2f}")
    print()

    # Build a map of transactions for pairing detection
    # Key: (date, abs(amount), description_pattern)
    # Value: list of transactions with that key

    def extract_pattern(desc):
        """Extract a pattern from description for matching."""
        # Normalize: strip whitespace, lowercase, and extract common parts
        return desc.strip().lower()

    roundup_map = {}
    for txn in txns:
        # Use date and absolute amount as primary key
        key = (txn.date, round(abs(txn.amount), 2))
        pattern = extract_pattern(txn.description)

        if key not in roundup_map:
            roundup_map[key] = []
        roundup_map[key].append((txn, pattern))

    # Find unpaired transactions
    unpaired = []
    for key, txn_list in roundup_map.items():
        date_val, amount = key

        # For a proper pair, we expect:
        # - One positive amount (charge)
        # - One negative amount (credit)
        # - Same or similar description

        pos_for_key = [t for t, _ in txn_list if t.amount > 0]
        neg_for_key = [t for t, _ in txn_list if t.amount < 0]

        # If we don't have both, it's unpaired
        if len(pos_for_key) == 0 or len(neg_for_key) == 0:
            unpaired.extend(txn_list)
        elif len(pos_for_key) != len(neg_for_key):
            # Mismatch in counts
            unpaired.extend(txn_list)

    if unpaired:
        print(f"=== UNPAIRED TRANSACTIONS ({len(unpaired)}) ===")
        print(f"{'Date':12s} {'Amount':>10s} {'Description':50s}")
        print("-" * 75)
        for txn, _ in sorted(unpaired, key=lambda x: x[0].date, reverse=True):
            desc = txn.description[:50]
            print(f"{str(txn.date):12s} {txn.amount:>10.2f}  {desc:50s}")
        print()
    else:
        print("All transactions appear to be properly paired!")
        print()

    # Check for sign convention issues
    # Roundups should typically be:
    # - POSITIVE when charging (roundup initiated)
    # - NEGATIVE when crediting back (refund)

    print(f"=== SIGN ANALYSIS ===")
    print()

    # Group by description to find patterns
    desc_groups = {}
    for txn in txns:
        pattern = extract_pattern(txn.description)
        if pattern not in desc_groups:
            desc_groups[pattern] = {"pos": [], "neg": [], "zero": []}
        if txn.amount > 0:
            desc_groups[pattern]["pos"].append(txn)
        elif txn.amount < 0:
            desc_groups[pattern]["neg"].append(txn)
        else:
            desc_groups[pattern]["zero"].append(txn)

    print(f"Description patterns found: {len(desc_groups)}")
    print()

    # Show patterns with sign anomalies
    print(f"--- Patterns with Only One Sign (potential issues) ---")
    print()

    has_issues = False
    for pattern in sorted(desc_groups.keys()):
        data = desc_groups[pattern]
        pos_count = len(data["pos"])
        neg_count = len(data["neg"])
        zero_count = len(data["zero"])

        # If we have transactions but only one sign (not paired), it's an issue
        if (pos_count > 0 and neg_count == 0 and zero_count == 0) or \
           (neg_count > 0 and pos_count == 0 and zero_count == 0):
            has_issues = True
            total_pos_amt = sum(t.amount for t in data["pos"])
            total_neg_amt = sum(t.amount for t in data["neg"])
            print(f"Pattern: {pattern[:60]}")
            print(f"  Positive:  {pos_count:>3d} txns   ${total_pos_amt:>10,.2f}")
            print(f"  Negative:  {neg_count:>3d} txns   ${total_neg_amt:>10,.2f}")
            print(f"  Zero:      {zero_count:>3d} txns")
            print()

    if not has_issues:
        print("No obvious sign convention issues found.")
        print()

    # Show all transactions for manual review
    print(f"=== ALL ROUNDUP TRANSACTIONS (sorted by date desc) ===")
    print(f"{'Date':12s} {'Amount':>10s} {'Account':25s}  Description")
    print("-" * 90)

    from backend.models import Account
    for txn in sorted(txns, key=lambda t: t.date, reverse=True):
        acct = db.get(Account, txn.account_id) if txn.account_id else None
        acct_name = acct.name if acct else "Unknown"
        desc = txn.description[:50]
        print(f"{str(txn.date):12s} {txn.amount:>10.2f}  {acct_name:25s}  {desc:50s}")

    db.close()
    print()
    print("Done.")


if __name__ == "__main__":
    main()
