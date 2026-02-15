"""
Category management endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Category, Transaction

router = APIRouter()


class CategoryOut(BaseModel):
    id: int
    short_desc: str
    display_name: str
    parent_id: Optional[int] = None
    parent_name: Optional[str] = None
    color: Optional[str] = None
    is_income: bool
    is_recurring: bool

    class Config:
        from_attributes = True


class CategoryCreate(BaseModel):
    short_desc: str
    display_name: str
    parent_short_desc: Optional[str] = None
    color: Optional[str] = None
    is_income: bool = False
    is_recurring: bool = False


@router.get("/", response_model=list[CategoryOut])
def list_categories(
    parent_only: bool = False,
    db: Session = Depends(get_db),
):
    """List all categories, optionally only parent (high-level) categories."""
    query = db.query(Category)

    if parent_only:
        query = query.filter(Category.parent_id.is_(None))

    categories = query.order_by(Category.display_name).all()

    results = []
    for cat in categories:
        parent = db.query(Category).get(cat.parent_id) if cat.parent_id else None
        results.append(CategoryOut(
            id=cat.id,
            short_desc=cat.short_desc,
            display_name=cat.display_name,
            parent_id=cat.parent_id,
            parent_name=parent.display_name if parent else None,
            color=cat.color,
            is_income=cat.is_income,
            is_recurring=cat.is_recurring,
        ))

    return results


@router.get("/tree")
def category_tree(db: Session = Depends(get_db)):
    """Get categories as a hierarchical tree (parent → children)."""
    parents = (
        db.query(Category)
        .filter(Category.parent_id.is_(None))
        .order_by(Category.display_name)
        .all()
    )

    tree = []
    for parent in parents:
        children = (
            db.query(Category)
            .filter(Category.parent_id == parent.id)
            .order_by(Category.display_name)
            .all()
        )
        tree.append({
            "id": parent.id,
            "short_desc": parent.short_desc,
            "display_name": parent.display_name,
            "color": parent.color,
            "is_income": parent.is_income,
            "children": [
                {
                    "id": c.id,
                    "short_desc": c.short_desc,
                    "display_name": c.display_name,
                    "is_recurring": c.is_recurring,
                }
                for c in children
            ],
        })

    return tree


@router.post("/", response_model=CategoryOut)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
):
    """Create a new category."""
    existing = db.query(Category).filter(Category.short_desc == data.short_desc).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Category '{data.short_desc}' already exists")

    parent = None
    if data.parent_short_desc:
        parent = db.query(Category).filter(Category.short_desc == data.parent_short_desc).first()
        if not parent:
            raise HTTPException(status_code=400, detail=f"Parent category '{data.parent_short_desc}' not found")

    category = Category(
        short_desc=data.short_desc,
        display_name=data.display_name,
        parent_id=parent.id if parent else None,
        color=data.color,
        is_income=data.is_income,
        is_recurring=data.is_recurring,
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    return CategoryOut(
        id=category.id,
        short_desc=category.short_desc,
        display_name=category.display_name,
        parent_id=category.parent_id,
        parent_name=parent.display_name if parent else None,
        color=category.color,
        is_income=category.is_income,
        is_recurring=category.is_recurring,
    )


class CategoryUpdate(BaseModel):
    display_name: Optional[str] = None
    color: Optional[str] = None
    is_income: Optional[bool] = None
    is_recurring: Optional[bool] = None


@router.patch("/{short_desc}")
def update_category(
    short_desc: str,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
):
    """Update a category's display name, color, or flags."""
    category = db.query(Category).filter(Category.short_desc == short_desc).first()
    if not category:
        raise HTTPException(status_code=404, detail=f"Category '{short_desc}' not found")

    if data.display_name is not None:
        category.display_name = data.display_name.strip()
    if data.color is not None:
        category.color = data.color
    if data.is_income is not None:
        category.is_income = data.is_income
    if data.is_recurring is not None:
        category.is_recurring = data.is_recurring

    db.commit()
    db.refresh(category)

    parent = db.query(Category).get(category.parent_id) if category.parent_id else None
    return CategoryOut(
        id=category.id,
        short_desc=category.short_desc,
        display_name=category.display_name,
        parent_id=category.parent_id,
        parent_name=parent.display_name if parent else None,
        color=category.color,
        is_income=category.is_income,
        is_recurring=category.is_recurring,
    )


class CategoryMove(BaseModel):
    new_parent_short_desc: str


@router.patch("/{short_desc}/move")
def move_category(
    short_desc: str,
    data: CategoryMove,
    db: Session = Depends(get_db),
):
    """Move a subcategory to a different parent category."""
    category = db.query(Category).filter(Category.short_desc == short_desc).first()
    if not category:
        raise HTTPException(status_code=404, detail=f"Category '{short_desc}' not found")

    if not category.parent_id:
        raise HTTPException(status_code=400, detail="Cannot move a parent category — only subcategories can be moved")

    new_parent = db.query(Category).filter(Category.short_desc == data.new_parent_short_desc).first()
    if not new_parent:
        raise HTTPException(status_code=404, detail=f"Target parent '{data.new_parent_short_desc}' not found")

    if new_parent.parent_id is not None:
        raise HTTPException(status_code=400, detail="Target must be a parent category (not a subcategory)")

    if new_parent.id == category.parent_id:
        raise HTTPException(status_code=400, detail="Category is already under this parent")

    old_parent = db.query(Category).get(category.parent_id)
    category.parent_id = new_parent.id
    db.commit()

    return {
        "status": "moved",
        "category": category.display_name,
        "from": old_parent.display_name if old_parent else None,
        "to": new_parent.display_name,
    }


@router.delete("/{short_desc}")
def delete_category(
    short_desc: str,
    db: Session = Depends(get_db),
):
    """Delete a category by short_desc. Fails if transactions reference it."""
    category = db.query(Category).filter(Category.short_desc == short_desc).first()
    if not category:
        raise HTTPException(status_code=404, detail=f"Category '{short_desc}' not found")

    # Check if any transactions use this category
    txn_count = db.query(Transaction).filter(
        (Transaction.category_id == category.id) |
        (Transaction.predicted_category_id == category.id)
    ).count()
    if txn_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete '{category.display_name}' — {txn_count} transaction(s) use this category. Reassign them first."
        )

    # If parent, check for children
    children = db.query(Category).filter(Category.parent_id == category.id).count()
    if children > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete '{category.display_name}' — it has {children} subcategories. Delete them first."
        )

    db.delete(category)
    db.commit()
    return {"status": "deleted", "short_desc": short_desc}
