"""
Archive Import API — Import historical transaction data from Excel/CSV archives.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter()

# Base path for the Budget archive folder (relative to project root)
BUDGET_FOLDER = "Budget"


class ArchiveImportRequest(BaseModel):
    file_path: str
    default_account: Optional[str] = None  # e.g., "discover" for single-account files


@router.get("/scan")
def scan_archives():
    """Scan the Budget folder for importable archive files."""
    from ..services.archive_importer import scan_archive_folder
    files = scan_archive_folder(BUDGET_FOLDER)
    return {"files": files}


@router.post("/import")
def import_archive(req: ArchiveImportRequest, db: Session = Depends(get_db)):
    """Import a specific archive file into the database."""
    from ..services.archive_importer import import_archive_excel

    try:
        result = import_archive_excel(
            file_path=req.file_path,
            db=db,
            default_account=req.default_account,
        )
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {req.file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/coverage")
def get_data_coverage(db: Session = Depends(get_db)):
    """
    Get a summary of transaction coverage by year and source.
    Shows what years have data and where it came from (Plaid vs archive vs CSV).
    """
    from sqlalchemy import func, extract
    from ..models import Transaction

    results = (
        db.query(
            func.strftime("%Y", Transaction.date).label("year"),
            Transaction.source,
            func.count(Transaction.id).label("count"),
            func.min(Transaction.date).label("earliest"),
            func.max(Transaction.date).label("latest"),
        )
        .group_by(func.strftime("%Y", Transaction.date), Transaction.source)
        .order_by(func.strftime("%Y", Transaction.date))
        .all()
    )

    coverage = {}
    for r in results:
        year = r.year
        if year not in coverage:
            coverage[year] = {"year": year, "sources": {}, "total": 0}
        coverage[year]["sources"][r.source] = {
            "count": r.count,
            "earliest": str(r.earliest),
            "latest": str(r.latest),
        }
        coverage[year]["total"] += r.count

    return {"coverage": list(coverage.values())}
