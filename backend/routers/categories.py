"""
Category management endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Category

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
