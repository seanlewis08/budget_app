"""
Investment account management and portfolio analysis endpoints.
All data lives in investments.db, separate from the main budget database.
"""

from typing import Optional
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from ..investments_database import get_investments_db
from ..models_investments import InvestmentAccount, Security, Holding, InvestmentTransaction

router = APIRouter()


# ── Pydantic Schemas ──


class InvestmentAccountOut(BaseModel):
    id: int
    account_name: str
    account_type: str
    institution_name: Optional[str] = None
    connection_status: str
    last_synced_at: Optional[str] = None
    last_sync_error: Optional[str] = None
    total_value: Optional[float] = None

    class Config:
        from_attributes = True


class SecurityOut(BaseModel):
    id: int
    ticker: Optional[str] = None
    name: str
    security_type: str
    sector: Optional[str] = None
    close_price: Optional[float] = None
    close_price_as_of: Optional[str] = None
    price_source: Optional[str] = None


class HoldingOut(BaseModel):
    id: int
    account_id: int
    account_name: str
    security_id: int
    ticker: Optional[str] = None
    name: str
    security_type: str
    quantity: float
    cost_basis: Optional[float] = None
    cost_basis_per_unit: Optional[float] = None
    current_value: Optional[float] = None
    current_price: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_pct: Optional[float] = None
    weight_pct: Optional[float] = None


class InvestmentTransactionOut(BaseModel):
    id: int
    account_name: str
    ticker: Optional[str] = None
    security_name: Optional[str] = None
    date: str
    type: str
    quantity: Optional[float] = None
    price: Optional[float] = None
    amount: float
    fees: float
    notes: Optional[str] = None


class LinkTokenRequest(BaseModel):
    redirect_uri: Optional[str] = None


class ExchangeRequest(BaseModel):
    public_token: str
    account_name: str
    account_type: str = "taxable"
    institution_name: Optional[str] = None


class ManualAccountRequest(BaseModel):
    account_name: str
    account_type: str = "taxable"
    institution_name: Optional[str] = None


class ManualHoldingRequest(BaseModel):
    ticker: str
    name: Optional[str] = None
    quantity: float
    cost_basis_per_share: Optional[float] = None


# ── Portfolio Summary ──


@router.get("/summary")
def portfolio_summary(inv_db: Session = Depends(get_investments_db)):
    """
    Portfolio overview: total value, cost basis, gain/loss, day change,
    and per-account breakdown.
    """
    # Get the most recent snapshot date
    latest_date = inv_db.query(func.max(Holding.as_of_date)).scalar()
    if not latest_date:
        return {
            "total_value": 0,
            "total_cost_basis": 0,
            "total_gain_loss": 0,
            "total_gain_loss_pct": 0,
            "day_change": 0,
            "day_change_pct": 0,
            "accounts": [],
            "last_updated": None,
        }

    # Current holdings (latest snapshot)
    holdings = (
        inv_db.query(Holding)
        .filter(Holding.as_of_date == latest_date)
        .all()
    )

    total_value = 0.0
    total_cost_basis = 0.0
    account_values = {}  # account_id -> value

    for h in holdings:
        val = h.current_value or 0
        cost = h.cost_basis or 0
        total_value += val
        total_cost_basis += cost
        account_values[h.investment_account_id] = account_values.get(h.investment_account_id, 0) + val

    total_gain_loss = total_value - total_cost_basis
    total_gain_loss_pct = (total_gain_loss / total_cost_basis * 100) if total_cost_basis > 0 else 0

    # Day change: compare to previous snapshot
    prev_date = (
        inv_db.query(func.max(Holding.as_of_date))
        .filter(Holding.as_of_date < latest_date)
        .scalar()
    )
    day_change = 0.0
    day_change_pct = 0.0
    if prev_date:
        prev_holdings = inv_db.query(Holding).filter(Holding.as_of_date == prev_date).all()
        prev_value = sum(h.current_value or 0 for h in prev_holdings)
        if prev_value > 0:
            day_change = total_value - prev_value
            day_change_pct = day_change / prev_value * 100

    # Account breakdown
    accounts = inv_db.query(InvestmentAccount).all()
    account_list = []
    for acct in accounts:
        acct_value = account_values.get(acct.id, 0)
        account_list.append({
            "id": acct.id,
            "account_name": acct.account_name,
            "account_type": acct.account_type,
            "institution_name": acct.institution_name,
            "connection_status": acct.connection_status,
            "last_synced_at": acct.last_synced_at.isoformat() if acct.last_synced_at else None,
            "total_value": round(acct_value, 2),
        })

    return {
        "total_value": round(total_value, 2),
        "total_cost_basis": round(total_cost_basis, 2),
        "total_gain_loss": round(total_gain_loss, 2),
        "total_gain_loss_pct": round(total_gain_loss_pct, 2),
        "day_change": round(day_change, 2),
        "day_change_pct": round(day_change_pct, 2),
        "accounts": account_list,
        "last_updated": latest_date.isoformat() if latest_date else None,
    }


