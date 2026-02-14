"""
Discover credit card CSV parser.

Expected format (with headers):
    Trans. Date, Post Date, Description, Amount, Category

Notes:
- Amounts are positive for purchases, negative for credits/payments
- Has its own "Category" column (ignored — we use our own taxonomy)
- Date format: MM/DD/YYYY
"""

import csv
import io
from datetime import datetime


def parse_discover_csv(text: str) -> list[dict]:
    """Parse Discover credit card CSV into standardized rows."""
    reader = csv.DictReader(io.StringIO(text))
    rows = []

    for row in reader:
        try:
            # Handle both "Trans. Date" and "Trans Date" variants
            date_str = row.get("Trans. Date") or row.get("Trans Date", "")
            if not date_str.strip():
                continue

            trans_date = datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
            description = row.get("Description", "").strip()
            amount_str = row.get("Amount", "0").strip()

            # Discover: positive = purchase/expense, negative = credit/payment
            amount = float(amount_str)

            # Clean the merchant name (remove extra whitespace, trailing codes)
            merchant_name = _clean_merchant(description)

            rows.append({
                "date": trans_date,
                "description": description,
                "merchant_name": merchant_name,
                "amount": amount,
            })
        except (ValueError, KeyError) as e:
            continue  # Skip malformed rows

    return rows


def _clean_merchant(description: str) -> str:
    """Extract a clean merchant name from Discover descriptions."""
    # Remove common suffixes like city/state codes
    merchant = description.strip()

    # Remove trailing location info (e.g., "SAFEWAY #1547 BURLINGAME CA")
    # Keep the core merchant name
    parts = merchant.split()
    if len(parts) >= 3:
        # Check if last part looks like a state code
        if len(parts[-1]) == 2 and parts[-1].isalpha():
            merchant = " ".join(parts[:-1])

    return merchant
