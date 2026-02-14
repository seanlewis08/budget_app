"""
CSV import endpoints.
Handles file uploads for each bank's CSV format and processes them
through the categorization engine.
"""

import io
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Transaction, Account
from ..services.csv_parsers.discover import parse_discover_csv
from ..services.csv_parsers.sofi import parse_sofi_csv
from ..services.csv_parsers.wellsfargo import parse_wellsfargo_csv
from ..services.categorize import categorize_transaction

router = APIRouter()

PARSERS = {
    "discover": parse_discover_csv,
    "sofi_checking": parse_sofi_csv,
    "sofi_savings": parse_sofi_csv,
    "wellsfargo": parse_wellsfargo_csv,
}


@router.post("/csv")
async def import_csv(
    file: UploadFile = File(...),
    bank: str = Query(..., description="Bank name: discover, sofi_checking, sofi_savings, wellsfargo"),
    db: Session = Depends(get_db),
):
    """Import a CSV file from a specific bank."""
    if bank not in PARSERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bank: {bank}. Must be one of: {', '.join(PARSERS.keys())}",
        )

    # Read uploaded file
    content = await file.read()
    text = content.decode("utf-8")

    # Find the account
    institution_map = {
        "discover": "discover",
        "sofi_checking": "sofi",
        "sofi_savings": "sofi",
        "wellsfargo": "wellsfargo",
    }
    account_type_map = {
        "discover": "credit",
        "sofi_checking": "checking",
        "sofi_savings": "savings",
        "wellsfargo": "checking",
    }

    account = db.query(Account).filter(
        Account.institution == institution_map[bank],
        Account.account_type == account_type_map[bank],
    ).first()

    if not account:
        raise HTTPException(status_code=400, detail=f"Account not found for bank: {bank}")

    # Parse CSV into standardized rows
    parser = PARSERS[bank]
    try:
        rows = parser(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {str(e)}")

    # Insert transactions, skip duplicates
    imported = 0
    skipped = 0

    for row in rows:
        # Check for duplicate (same account, date, description, amount)
        existing = db.query(Transaction).filter(
            Transaction.account_id == account.id,
            Transaction.date == row["date"],
            Transaction.description == row["description"],
            Transaction.amount == row["amount"],
        ).first()

        if existing:
            skipped += 1
            continue

        # Categorize the transaction
        cat_result = categorize_transaction(
            description=row["description"],
            amount=row["amount"],
            db=db,
        )

        txn = Transaction(
            account_id=account.id,
            date=row["date"],
            description=row["description"],
            merchant_name=row.get("merchant_name"),
            amount=row["amount"],
            category_id=cat_result.get("category_id"),
            predicted_category_id=cat_result.get("category_id"),
            status=cat_result.get("status", "pending_review"),
            source="csv_import",
            categorization_tier=cat_result.get("tier"),
        )
        db.add(txn)
        imported += 1

    db.commit()

    return {
        "status": "ok",
        "file": file.filename,
        "bank": bank,
        "imported": imported,
        "skipped_duplicates": skipped,
        "total_rows": len(rows),
    }


@router.post("/csv/auto-detect")
async def import_csv_auto(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Try to auto-detect the bank format from CSV content."""
    content = await file.read()
    text = content.decode("utf-8")
    first_line = text.split("\n")[0].strip()

    # Detect format by header patterns
    if "Trans. Date" in first_line and "Post Date" in first_line:
        bank = "discover"
    elif "Current balance" in first_line and "Status" in first_line:
        # SoFi — need to infer checking vs savings from content
        if "Roundup" in text[:2000]:
            bank = "sofi_checking"
        else:
            bank = "sofi_savings"
    elif first_line and not any(c.isalpha() for c in first_line.split(",")[0]):
        # No headers, starts with a date — likely Wells Fargo
        bank = "wellsfargo"
    else:
        raise HTTPException(
            status_code=400,
            detail="Could not auto-detect bank format. Please specify the bank parameter.",
        )

    # Re-create the upload file with the content we already read
    file.file = io.BytesIO(content)
    return await import_csv(file=file, bank=bank, db=db)