# ── Holdings ──


@router.get("/holdings")
def list_holdings(
    account_id: Optional[int] = None,
    inv_db: Session = Depends(get_investments_db),
):
    """
    All holdings across accounts (latest snapshot), with gain/loss and weight %.
    Optionally filter by account_id.
    """
    latest_date = inv_db.query(func.max(Holding.as_of_date)).scalar()
    if not latest_date:
        return []

    query = inv_db.query(Holding).filter(Holding.as_of_date == latest_date)
    if account_id:
        query = query.filter(Holding.investment_account_id == account_id)

    holdings = query.all()

    # Calculate total value for weight %
    total_value = sum(h.current_value or 0 for h in holdings)

    results = []
    for h in holdings:
        security = inv_db.query(Security).get(h.security_id)
        account = inv_db.query(InvestmentAccount).get(h.investment_account_id)
        if not security:
            continue

        val = h.current_value or 0
        cost = h.cost_basis or 0
        gain_loss = val - cost if cost > 0 else None
        gain_loss_pct = (gain_loss / cost * 100) if cost > 0 and gain_loss is not None else None
        weight = (val / total_value * 100) if total_value > 0 else 0

        results.append(HoldingOut(
            id=h.id,
            account_id=h.investment_account_id,
            account_name=account.account_name if account else "Unknown",
            security_id=h.security_id,
            ticker=security.ticker,
            name=security.name,
            security_type=security.security_type,
            quantity=round(h.quantity, 4),
            cost_basis=round(cost, 2) if cost else None,
            cost_basis_per_unit=round(h.cost_basis_per_unit, 4) if h.cost_basis_per_unit else None,
            current_value=round(val, 2),
            current_price=security.close_price,
            gain_loss=round(gain_loss, 2) if gain_loss is not None else None,
            gain_loss_pct=round(gain_loss_pct, 2) if gain_loss_pct is not None else None,
            weight_pct=round(weight, 2),
        ))

    # Sort by value descending
    results.sort(key=lambda x: x.current_value or 0, reverse=True)
    return results


# ── Performance ──


@router.get("/performance")
def portfolio_performance(
    months: int = Query(default=12, ge=1, le=60),
    inv_db: Session = Depends(get_investments_db),
):
    """
    Date series of portfolio values from holding snapshots.
    Returns daily data points for charting.
    """
    start_date = date.today() - timedelta(days=months * 30)

    # Get daily portfolio totals
    daily_values = (
        inv_db.query(
            Holding.as_of_date,
            func.sum(Holding.current_value).label("total_value"),
            func.sum(Holding.cost_basis).label("total_cost_basis"),
        )
        .filter(Holding.as_of_date >= start_date)
        .group_by(Holding.as_of_date)
        .order_by(Holding.as_of_date)
        .all()
    )

    return [
        {
            "date": row.as_of_date.isoformat(),
            "value": round(row.total_value or 0, 2),
            "cost_basis": round(row.total_cost_basis or 0, 2),
        }
        for row in daily_values
    ]


