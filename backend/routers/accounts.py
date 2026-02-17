"""
Accounts API — Bank account management and Plaid Link flow.

Endpoints:
- GET    /api/accounts           — List all accounts with status/balances
- GET    /api/accounts/{id}      — Single account detail
- POST   /api/accounts/link/token    — Create Plaid Link token
- POST   /api/accounts/link/exchange — Exchange public_token for access_token
- POST   /api/accounts/{id}/sync     — Trigger manual transaction sync
- POST   /api/accounts/{id}/balances — Refresh account balances
"""

import logging
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from ..database import get_db
from ..models import Account, Transaction

router = APIRouter()


# --- Pydantic Schemas ---

class AccountOut(BaseModel):
    id: int
    name: str
    institution: str
    account_type: str
    plaid_connection_status: str
    plaid_account_id: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_sync_error: Optional[str] = None
    balance_current: Optional[float] = None
    balance_available: Optional[float] = None
    balance_limit: Optional[float] = None
    balance_updated_at: Optional[datetime] = None
    created_at: datetime
    # Date range of stored transactions
    earliest_transaction: Optional[date] = None
    latest_transaction: Optional[date] = None
    transaction_count: int = 0

    class Config:
        from_attributes = True


class AccountCreate(BaseModel):
    name: str
    institution: str
    account_type: str  # "checking", "savings", or "credit"


class LinkTokenRequest(BaseModel):
    account_id: int
    redirect_uri: Optional[str] = None


class LinkExchangeRequest(BaseModel):
    account_id: int
    public_token: str


class SyncResult(BaseModel):
    added: int
    modified: int
    removed: int


# --- Endpoints ---

