"""
SoFi Checking & Savings CSV parser.

Expected format (with headers):
    Date, Description, Type, Amount, Current balance, Status

Notes:
- Type column: "Debit Card", "Direct Payment", "Deposit", "Withdrawal", "Roundup"
- Amounts: positive = deposit/credit, negative = debit/expense
- We flip the sign so positive = expense (consistent with our schema)
- Date format: YYYY-MM-DD or MM/DD/YYYY (user may have edited)
"""

import csv
import io
from datetime import datetime


def parse_sofi_csv(text: str) -> list[dict]:
    """Parse SoFi checking or savings CSV into standardized rows."""
    reader = csv.DictReader(io.StringIO(text))
    rows = []

    for row in reader:
        try:
            date_str = row.get("Date", "").strip()
            if not date_str:
                continue

            # Handle multiple date formats
            trans_date = _parse_date(date_str)
            if not trans_date:
                continue

            description = row.get("Description", "").strip()
            amount_str = row.get("Amount", "0").strip().replace(",", "")
            txn_type = row.get("Type", "").strip()
            status = row.get("Status", "").strip()

            # Skip pending transactions if marked
            if status.lower() == "pending":
                continue

            amount = float(amount_str)

            # SoFi: negative = expense, positive = income
            # Flip sign so positive = expense in our schema
            amount = -amount

            merchant_name = _clean_merchant(description)

            rows.append({
                "date": trans_date,
                "description": description,
                "merchant_name": merchant_name,
                "amount": amount,
                "type": txn_type,
            })
        except (ValueError, KeyError) as e:
            continue

    return rows


def _parse_date(date_str: str):
    """Try multiple date formats."""
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _clean_merchant(description: str) -> str:
    """Extract a clean merchant name from SoFi descriptions."""
    merchant = description.strip()

    # SoFi sometimes prepends transaction type
    prefixes = ["DEBIT CARD PURCHASE - ", "DIRECT PAYMENT - ", "ACH - "]
    for prefix in prefixes:
        if merchant.upper().startswith(prefix):
            merchant = merchant[len(prefix):]

    return merchant.strip()