# ── Allocation ──


@router.get("/allocation")
def portfolio_allocation(inv_db: Session = Depends(get_investments_db)):
    """
    Breakdown by security_type and by sector for the latest snapshot.
    """
    latest_date = inv_db.query(func.max(Holding.as_of_date)).scalar()
    if not latest_date:
        return {"by_type": [], "by_sector": []}

    holdings = inv_db.query(Holding).filter(Holding.as_of_date == latest_date).all()

    by_type = {}
    by_sector = {}
    total = 0.0

    for h in holdings:
        security = inv_db.query(Security).get(h.security_id)
        if not security:
            continue

        val = h.current_value or 0
        total += val

        sec_type = security.security_type or "other"
        by_type[sec_type] = by_type.get(sec_type, 0) + val

        sector = security.sector or "Unknown"
        by_sector[sector] = by_sector.get(sector, 0) + val

    def to_list(d):
        return sorted(
            [
                {"name": k, "value": round(v, 2), "pct": round(v / total * 100, 2) if total > 0 else 0}
                for k, v in d.items()
            ],
            key=lambda x: x["value"],
            reverse=True,
        )

    return {
        "by_type": to_list(by_type),
        "by_sector": to_list(by_sector),
        "total_value": round(total, 2),
    }


# ── Investment Transactions ──


@router.get("/transactions")
def list_investment_transactions(
    type: Optional[str] = None,
    account_id: Optional[int] = None,
    security_id: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    inv_db: Session = Depends(get_investments_db),
):
    """Paginated investment transaction history with filters."""
    query = inv_db.query(InvestmentTransaction)

    if type:
        types = [t.strip() for t in type.split(",")]
        query = query.filter(InvestmentTransaction.type.in_(types))
    if account_id:
        query = query.filter(InvestmentTransaction.investment_account_id == account_id)
    if security_id:
        query = query.filter(InvestmentTransaction.security_id == security_id)

    total = query.count()
    txns = query.order_by(desc(InvestmentTransaction.date)).offset(offset).limit(limit).all()

    results = []
    for t in txns:
        account = inv_db.query(InvestmentAccount).get(t.investment_account_id)
        security = inv_db.query(Security).get(t.security_id) if t.security_id else None

        results.append(InvestmentTransactionOut(
            id=t.id,
            account_name=account.account_name if account else "Unknown",
            ticker=security.ticker if security else None,
            security_name=security.name if security else None,
            date=t.date.isoformat(),
            type=t.type,
            quantity=t.quantity,
            price=t.price,
            amount=t.amount,
            fees=t.fees or 0,
            notes=t.notes,
        ))

    return {"transactions": results, "total": total, "limit": limit, "offset": offset}


# ── Account Management ──


@router.get("/accounts")
def list_investment_accounts(inv_db: Session = Depends(get_investments_db)):
    """List all investment accounts."""
    accounts = inv_db.query(InvestmentAccount).all()
    results = []
    for acct in accounts:
        # Get latest total value
        latest_date = (
            inv_db.query(func.max(Holding.as_of_date))
            .filter(Holding.investment_account_id == acct.id)
            .scalar()
        )
        total_value = 0
        if latest_date:
            holdings = inv_db.query(Holding).filter(
                Holding.investment_account_id == acct.id,
                Holding.as_of_date == latest_date,
            ).all()
            total_value = sum(h.current_value or 0 for h in holdings)

        results.append(InvestmentAccountOut(
            id=acct.id,
            account_name=acct.account_name,
            account_type=acct.account_type,
            institution_name=acct.institution_name,
            connection_status=acct.connection_status,
            last_synced_at=acct.last_synced_at.isoformat() if acct.last_synced_at else None,
            last_sync_error=acct.last_sync_error,
            total_value=round(total_value, 2),
        ))
    return results