@router.get("/", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    """List all bank accounts with connection status, balances, and date coverage."""
    accounts = db.query(Account).order_by(Account.institution, Account.name).all()

    # Fetch date range stats for all accounts in one query
    date_stats = (
        db.query(
            Transaction.account_id,
            func.min(Transaction.date).label("earliest"),
            func.max(Transaction.date).label("latest"),
            func.count(Transaction.id).label("count"),
        )
        .group_by(Transaction.account_id)
        .all()
    )
    stats_map = {s.account_id: s for s in date_stats}

    results = []
    for acct in accounts:
        out = AccountOut.model_validate(acct)
        stats = stats_map.get(acct.id)
        if stats:
            out.earliest_transaction = stats.earliest
            out.latest_transaction = stats.latest
            out.transaction_count = stats.count
        results.append(out)

    return results


@router.post("/", response_model=AccountOut)
def create_account(req: AccountCreate, db: Session = Depends(get_db)):
    """Create a new bank account that can then be linked via Plaid or used for CSV import."""
    if req.account_type not in ("checking", "savings", "credit"):
        raise HTTPException(status_code=400, detail="account_type must be checking, savings, or credit")

    account = Account(
        name=req.name,
        institution=req.institution,
        account_type=req.account_type,
        plaid_connection_status="disconnected",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    logger.info(f"Created account: {account.name} ({account.account_type}) at {account.institution}")
    return AccountOut.model_validate(account)


# NOTE: Literal paths (/sync-history) MUST be defined before
#       parameterised paths (/{account_id}) so FastAPI matches them first.

@router.get("/sync-history")
def get_sync_history(
    account_id: int = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Return recent sync log entries for all or a specific account."""
    from ..models import SyncLog

    query = db.query(SyncLog).order_by(SyncLog.started_at.desc())
    if account_id:
        query = query.filter(SyncLog.account_id == account_id)
    logs = query.limit(limit).all()

    return [
        {
            "id": log.id,
            "account_id": log.account_id,
            "account_name": log.account.name if log.account else "Unknown",
            "trigger": log.trigger,
            "status": log.status,
            "added": log.added,
            "modified": log.modified,
            "removed": log.removed,
            "error_message": log.error_message,
            "duration_seconds": log.duration_seconds,
            "started_at": log.started_at.isoformat() if log.started_at else None,
        }
        for log in logs
    ]


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """Get a single account by ID."""
    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/link/token")
def create_link_token(req: LinkTokenRequest, db: Session = Depends(get_db)):
    """
    Create a Plaid Link token for the frontend widget.
    The frontend opens Plaid Link with this token.
    """
    from ..services.plaid_service import plaid_service

    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        link_token = plaid_service.create_link_token(
            account.id, redirect_uri=req.redirect_uri
        )
        return {"link_token": link_token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plaid error: {str(e)}")


@router.post("/link/exchange")
def exchange_public_token(req: LinkExchangeRequest, db: Session = Depends(get_db)):
    """
    Exchange the public_token from Plaid Link for an access_token.
    Encrypts and stores the token, then triggers first sync.
    """
    from ..services.plaid_service import plaid_service

    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        result = plaid_service.exchange_public_token(req.public_token, account, db)

        # Trigger first sync for the primary account
        try:
            sync_result = plaid_service.sync_transactions(account, db, trigger="initial")
            result["sync"] = sync_result
        except Exception as sync_err:
            result["sync_error"] = str(sync_err)

        # Also sync any auto-linked sibling accounts
        if result.get("siblings_linked"):
            siblings = db.query(Account).filter(
                Account.institution == account.institution,
                Account.id != account.id,
                Account.plaid_connection_status == "connected",
            ).all()
            for sibling in siblings:
                try:
                    plaid_service.sync_transactions(sibling, db, trigger="initial")
                except Exception as sib_err:
                    logger.warning(f"Sibling sync failed for {sibling.name}: {sib_err}")

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {str(e)}")


@router.post("/{account_id}/sync", response_model=SyncResult)
def sync_account(account_id: int, db: Session = Depends(get_db)):
    """Manually trigger a transaction sync for one account."""
    from ..services.plaid_service import plaid_service

    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.plaid_connection_status != "connected":
        raise HTTPException(
            status_code=400,
            detail=f"Account is not connected (status: {account.plaid_connection_status})"
        )

    try:
        result = plaid_service.sync_transactions(account, db, trigger="manual")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/{account_id}/balances")
def refresh_balances(account_id: int, db: Session = Depends(get_db)):
    """Fetch current balances for one account from Plaid."""
    from ..services.plaid_service import plaid_service

    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.plaid_connection_status != "connected":
        raise HTTPException(
            status_code=400,
            detail=f"Account is not connected (status: {account.plaid_connection_status})"
        )

    try:
        result = plaid_service.get_account_balances(account, db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Balance fetch failed: {str(e)}")


@router.post("/{account_id}/disconnect")
def disconnect_account(account_id: int, db: Session = Depends(get_db)):
    """Disconnect a Plaid-linked account. Preserves all transaction data."""
    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Clear Plaid connection fields — but keep all transactions
    account.plaid_access_token = None
    account.plaid_item_id = None
    account.plaid_cursor = None
    account.plaid_account_id = None
    account.plaid_connection_status = "disconnected"
    account.last_synced_at = None
    account.last_sync_error = None
    account.balance_current = None
    account.balance_available = None
    account.balance_limit = None
    account.balance_updated_at = None

    db.commit()
    logger.info(f"Disconnected {account.name} — transaction data preserved")
    return {"status": "disconnected"}


@router.post("/{account_id}/reset-cursor")
def reset_cursor(account_id: int, db: Session = Depends(get_db)):
    """
    Reset the sync cursor so the next sync re-fetches all transactions
    from Plaid. Existing records are updated via dedup, not duplicated.
    """
    from ..services.plaid_service import plaid_service

    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.plaid_connection_status != "connected":
        raise HTTPException(
            status_code=400,
            detail=f"Account is not connected (status: {account.plaid_connection_status})"
        )

    account.plaid_cursor = None
    db.commit()

    # Immediately re-sync with fresh cursor
    try:
        result = plaid_service.sync_transactions(account, db, trigger="manual")
        return {"status": "ok", "cursor_reset": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed after reset: {str(e)}")


@router.post("/sync-all")
def sync_all_accounts(db: Session = Depends(get_db)):
    """Sync all connected accounts. Used by the scheduler and manual 'Sync All' button."""
    from ..services.plaid_service import plaid_service

    accounts = db.query(Account).filter(
        Account.plaid_connection_status == "connected"
    ).all()

    results = {}
    for account in accounts:
        try:
            result = plaid_service.sync_transactions(account, db, trigger="manual")
            results[account.name] = {"status": "ok", **result}
        except Exception as e:
            results[account.name] = {"status": "error", "error": str(e)}

    return {"accounts": results}
