"""
Transaction CRUD and review endpoints.

Includes staging workflow:
  pending_review → pending_save → confirmed
"""

import logging
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, extract
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Transaction, Category, MerchantMapping, Account

logger = logging.getLogger(__name__)

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
    predicted_category_short_desc: Optional[str] = None
    predicted_parent_category_name: Optional[str] = None
    status: str
    source: str
    is_pending: bool
    categorization_tier: Optional[str] = None
    prediction_confidence: Optional[float] = None
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

def _query_transactions(
    db: Session,
    status: Optional[str] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    parent_category_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    search: Optional[str] = None,
    source: Optional[str] = None,
    exclude_transfers: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[TransactionOut]:
    """Core transaction query logic (used by both route handlers)."""
    query = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category).joinedload(Category.parent),
            joinedload(Transaction.predicted_category).joinedload(Category.parent),
        )
    )

    if status:
        query = query.filter(Transaction.status == status)
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if parent_category_id:
        # Filter by parent category — match any child category under this parent
        child_ids = [
            c.id for c in db.query(Category.id).filter(
                Category.parent_id == parent_category_id
            ).all()
        ]
        # Also include the parent itself (in case transactions are directly assigned)
        child_ids.append(parent_category_id)
        query = query.filter(Transaction.category_id.in_(child_ids))
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if source:
        query = query.filter(Transaction.source == source)
    if search:
        query = query.filter(Transaction.description.ilike(f"%{search}%"))
    if exclude_transfers:
        query = _exclude_transfers(query, db)

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
        pred_parent = pred_cat.parent if pred_cat and pred_cat.parent_id else None

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
            predicted_category_short_desc=pred_cat.short_desc if pred_cat else None,
            predicted_parent_category_name=pred_parent.display_name if pred_parent else (pred_cat.display_name if pred_cat and not pred_cat.parent_id else None),
            status=txn.status,
            source=txn.source,
            is_pending=txn.is_pending,
            categorization_tier=txn.categorization_tier,
            prediction_confidence=txn.prediction_confidence,
            created_at=txn.created_at,
        ))

    return results