@router.post("/link-token")
def create_investment_link_token(data: LinkTokenRequest):
    """Create a Plaid link token with the investments product."""
    from ..services.plaid_service import plaid_service

    try:
        link_token = plaid_service.create_link_token_investments(
            user_id=1,  # Single-user app
            redirect_uri=data.redirect_uri,
        )
        return {"link_token": link_token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create link token: {e}")


@router.post("/link/exchange")
def exchange_investment_token(
    data: ExchangeRequest,
    inv_db: Session = Depends(get_investments_db),
):
    """
    Exchange a public token from Plaid Link, create an InvestmentAccount,
    and run the initial sync.
    """
    from ..services.plaid_service import plaid_service
    from ..database import SessionLocal
    from ..models import Account

    budget_db = SessionLocal()
    try:
        # Exchange the public token
        request_data = {
            "public_token": data.public_token,
        }
        from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
        exchange_req = ItemPublicTokenExchangeRequest(**request_data)
        response = plaid_service.client.item_public_token_exchange(exchange_req)

        access_token = response["access_token"]
        item_id = response["item_id"]
        encrypted_token = plaid_service.encrypt_token(access_token)

        # Detect the Plaid account ID for investments
        from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
        holdings_req = InvestmentsHoldingsGetRequest(access_token=access_token)
        holdings_resp = plaid_service.client.investments_holdings_get(holdings_req)
        plaid_accounts = holdings_resp.get("accounts", [])

        plaid_account_id = None
        if plaid_accounts:
            # Use the first investment account found
            for pa in plaid_accounts:
                if str(pa.get("type")) == "investment":
                    plaid_account_id = pa["account_id"]
                    break
            if not plaid_account_id:
                plaid_account_id = plaid_accounts[0]["account_id"]

        # Create InvestmentAccount
        inv_account = InvestmentAccount(
            plaid_item_id=item_id,
            plaid_account_id=plaid_account_id,
            account_name=data.account_name,
            account_type=data.account_type,
            institution_name=data.institution_name,
            connection_status="connected",
        )
        inv_db.add(inv_account)
        inv_db.commit()
        inv_db.refresh(inv_account)

        # We also need a budget Account record to store the encrypted access token
        # Check if one already exists for this item_id
        existing_budget_acct = budget_db.query(Account).filter(
            Account.plaid_item_id == item_id
        ).first()

        if not existing_budget_acct:
            # Create a minimal budget Account to hold the access token
            budget_acct = Account(
                name=f"{data.account_name} (Investment)",
                institution=data.institution_name or "Fidelity",
                account_type="investment",
                plaid_access_token=encrypted_token,
                plaid_item_id=item_id,
                plaid_account_id=plaid_account_id,
                plaid_connection_status="connected",
            )
            budget_db.add(budget_acct)
            budget_db.commit()
        else:
            # Reuse existing budget account's access token
            encrypted_token = existing_budget_acct.plaid_access_token

        # Run initial sync
        try:
            h_result = plaid_service.sync_investment_holdings(
                encrypted_token, inv_account, inv_db
            )
            t_result = plaid_service.sync_investment_transactions(
                encrypted_token, inv_account, inv_db
            )
        except Exception as e:
            # Account created but sync failed — not fatal
            inv_account.last_sync_error = str(e)[:500]
            inv_db.commit()
            return {
                "status": "linked_with_errors",
                "account_id": inv_account.id,
                "error": str(e),
            }

        return {
            "status": "linked",
            "account_id": inv_account.id,
            "holdings_synced": h_result["holdings_upserted"],
            "transactions_synced": t_result["added"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to link investment account: {e}")
    finally:
        budget_db.close()


@router.post("/accounts/manual")
def create_manual_account(
    data: ManualAccountRequest,
    inv_db: Session = Depends(get_investments_db),
):
    """Create a manually-tracked investment account (no Plaid connection)."""
    inv_account = InvestmentAccount(
        account_name=data.account_name,
        account_type=data.account_type,
        institution_name=data.institution_name,
        connection_status="manual",
    )
    inv_db.add(inv_account)
    inv_db.commit()
    inv_db.refresh(inv_account)
    return {
        "status": "created",
        "account_id": inv_account.id,
        "account_name": inv_account.account_name,
    }


@router.post("/accounts/{account_id}/holdings")
def add_manual_holding(
    account_id: int,
    data: ManualHoldingRequest,
    inv_db: Session = Depends(get_investments_db),
):
    """Add a holding to a manual investment account."""
    inv_account = inv_db.query(InvestmentAccount).get(account_id)
    if not inv_account:
        raise HTTPException(status_code=404, detail="Investment account not found")

    # Find or create the security by ticker
    security = inv_db.query(Security).filter(Security.ticker == data.ticker.upper()).first()
    if not security:
        security = Security(
            ticker=data.ticker.upper(),
            name=data.name or data.ticker.upper(),
            security_type="equity",
        )
        inv_db.add(security)
        inv_db.flush()

    # Fetch current price if possible
    current_price = security.close_price
    if not current_price:
        try:
            from ..services.price_fetcher import fetch_price_for_ticker
            current_price = fetch_price_for_ticker(data.ticker.upper())
            if current_price:
                security.close_price = current_price
                security.close_price_as_of = date.today()
                security.price_source = "yfinance"
        except Exception:
            pass

    cost_basis = (data.cost_basis_per_share or 0) * data.quantity
    current_value = (current_price or 0) * data.quantity

    holding = Holding(
        investment_account_id=account_id,
        security_id=security.id,
        quantity=data.quantity,
        cost_basis=round(cost_basis, 2),
        current_value=round(current_value, 2),
        as_of_date=date.today(),
    )
    inv_db.add(holding)
    inv_db.commit()

    return {
        "status": "added",
        "holding_id": holding.id,
        "ticker": security.ticker,
        "quantity": data.quantity,
        "current_value": round(current_value, 2),
    }


@router.delete("/accounts/{account_id}")
def delete_investment_account(
    account_id: int,
    inv_db: Session = Depends(get_investments_db),
):
    """Delete an investment account and all its holdings/transactions."""
    inv_account = inv_db.query(InvestmentAccount).get(account_id)
    if not inv_account:
        raise HTTPException(status_code=404, detail="Investment account not found")
    inv_db.delete(inv_account)
    inv_db.commit()
    return {"status": "deleted", "account_id": account_id}


@router.post("/accounts/{account_id}/sync")
def manual_sync(
    account_id: int,
    inv_db: Session = Depends(get_investments_db),
):
    """Manually trigger a sync for a specific investment account."""
    from ..services.plaid_service import plaid_service
    from ..database import SessionLocal
    from ..models import Account

    inv_account = inv_db.query(InvestmentAccount).get(account_id)
    if not inv_account:
        raise HTTPException(status_code=404, detail="Investment account not found")

    budget_db = SessionLocal()
    try:
        budget_account = budget_db.query(Account).filter(
            Account.plaid_item_id == inv_account.plaid_item_id
        ).first()

        if not budget_account or not budget_account.plaid_access_token:
            raise HTTPException(status_code=400, detail="No access token found for this account")

        h_result = plaid_service.sync_investment_holdings(
            budget_account.plaid_access_token, inv_account, inv_db
        )
        t_result = plaid_service.sync_investment_transactions(
            budget_account.plaid_access_token, inv_account, inv_db
        )

        return {
            "status": "synced",
            "securities_upserted": h_result["securities_upserted"],
            "holdings_upserted": h_result["holdings_upserted"],
            "transactions_added": t_result["added"],
            "transactions_skipped": t_result["skipped"],
        }
    finally:
        budget_db.close()


@router.post("/refresh-prices")
def refresh_prices(inv_db: Session = Depends(get_investments_db)):
    """Manually trigger a price refresh for all securities via yfinance."""
    from ..services.price_fetcher import fetch_all_prices

    result = fetch_all_prices(inv_db)
    return {
        "status": "refreshed",
        "updated": result["updated"],
        "failed": result["failed"],
        "tickers": result["tickers"],
    }
