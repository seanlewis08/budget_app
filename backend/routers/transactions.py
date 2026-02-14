"""
Transaction CRUD and review endpoints.
"""

from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, extract
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Transaction, Category, MerchantMapping, Account

router = APIRouter()


# --- Pydantic Schemas ---

class TransactionOut(BaseModel):
    id: int
    account_id: int
    account_name: Optional[str] = None
    date: date
    description: str
    merchant_name: Optional[str] = None
    amount: float
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_short_desc: Optional[str] = None
    parent_category_name: Optional[str] = None
    predicted_category_id: Optional[int] = None
    predicted_category_name: Optional[str] = None
    status: str
    source: str
    is_pending: bool
    categorization_tier: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewAction(BaseModel):
    category_short_desc: str  # The Short_Desc to assign


class BulkReviewAction(BaseModel):
    transaction_ids: list[int]
    action: str  # "confirm" or "change"
    category_short_desc: Optional[str] = None


# --- Endpoints ---

@router.get("/", response_model=list[TransactionOut])
def list_transactions(
    status: Optional[str] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List transactions with optional filters."""
    query = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
            joinedload(Transaction.predicted_category),
        )
    )

    if status:
        query = query.filter(Transaction.status == status)
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if search:
        query = query.filter(Transaction.description.ilike(f"%{search}%"))

    transactions = (
        query.order_by(Transaction.date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for txn in transactions:
        cat = txn.category
        pred_cat = txn.predicted_category
        parent_cat = cat.parent if cat and cat.parent_id else None

        results.append(TransactionOut(
            id=txn.id,
            account_id=txn.account_id,
            account_name=txn.account.name if txn.account else None,
            date=txn.date,
            description=txn.description,
            merchant_name=txn.merchant_name,
            amount=txn.amount,
            category_id=txn.category_id,
            category_name=cat.display_name if cat else None,
            category_short_desc=cat.short_desc if cat else None,
            parent_category_name=parent_cat.display_name if parent_cat else (cat.display_name if cat and not cat.parent_id else None),
            predicted_category_id=txn.predicted_category_id,
            predicted_category_name=pred_cat.display_name if pred_cat else None,
            status=txn.status,
            source=txn.source,
            is_pending=txn.is_pending,
            categorization_tier=txn.categorization_tier,
            created_at=txn.created_at,
        ))

    return results


@router.get("/pending", response_model=list[TransactionOut])
def list_pending(db: Session = Depends(get_db)):
    """Get all transactions awaiting review."""
    return list_transactions(status="pending_review", db=db)


@router.post("/{transaction_id}/review")
def review_transaction(
    transaction_id: int,
    action: ReviewAction,
    db: Session = Depends(get_db),
):
    """Confirm or change a transaction's category."""
    txn = db.query(Transaction).get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Find the category by short_desc
    category = db.query(Category).filter(
        Category.short_desc == action.category_short_desc
    ).first()
    if not category:
        raise HTTPException(status_code=400, detail=f"Unknown category: {action.category_short_desc}")

    txn.category_id = category.id
    txn.status = "confirmed"

    # Update or create merchant mapping to learn from this confirmation
    if txn.merchant_name:
        mapping = db.query(MerchantMapping).filter(
            MerchantMapping.merchant_pattern == txn.merchant_name.upper()
        ).first()

        if mapping:
            if mapping.category_id == category.id:
                mapping.confidence += 1
            else:
                # User changed the category — reset confidence
                mapping.category_id = category.id
                mapping.confidence = 1
        else:
            mapping = MerchantMapping(
                merchant_pattern=txn.merchant_name.upper(),
                category_id=category.id,
                confidence=1,
            )
            db.add(mapping)

    db.commit()
    return {"status": "confirmed", "transaction_id": txn.id, "category": action.category_short_desc}


@router.post("/bulk-review")
def bulk_review(
    action: BulkReviewAction,
    db: Session = Depends(get_db),
):
    """Bulk confirm or change categories for multiple transactions."""
    transactions = db.query(Transaction).filter(
        Transaction.id.in_(action.transaction_ids)
    ).all()

    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions found")

    if action.action == "confirm":
        # Confirm each with its predicted category
        for txn in transactions:
            if txn.predicted_category_id:
                txn.category_id = txn.predicted_category_id
                txn.status = "confirmed"
    elif action.action == "change" and action.category_short_desc:
        category = db.query(Category).filter(
            Category.short_desc == action.category_short_desc
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail=f"Unknown category: {action.category_short_desc}")
        for txn in transactions:
            txn.category_id = category.id
            txn.status = "confirmed"

    db.commit()
    return {"status": "ok", "updated": len(transactions)}


@router.get("/spending-by-category")
def spending_by_category(
    month: Optional[str] = None,  # "2025-01"
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Get spending totals grouped by parent category."""
    query = (
        db.query(
            Category.short_desc,
            Category.display_name,
            Category.color,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
        .filter(Transaction.amount > 0)  # Expenses only
    )

    if month:
        year, mo = month.split("-")
        query = query.filter(
            extract("year", Transaction.date) == int(year),
            extract("month", Transaction.date) == int(mo),
        )
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)

    results = query.group_by(Category.short_desc).all()

    return [
        {
            "short_desc": r.short_desc,
            "display_name": r.display_name,
            "color": r.color,
            "total": round(r.total, 2),
            "count": r.count,
        }
        for r in results
    ]


@router.get("/monthly-trend")
def monthly_trend(
    months: int = 6,
    db: Session = Depends(get_db),
):
    """Get monthly spending totals for trend charts."""
    results = (
        db.query(
            func.strftime("%Y-%m", Transaction.date).label("month"),
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
        .filter(Transaction.amount > 0)
        .group_by(func.strftime("%Y-%m", Transaction.date))
        .order_by(func.strftime("%Y-%m", Transaction.date).desc())
        .limit(months)
        .all()
    )

    return [
        {"month": r.month, "total": round(r.total, 2), "count": r.count}
        for r in reversed(results)
    ]