@router.get("/", response_model=list[TransactionOut])
def list_transactions(
    status: Optional[str] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    parent_category_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    search: Optional[str] = None,
    source: Optional[str] = None,
    exclude_transfers: bool = False,
    limit: int = Query(default=100, le=50000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List transactions with optional filters."""
    return _query_transactions(
        db=db, status=status, account_id=account_id, category_id=category_id,
        parent_category_id=parent_category_id,
        start_date=start_date, end_date=end_date, search=search,
        source=source, exclude_transfers=exclude_transfers,
        limit=limit, offset=offset,
    )


@router.get("/pending", response_model=list[TransactionOut])
def list_pending(
    year: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get all transactions awaiting review, optionally filtered by year."""
    start = date(year, 1, 1) if year else None
    end = date(year, 12, 31) if year else None
    return _query_transactions(
        db=db, status="pending_review", start_date=start, end_date=end,
        limit=10000,
    )


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


## Categories excluded from spending analytics (spending-by-category, monthly-trend, cash-flow).
## Only credit card payments and transfers — these cause double-counting.
## Real financial events (interest, fees, credits, cashback) are NOT excluded.
EXCLUDED_CATEGORIES = {
    "transfer", "credit_card_payment", "payment",
    "discover", "roundups",
}


def _exclude_transfers(query, db: Session):
    """Exclude transfer/payment categories AND their children from a spending query."""
    # Get directly excluded category ids
    excluded_parents = (
        db.query(Category.id)
        .filter(Category.short_desc.in_(EXCLUDED_CATEGORIES))
        .all()
    )
    excluded_ids = {row[0] for row in excluded_parents}

    # Also exclude any child categories whose parent is in the excluded set
    child_ids = (
        db.query(Category.id)
        .filter(Category.parent_id.in_(excluded_ids))
        .all()
    )
    excluded_ids.update(row[0] for row in child_ids)

    return query.filter(
        ~Transaction.category_id.in_(excluded_ids),
    )


@router.get("/spending-by-category")
def spending_by_category(
    month: Optional[str] = None,  # "2025-01"
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Get spending totals grouped by subcategory, excluding transfers/payments."""
    from sqlalchemy.orm import aliased

    ParentCat = aliased(Category)

    query = (
        db.query(
            Category.id,
            Category.short_desc,
            Category.display_name,
            Category.color,
            Category.parent_id,
            ParentCat.display_name.label("parent_display_name"),
            ParentCat.color.label("parent_color"),
            ParentCat.short_desc.label("parent_short_desc"),
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .join(Transaction, Transaction.category_id == Category.id)
        .outerjoin(ParentCat, Category.parent_id == ParentCat.id)
        .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
        .filter(Transaction.amount > 0)  # Expenses only
    )

    # Exclude transfers/payments (internal account movements)
    query = _exclude_transfers(query, db)

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

    results = query.group_by(Category.id, Category.short_desc).all()

    return [
        {
            "id": r.id,
            "short_desc": r.short_desc,
            "display_name": r.display_name,
            "color": r.color,
            "parent_id": r.parent_id,
            "parent_display_name": r.parent_display_name,
            "parent_color": r.parent_color,
            "parent_short_desc": r.parent_short_desc,
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
    """Get monthly spending totals for trend charts, excluding transfers/payments."""
    query = (
        db.query(
            func.strftime("%Y-%m", Transaction.date).label("month"),
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
        .filter(Transaction.amount > 0)
    )

    # Exclude transfers/payments (internal account movements)
    query = _exclude_transfers(query, db)

    results = (
        query
        .group_by(func.strftime("%Y-%m", Transaction.date))
        .order_by(func.strftime("%Y-%m", Transaction.date).desc())
        .limit(months)
        .all()
    )

    return [
        {"month": r.month, "total": round(r.total, 2), "count": r.count}
        for r in reversed(results)
    ]


@router.get("/years")
def get_available_years(db: Session = Depends(get_db)):
    """Get all years that have transaction data, with counts."""
    results = (
        db.query(
            func.strftime("%Y", Transaction.date).label("year"),
            func.count(Transaction.id).label("total"),
        )
        .group_by(func.strftime("%Y", Transaction.date))
        .order_by(func.strftime("%Y", Transaction.date).desc())
        .all()
    )

    pending_counts = (
        db.query(
            func.strftime("%Y", Transaction.date).label("year"),
            func.count(Transaction.id).label("pending"),
        )
        .filter(Transaction.status == "pending_review")
        .group_by(func.strftime("%Y", Transaction.date))
        .all()
    )
    pending_map = {r.year: r.pending for r in pending_counts}

    return [
        {
            "year": int(r.year),
            "total": r.total,
            "pending": pending_map.get(r.year, 0),
        }
        for r in results
    ]


# ── Cash Flow Analysis ──


@router.get("/cash-flow")
def cash_flow(
    year: int = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Weekly cash-flow data for the given year, including:
    - summary (total income, expenses, net)
    - weekly aggregates (income, expenses, net, cumulative)
    - category breakdown with per-week totals (parent → children hierarchy)
    """
    from datetime import timedelta

    if year is None:
        year = datetime.utcnow().year

    start = date(year, 1, 1)
    end = date(year, 12, 31)

    # ── Fetch all confirmed/auto_confirmed transactions for the year ──
    # Exclude transfers/payments (internal account movements) like Spending page
    query = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.category).joinedload(Category.parent),
        )
        .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
        .filter(Transaction.date >= start)
        .filter(Transaction.date <= end)
    )
    query = _exclude_transfers(query, db)
    transactions = query.all()

    # ── Fetch excluded transactions to show what's being filtered ──
    excluded_query = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.category).joinedload(Category.parent),
        )
        .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
        .filter(Transaction.date >= start)
        .filter(Transaction.date <= end)
    )
    # Get ALL transactions minus the non-excluded ones = excluded set
    all_ids = {t.id for t in transactions}
    all_txns_query = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.category).joinedload(Category.parent),
        )
        .filter(Transaction.status.in_(["confirmed", "auto_confirmed"]))
        .filter(Transaction.date >= start)
        .filter(Transaction.date <= end)
    )
    all_txns = all_txns_query.all()
    excluded_txns = [t for t in all_txns if t.id not in all_ids]

    # Group excluded by category — use signed amounts so transfers net to ~$0
    excluded_cat_totals = {}
    for txn in excluded_txns:
        cat = txn.category
        cat_name = cat.display_name if cat else "Uncategorized"
        cat_id = cat.id if cat else 0
        if cat_id not in excluded_cat_totals:
            excluded_cat_totals[cat_id] = {"name": cat_name, "total": 0.0, "count": 0}
        excluded_cat_totals[cat_id]["total"] += txn.amount
        excluded_cat_totals[cat_id]["count"] += 1

    excluded_categories = sorted(
        [
            {"name": v["name"], "total": round(v["total"], 2), "count": v["count"]}
            for v in excluded_cat_totals.values()
        ],
        key=lambda x: -abs(x["total"]),
    )

    # ── Build 2-week (biweekly) period buckets ──
    # Determine the Monday of the first week and build a list of all 2-week periods
    first_monday = start - timedelta(days=start.weekday())  # Monday of week containing Jan 1
    today = date.today()
    last_day = min(end, today)
    last_monday = last_day - timedelta(days=last_day.weekday())

    period_starts = []
    d = first_monday
    while d <= last_monday:
        period_starts.append(d)
        d += timedelta(days=14)

    num_periods = len(period_starts)
    if num_periods == 0:
        return {"year": year, "summary": {"total_income": 0, "total_expenses": 0, "net": 0}, "weeks": [], "categories": [], "excluded_categories": excluded_categories}

    def get_period_idx(txn_date):
        """Return the 2-week bucket index for a transaction date."""
        days_from_start = (txn_date - first_monday).days
        if days_from_start < 0:
            return None
        idx = days_from_start // 14
        return idx if idx < num_periods else None

    # ── Aggregate biweekly totals ──
    period_income = [0.0] * num_periods
    period_expenses = [0.0] * num_periods

    # ── Category aggregation ──
    # parent_id → { id, name, color, is_income, total, period_totals, children: { child_id → {...} } }
    cat_map = {}

    for txn in transactions:
        pi = get_period_idx(txn.date)
        if pi is None:
            continue

        amt = txn.amount  # positive = expense, negative = income
        if amt < 0:
            period_income[pi] += abs(amt)
        else:
            period_expenses[pi] += amt

        # Category breakdown
        cat = txn.category
        if not cat:
            continue

        # Determine parent and child
        if cat.parent_id:
            parent_id = cat.parent_id
            child_id = cat.id
            child_name = cat.display_name
            # We need parent info — fetch lazily
            parent = cat.parent
            parent_name = parent.display_name if parent else "Unknown"
            parent_color = parent.color if parent else None
            parent_is_income = parent.is_income if parent else False
        else:
            parent_id = cat.id
            child_id = None
            child_name = None
            parent_name = cat.display_name
            parent_color = cat.color
            parent_is_income = cat.is_income

        if parent_id not in cat_map:
            cat_map[parent_id] = {
                "id": parent_id,
                "name": parent_name,
                "color": parent_color,
                "is_income": parent_is_income,
                "total": 0.0,
                "income_total": 0.0,
                "expense_total": 0.0,
                "period_totals": [0.0] * num_periods,
                "children_map": {},
            }

        parent_entry = cat_map[parent_id]
        parent_entry["total"] += amt  # signed: positive = expense, negative = income
        parent_entry["period_totals"][pi] += amt
        if amt < 0:
            parent_entry["income_total"] += abs(amt)
        else:
            parent_entry["expense_total"] += amt

        if child_id:
            if child_id not in parent_entry["children_map"]:
                parent_entry["children_map"][child_id] = {
                    "id": child_id,
                    "name": child_name,
                    "total": 0.0,
                    "income_total": 0.0,
                    "expense_total": 0.0,
                    "period_totals": [0.0] * num_periods,
                }
            child_entry = parent_entry["children_map"][child_id]
            child_entry["total"] += amt
            child_entry["period_totals"][pi] += amt
            if amt < 0:
                child_entry["income_total"] += abs(amt)
            else:
                child_entry["expense_total"] += amt

    # ── Build response ──
    total_income = sum(period_income)
    total_expenses = sum(period_expenses)

    cumulative = 0.0
    periods_out = []
    for i, ps in enumerate(period_starts):
        inc = round(period_income[i], 2)
        exp = round(period_expenses[i], 2)
        net = round(inc - exp, 2)
        cumulative += net
        periods_out.append({
            "week_start": ps.isoformat(),
            "week_end": (ps + timedelta(days=13)).isoformat(),
            "income": inc,
            "expenses": exp,
            "net": net,
            "cumulative": round(cumulative, 2),
        })

    # Format categories — sorted by absolute total descending, expenses first then income
    categories_out = []
    for entry in sorted(cat_map.values(), key=lambda e: (-int(not e["is_income"]), -abs(e["total"]))):
        children = sorted(entry["children_map"].values(), key=lambda c: -abs(c["total"]))
        avg = entry["total"] / num_periods if num_periods > 0 else 0
        categories_out.append({
            "id": entry["id"],
            "name": entry["name"],
            "color": entry["color"],
            "is_income": entry["is_income"],
            "total": round(entry["total"], 2),
            "income_total": round(entry["income_total"], 2),
            "expense_total": round(entry["expense_total"], 2),
            "weekly_avg": round(avg, 2),
            "weekly_totals": [round(v, 2) for v in entry["period_totals"]],
            "children": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "total": round(c["total"], 2),
                    "income_total": round(c["income_total"], 2),
                    "expense_total": round(c["expense_total"], 2),
                    "weekly_avg": round(c["total"] / num_periods, 2) if num_periods > 0 else 0,
                    "weekly_totals": [round(v, 2) for v in c["period_totals"]],
                }
                for c in children
            ],
        })

    return {
        "year": year,
        "summary": {
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net": round(total_income - total_expenses, 2),
        },
        "weeks": periods_out,
        "categories": categories_out,
        "excluded_categories": excluded_categories,
    }


