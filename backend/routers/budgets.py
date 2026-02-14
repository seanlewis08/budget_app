"""
Budget management endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Budget, Category, Transaction

router = APIRouter()


class BudgetOut(BaseModel):
    id: int
    category_id: int
    category_name: str
    category_short_desc: str
    month: str
    budgeted: float
    spent: float
    remaining: float
    percent_used: float

    class Config:
        from_attributes = True


class BudgetCreate(BaseModel):
    category_short_desc: str
    month: str  # "2025-01"
    amount: float


@router.get("/", response_model=list[BudgetOut])
def list_budgets(
    month: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all budgets for a given month with spending progress."""
    query = db.query(Budget).join(Category)

    if month:
        query = query.filter(Budget.month == month)

    budgets = query.order_by(Category.display_name).all()
    results = []

    for budget in budgets:
        # Calculate actual spending for this category in this month
        year, mo = budget.month.split("-")
        spent = (
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.category_id == budget.category_id,
                Transaction.status.in_(["confirmed", "auto_confirmed"]),
                Transaction.amount > 0,
                extract("year", Transaction.date) == int(year),
                extract("month", Transaction.date) == int(mo),
            )
            .scalar()
        )

        spent = round(float(spent), 2)
        remaining = round(budget.amount - spent, 2)
        percent = round((spent / budget.amount * 100) if budget.amount > 0 else 0, 1)

        results.append(BudgetOut(
            id=budget.id,
            category_id=budget.category_id,
            category_name=budget.category.display_name,
            category_short_desc=budget.category.short_desc,
            month=budget.month,
            budgeted=budget.amount,
            spent=spent,
            remaining=remaining,
            percent_used=percent,
        ))

    return results


@router.post("/", response_model=dict)
def create_or_update_budget(
    data: BudgetCreate,
    db: Session = Depends(get_db),
):
    """Create or update a budget for a category+month."""
    category = db.query(Category).filter(Category.short_desc == data.category_short_desc).first()
    if not category:
        raise HTTPException(status_code=400, detail=f"Unknown category: {data.category_short_desc}")

    existing = db.query(Budget).filter(
        Budget.category_id == category.id,
        Budget.month == data.month,
    ).first()

    if existing:
        existing.amount = data.amount
        db.commit()
        return {"status": "updated", "id": existing.id}
    else:
        budget = Budget(
            category_id=category.id,
            month=data.month,
            amount=data.amount,
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)
        return {"status": "created", "id": budget.id}
