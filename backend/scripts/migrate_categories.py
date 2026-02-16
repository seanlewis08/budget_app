"""
Category Migration Script
=========================
Applies the following changes to the live database:

1. Create "Streaming Services" parent category
   - Move spotify, netflix, hulu, hbo, apple_tv, youtube_premium, disney_plus
     from Recreation_Entertainment to Streaming Services

2. Merge state_farm and progressive into car_insurance
   - Reassign all transactions from state_farm/progressive to car_insurance
   - Update merchant mappings to point to car_insurance
   - Delete state_farm and progressive categories

3. Move car_insurance from Transportation to Insurance

4. Create "Education" parent category with subcategories:
   - books, courses, tuition

Run with:
    cd ~/DataspellProjects/budget-app
    uv run python -m backend.scripts.migrate_categories
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.database import SessionLocal, DB_PATH
from backend.models import Category, Transaction, MerchantMapping

def migrate():
    db = SessionLocal()

    print(f"Database: {DB_PATH}")
    print(f"File size: {DB_PATH.stat().st_size / (1024*1024):.1f} MB")
    print()

    try:
        # ─────────────────────────────────────────────
        # 1. Create Streaming Services parent + move streaming subcategories
        # ─────────────────────────────────────────────
        print("=== 1. Streaming Services ===")

        # Check if it already exists
        streaming_parent = db.query(Category).filter(
            Category.short_desc == "streaming_services",
            Category.parent_id.is_(None),
        ).first()

        if not streaming_parent:
            streaming_parent = Category(
                short_desc="streaming_services",
                display_name="Streaming Services",
                parent_id=None,
                color="#E74C3C",
                is_income=False,
            )
            db.add(streaming_parent)
            db.flush()
            print(f"  Created parent: Streaming Services (id={streaming_parent.id})")
        else:
            print(f"  Parent already exists (id={streaming_parent.id})")

        streaming_subs = ["spotify", "netflix", "hulu", "hbo", "apple_tv", "youtube_premium", "disney_plus"]
        for short_desc in streaming_subs:
            cat = db.query(Category).filter(Category.short_desc == short_desc).first()
            if cat:
                old_parent_id = cat.parent_id
                cat.parent_id = streaming_parent.id
                print(f"  Moved {short_desc} (id={cat.id}) from parent_id={old_parent_id} → {streaming_parent.id}")
            else:
                print(f"  WARNING: {short_desc} not found, skipping")

        # ─────────────────────────────────────────────
        # 2. Merge state_farm + progressive → car_insurance
        # ─────────────────────────────────────────────
        print("\n=== 2. Merge state_farm + progressive → car_insurance ===")

        car_insurance = db.query(Category).filter(Category.short_desc == "car_insurance").first()
        if not car_insurance:
            print("  ERROR: car_insurance category not found!")
            return

        for old_name in ["state_farm", "progressive"]:
            old_cat = db.query(Category).filter(Category.short_desc == old_name).first()
            if not old_cat:
                print(f"  {old_name}: not found, skipping")
                continue

            # Reassign transactions
            txn_count = db.query(Transaction).filter(Transaction.category_id == old_cat.id).count()
            db.query(Transaction).filter(Transaction.category_id == old_cat.id).update(
                {Transaction.category_id: car_insurance.id}, synchronize_session="fetch"
            )

            # Reassign predicted categories
            pred_count = db.query(Transaction).filter(Transaction.predicted_category_id == old_cat.id).count()
            db.query(Transaction).filter(Transaction.predicted_category_id == old_cat.id).update(
                {Transaction.predicted_category_id: car_insurance.id}, synchronize_session="fetch"
            )

            # Update merchant mappings
            map_count = db.query(MerchantMapping).filter(MerchantMapping.category_id == old_cat.id).count()
            db.query(MerchantMapping).filter(MerchantMapping.category_id == old_cat.id).update(
                {MerchantMapping.category_id: car_insurance.id}, synchronize_session="fetch"
            )

            # Delete the old category
            db.delete(old_cat)
            print(f"  {old_name} (id={old_cat.id}): "
                  f"moved {txn_count} txns, {pred_count} predictions, {map_count} mappings → car_insurance, then deleted")

        # ─────────────────────────────────────────────
        # 3. Move car_insurance from Transportation to Insurance
        # ─────────────────────────────────────────────
        print("\n=== 3. Move car_insurance to Insurance ===")

        insurance_parent = db.query(Category).filter(
            Category.short_desc == "insurance",
            Category.parent_id.is_(None),
        ).first()

        if not insurance_parent:
            print("  ERROR: Insurance parent category not found!")
            return

        old_parent = car_insurance.parent_id
        car_insurance.parent_id = insurance_parent.id
        print(f"  Moved car_insurance (id={car_insurance.id}) from parent_id={old_parent} → {insurance_parent.id}")

        # ─────────────────────────────────────────────
        # 4. Create Education parent + subcategories
        # ─────────────────────────────────────────────
        print("\n=== 4. Education ===")

        # Check if 'education' exists at all (could be a subcategory)
        education_existing = db.query(Category).filter(
            Category.short_desc == "education",
        ).first()

        if education_existing and education_existing.parent_id is None:
            # Already a parent category — use it
            education_parent = education_existing
            print(f"  Parent already exists (id={education_parent.id})")
        elif education_existing:
            # Exists as a subcategory — promote it to parent
            old_parent_id = education_existing.parent_id
            education_existing.parent_id = None
            education_existing.display_name = "Education"
            education_existing.color = "#5DADE2"
            education_existing.is_income = False
            education_parent = education_existing
            print(f"  Promoted existing subcategory (id={education_parent.id}) from parent_id={old_parent_id} to top-level parent")
        else:
            # Doesn't exist at all — create it
            education_parent = Category(
                short_desc="education",
                display_name="Education",
                parent_id=None,
                color="#5DADE2",
                is_income=False,
            )
            db.add(education_parent)
            db.flush()
            print(f"  Created parent: Education (id={education_parent.id})")

        education_subs = [
            ("books", "Books", False),
            ("courses", "Courses", False),
            ("tuition", "Tuition", False),
        ]

        for short_desc, display_name, is_recurring in education_subs:
            existing = db.query(Category).filter(Category.short_desc == short_desc).first()
            if not existing:
                cat = Category(
                    short_desc=short_desc,
                    display_name=display_name,
                    parent_id=education_parent.id,
                    is_recurring=is_recurring,
                )
                db.add(cat)
                print(f"  Created subcategory: {display_name}")
            else:
                print(f"  {short_desc} already exists (id={existing.id})")

        # ─────────────────────────────────────────────
        # Summary
        # ─────────────────────────────────────────────
        print("\n=== Summary ===")
        db.commit()
        print("Migration committed successfully!")

        # Print final category tree for verification
        parents = db.query(Category).filter(Category.parent_id.is_(None)).order_by(Category.display_name).all()
        for p in parents:
            children = db.query(Category).filter(Category.parent_id == p.id).order_by(Category.display_name).all()
            print(f"\n  {p.display_name} ({p.short_desc})")
            for c in children:
                txn_count = db.query(Transaction).filter(Transaction.category_id == c.id).count()
                suffix = f" — {txn_count} txns" if txn_count > 0 else ""
                print(f"    └─ {c.display_name} ({c.short_desc}){suffix}")

    except Exception as e:
        db.rollback()
        print(f"\nERROR: Migration failed — {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