# ── Staging Workflow Endpoints ──
# NOTE: Literal paths (/staged/*, /bulk-stage) MUST be defined before
#       parameterised paths (/{transaction_id}/*) so FastAPI matches them first.


@router.post("/staged/commit")
def commit_staged(db: Session = Depends(get_db)):
    """Commit all pending_save transactions to confirmed and update merchant mappings."""
    transactions = (
        db.query(Transaction)
        .filter(Transaction.status == "pending_save")
        .all()
    )

    if not transactions:
        return {"status": "ok", "committed": 0, "mappings_updated": 0}

    mappings_updated = 0
    # Track mappings we've already created/updated in this batch to avoid
    # duplicate INSERT on the same merchant_pattern (UniqueConstraint).
    seen_mappings: dict[str, MerchantMapping] = {}

    for txn in transactions:
        txn.status = "confirmed"

        # NOW update merchant mappings (learning happens at commit time)
        if txn.merchant_name and txn.category_id:
            pattern = txn.merchant_name.upper()

            # Check our in-memory cache first, then fall back to DB
            mapping = seen_mappings.get(pattern)
            if mapping is None:
                mapping = db.query(MerchantMapping).filter(
                    MerchantMapping.merchant_pattern == pattern
                ).first()

            if mapping:
                if mapping.category_id == txn.category_id:
                    mapping.confidence += 1
                else:
                    mapping.category_id = txn.category_id
                    mapping.confidence = 1
                seen_mappings[pattern] = mapping
                mappings_updated += 1
            else:
                new_mapping = MerchantMapping(
                    merchant_pattern=pattern,
                    category_id=txn.category_id,
                    confidence=1,
                )
                db.add(new_mapping)
                seen_mappings[pattern] = new_mapping
                mappings_updated += 1

    db.commit()
    return {"status": "ok", "committed": len(transactions), "mappings_updated": mappings_updated}


