"""
Wells Fargo checking CSV parser.

Expected format (NO HEADERS):
    Date, Amount, (empty), (empty), Description

Notes:
- No header row — 5 columns, columns 3 and 4 are always empty
- Amounts: positive = deposit, negative = debit
- We flip the sign so positive = expense (consistent with our schema)
- Date format: MM/DD/YYYY
"""

import csv
import io
from datetime import datetime


def parse_wellsfargo_csv(text: str) -> list[dict]:
    """Parse Wells Fargo CSV (no headers) into standardized rows."""
    reader = csv.reader(io.StringIO(text))
    rows = []

    for line in reader:
        try:
            # Skip empty lines
            if not line or len(line) < 5:
                continue

            # Wells Fargo format: Date, Amount, empty, empty, Description
            date_str = line[0].strip().strip('"')
            amount_str = line[1].strip().strip('"').replace(",", "")
            description = line[4].strip().strip('"')

            if not date_str or not description:
                continue

            trans_date = _parse_date(date_str)
            if not trans_date:
                continue

            amount = float(amount_str)

            # Wells Fargo: negative = expense, positive = deposit
            # Flip sign so positive = expense in our schema
            amount = -amount

            merchant_name = _clean_merchant(description)

            rows.append({
                "date": trans_date,
                "description": description,
                "merchant_name": merchant_name,
                "amount": amount,
            })
        except (ValueError, IndexError) as e:
            continue

    return rows


def _parse_date(date_str: str):
    """Try multiple date formats."""
    formats = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _clean_merchant(description: str) -> str:
    """Extract a clean merchant name from Wells Fargo descriptions."""
    merchant = description.strip()

    # Remove common WF prefixes
    prefixes = [
        "PURCHASE AUTHORIZED ON ",
        "RECURRING PURCHASE AUTHORIZED ON ",
        "ONLINE TRANSFER TO ",
        "ONLINE TRANSFER FROM ",
        "CHECK ",
        "ATM WITHDRAWAL ",
    ]
    upper = merchant.upper()
    for prefix in prefixes:
        if upper.startswith(prefix):
            merchant = merchant[len(prefix):]
            break

    # Remove trailing date patterns (e.g., "01/15 CARD 1234")
    parts = merchant.split()
    cleaned = []
    for part in parts:
        if part.startswith("CARD") or (len(part) == 5 and "/" in part):
            break
        cleaned.append(part)

    return " ".join(cleaned).strip() if cleaned else merchant.strip()