@router.post("/staged/revert-all")
def revert_all_staged(db: Session = Depends(get_db)):
    """Revert ALL pending_save transactions back to pending_review."""
    transactions = (
        db.query(Transaction)
        .filter(Transaction.status == "pending_save")
        .all()
    )

    for txn in transactions:
        if txn.category_id and not txn.predicted_category_id:
            txn.predicted_category_id = txn.category_id
        txn.category_id = None
        txn.status = "pending_review"

    db.commit()
    return {"status": "ok", "reverted": len(transactions)}


@router.get("/staged", response_model=list[TransactionOut])
def list_staged(
    year: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get all staged (pending_save) transactions."""
    start = date(year, 1, 1) if year else None
    end = date(year, 12, 31) if year else None
    return _query_transactions(
        db=db, status="pending_save", start_date=start, end_date=end,
        limit=5000,
    )


@router.post("/bulk-stage")
def bulk_stage(
    action: BulkReviewAction,
    db: Session = Depends(get_db),
):
    """Bulk stage: confirm predicted categories into pending_save (no merchant mapping update)."""
    transactions = db.query(Transaction).filter(
        Transaction.id.in_(action.transaction_ids)
    ).all()

    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions found")

    staged = 0
    if action.action == "confirm":
        for txn in transactions:
            if txn.predicted_category_id:
                txn.category_id = txn.predicted_category_id
                txn.status = "pending_save"
                staged += 1
    elif action.action == "change" and action.category_short_desc:
        category = db.query(Category).filter(
            Category.short_desc == action.category_short_desc
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail=f"Unknown category: {action.category_short_desc}")
        for txn in transactions:
            txn.category_id = category.id
            txn.status = "pending_save"
            staged += 1

    db.commit()
    return {"status": "ok", "staged": staged}


@router.post("/{transaction_id}/stage")
def stage_transaction(
    transaction_id: int,
    action: ReviewAction,
    db: Session = Depends(get_db),
):
    """Stage a transaction with a category (pending_save). No merchant mapping update yet."""
    txn = db.query(Transaction).get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    category = db.query(Category).filter(
        Category.short_desc == action.category_short_desc
    ).first()
    if not category:
        raise HTTPException(status_code=400, detail=f"Unknown category: {action.category_short_desc}")

    txn.category_id = category.id
    txn.status = "pending_save"

    db.commit()
    return {"status": "pending_save", "transaction_id": txn.id, "category": action.category_short_desc}


@router.post("/{transaction_id}/kick-back")
def kick_back_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
):
    """Revert a staged transaction back to pending_review."""
    txn = db.query(Transaction).get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if txn.status != "pending_save":
        raise HTTPException(status_code=400, detail="Transaction is not staged")

    # Move category_id back to predicted, clear category_id
    if txn.category_id and not txn.predicted_category_id:
        txn.predicted_category_id = txn.category_id
    txn.category_id = None
    txn.status = "pending_review"

    db.commit()
    return {"status": "pending_review", "transaction_id": txn.id}


@router.post("/clear-predictions")
def clear_predictions(db: Session = Depends(get_db)):
    """
    Clear all AI/tier predictions from pending_review transactions.
    Resets predicted_category_id, prediction_confidence, and categorization_tier to NULL.
    Useful for re-running batch categorization from scratch.
    """
    count = (
        db.query(Transaction)
        .filter(Transaction.status == "pending_review")
        .filter(
            (Transaction.predicted_category_id.isnot(None)) |
            (Transaction.categorization_tier.isnot(None))
        )
        .update({
            Transaction.predicted_category_id: None,
            Transaction.prediction_confidence: None,
            Transaction.categorization_tier: None,
        }, synchronize_session="fetch")
    )
    db.commit()
    logger.info(f"Cleared predictions for {count} transactions")
    return {"cleared": count}


@router.post("/batch-categorize")
def batch_categorize(
    limit: int = Query(default=500, le=5000),
    db: Session = Depends(get_db),
):
    """
    Run the categorization cascade on pending_review transactions without predictions.
    Auto-confirmed results (Tier 1, high-conf Tier 2) go to pending_save.
    AI/low-conf predictions set predicted_category_id, keep pending_review.
    """
    from ..services.categorize import categorize_transaction

    # Count total eligible before limiting — exclude already-attempted unmatched txns
    total_eligible = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.status == "pending_review")
        .filter(Transaction.predicted_category_id.is_(None))
        .filter(Transaction.category_id.is_(None))
        .filter(
            (Transaction.categorization_tier.is_(None))
            | (Transaction.categorization_tier != "unmatched")
        )
        .scalar()
    )

    # Find transactions needing categorization (skip previously unmatched)
    transactions = (
        db.query(Transaction)
        .filter(Transaction.status == "pending_review")
        .filter(Transaction.predicted_category_id.is_(None))
        .filter(Transaction.category_id.is_(None))
        .filter(
            (Transaction.categorization_tier.is_(None))
            | (Transaction.categorization_tier != "unmatched")
        )
        .order_by(Transaction.date.desc())
        .limit(limit)
        .all()
    )

    stats = {
        "processed": 0,
        "auto_staged": 0,
        "predicted": 0,
        "unmatched": 0,
        "total_eligible": total_eligible,
        "by_tier": {"amount_rule": 0, "merchant_map": 0, "ai": 0, "none": 0},
    }

    for txn in transactions:
        stats["processed"] += 1

        result = categorize_transaction(txn.description, txn.amount, db, use_ai=True)
        tier = result.get("tier") or "none"
        stats["by_tier"][tier] = stats["by_tier"].get(tier, 0) + 1

        if result["category_id"]:
            txn.categorization_tier = result["tier"]
            txn.prediction_confidence = result.get("confidence", 0)

            if result["status"] == "auto_confirmed":
                # High confidence — go straight to pending_save
                txn.category_id = result["category_id"]
                txn.status = "pending_save"
                stats["auto_staged"] += 1
            else:
                # AI or low-confidence — set as prediction for user review
                txn.predicted_category_id = result["category_id"]
                stats["predicted"] += 1
        else:
            # Mark as attempted so it won't be re-queried in the next batch chunk
            txn.categorization_tier = "unmatched"
            stats["unmatched"] += 1

        # Commit every 50 to avoid long locks
        if stats["processed"] % 50 == 0:
            db.commit()
            logger.info(f"Batch categorize progress: {stats['processed']}/{len(transactions)}")

    db.commit()
    logger.info(f"Batch categorize complete: {stats}")
    return stats


@router.post("/fix-archive-signs")
def fix_archive_signs(
    dry_run: bool = Query(default=True, description="Preview changes without applying"),
    db: Session = Depends(get_db),
):
    """
    Fix sign convention for archive-imported bank transactions.

    The archive importer previously stored checking/savings amounts
    without flipping signs. Bank exports use positive=deposit, negative=expense,
    but the app convention is positive=expense, negative=income.

    This endpoint flips the sign on all archive-imported transactions
    for checking and savings accounts.
    """
    # Find all archive-imported transactions on checking/savings accounts
    affected = (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Transaction.source == "archive_import")
        .filter(Account.account_type.in_(["checking", "savings"]))
        .all()
    )

    flipped = 0
    sample = []

    for txn in affected:
        old_amount = txn.amount
        new_amount = -txn.amount

        if len(sample) < 10:
            sample.append({
                "id": txn.id,
                "date": str(txn.date),
                "description": txn.description[:60],
                "old_amount": old_amount,
                "new_amount": new_amount,
            })

        if not dry_run:
            txn.amount = new_amount

        flipped += 1

    if not dry_run:
        db.commit()
        logger.info(f"Fixed archive signs: {flipped} transactions flipped")

    return {
        "dry_run": dry_run,
        "transactions_affected": flipped,
        "sample": sample,
        "message": (
            f"Would flip {flipped} transactions" if dry_run
            else f"Flipped {flipped} transactions successfully"
        ),
    }


@router.post("/fix-archive-descriptions")
def fix_archive_descriptions(
    dry_run: bool = Query(default=True, description="Preview changes without applying"),
    db: Session = Depends(get_db),
):
    """
    Fix merchant_name for archive-imported transactions.

    The archive importer previously set merchant_name to Short_Desc
    (a category label like 'transfer', 'income') instead of the actual
    transaction description. The frontend displays merchant_name preferentially,
    so descriptions looked wrong.

    This endpoint copies description → merchant_name for all archive-imported
    transactions where merchant_name differs from description.
    """
    affected = (
        db.query(Transaction)
        .filter(Transaction.source == "archive_import")
        .filter(Transaction.merchant_name != Transaction.description)
        .all()
    )

    fixed = 0
    sample = []

    for txn in affected:
        old_merchant = txn.merchant_name
        new_merchant = txn.description[:200] if txn.description else old_merchant

        if old_merchant == new_merchant:
            continue

        if len(sample) < 15:
            sample.append({
                "id": txn.id,
                "date": str(txn.date),
                "old_merchant_name": old_merchant[:60] if old_merchant else None,
                "new_merchant_name": new_merchant[:60] if new_merchant else None,
            })

        if not dry_run:
            txn.merchant_name = new_merchant

        fixed += 1

    if not dry_run:
        db.commit()
        logger.info(f"Fixed archive descriptions: {fixed} transactions updated")

    return {
        "dry_run": dry_run,
        "transactions_affected": fixed,
        "sample": sample,
        "message": (
            f"Would fix {fixed} descriptions" if dry_run
            else f"Fixed {fixed} descriptions successfully"
        ),
    }
