# Part 3 — Plaid Integration & Account Management

This part covers connecting bank accounts through the Plaid API, encrypting access tokens at rest, syncing transactions incrementally, and the API endpoints that manage accounts.

---

## 3.1 How Plaid Works

Plaid is a middleware between your app and the user's bank. The flow is:

```
1. Backend creates a "link token" (short-lived, per-session)
2. Frontend opens the Plaid Link widget using that token
3. User logs into their bank inside the Plaid widget
4. Plaid returns a "public token" to the frontend
5. Frontend sends the public token to the backend
6. Backend exchanges it for a permanent "access token"
7. Backend uses the access token to pull transactions
```

You'll need a Plaid account. The sandbox environment is free and provides test data. For real bank connections, you need a development or production plan.

---

## 3.2 Plaid Service (`backend/services/plaid_service.py`)

This is the largest service file (~950 lines). Here are the key components.

### Client Initialization

The Plaid client is lazily initialized on first use, configured by environment variables:

```python
import os
from plaid.api import plaid_api
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid import Configuration, ApiClient

class PlaidService:
    _client = None

    @property
    def client(self):
        if self._client is None:
            env = os.getenv("PLAID_ENV", "sandbox")
            host = {
                "sandbox": "https://sandbox.plaid.com",
                "development": "https://development.plaid.com",
                "production": "https://production.plaid.com",
            }[env]

            # Use production secret if available and in production mode
            secret = os.getenv("PLAID_PRODUCTION_SECRET") if env == "production" \
                     else os.getenv("PLAID_SECRET")

            config = Configuration(
                host=host,
                api_key={
                    "clientId": os.getenv("PLAID_CLIENT_ID"),
                    "secret": secret,
                }
            )
            api_client = ApiClient(config)
            self._client = plaid_api.PlaidApi(api_client)
        return self._client
```

### Token Encryption

Plaid access tokens grant full access to a user's bank data, so they're encrypted at rest using Fernet (symmetric encryption from the `cryptography` library):

```python
from cryptography.fernet import Fernet
from pathlib import Path

KEY_PATH = Path.home() / "BudgetApp" / ".encryption_key"

def _get_or_create_key(self):
    """Load or generate the Fernet encryption key."""
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    else:
        key = Fernet.generate_key()
        KEY_PATH.write_bytes(key)
        KEY_PATH.chmod(0o600)  # Owner-only read/write
        return key

def encrypt_token(self, token: str) -> str:
    key = self._get_or_create_key()
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()

def decrypt_token(self, encrypted: str) -> str:
    key = self._get_or_create_key()
    f = Fernet(key)
    return f.decrypt(encrypted.encode()).decode()
```

The encryption key is stored at `~/BudgetApp/.encryption_key` with `0o600` permissions (owner-only). It's auto-generated on first use if missing.

### Link Token Creation

Creates a temporary link token that the frontend needs to open the Plaid Link widget:

```python
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser

def create_link_token(self):
    request = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id="budget-app-user"),
        client_name="Budget App",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en",
        redirect_uri="http://localhost:5173/oauth-callback",
    )
    response = self.client.link_token_create(request)
    return response.link_token
```

The `redirect_uri` is needed for OAuth-based banks (banks that redirect to their own login page instead of using Plaid's in-widget login).

### Token Exchange and Account Linking

After the user completes the Plaid Link flow, the frontend sends the public token. The backend exchanges it for a permanent access token and links accounts:

```python
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

def exchange_public_token(self, account_id: int, public_token: str, db):
    """Exchange Plaid public token for access token and link the account."""
    # Exchange for permanent access token
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = self.client.item_public_token_exchange(request)
    access_token = response.access_token
    item_id = response.item_id

    # Encrypt and store
    account = db.query(Account).get(account_id)
    account.plaid_access_token = self.encrypt_token(access_token)
    account.plaid_item_id = item_id
    account.plaid_connection_status = "connected"

    # Match Plaid's sub-accounts to local accounts
    self._match_plaid_accounts(access_token, item_id, db)

    db.commit()
    return {"status": "linked", "item_id": item_id}
```

### Account Matching

A single Plaid "item" (one bank login) can contain multiple accounts (checking, savings, credit). The service matches them to local accounts by type:

```python
def _match_plaid_accounts(self, access_token, item_id, db):
    """Match Plaid's accounts to local Account records."""
    from plaid.model.accounts_get_request import AccountsGetRequest

    response = self.client.accounts_get(
        AccountsGetRequest(access_token=access_token)
    )

    for plaid_acct in response.accounts:
        # Try to match by account type (checking, savings, credit)
        local = (
            db.query(Account)
            .filter(
                Account.plaid_item_id == item_id,
                Account.plaid_account_id.is_(None),
            )
            .first()
        )
        if local:
            local.plaid_account_id = plaid_acct.account_id
            local.plaid_connection_status = "connected"
```

### Transaction Sync

The core sync method uses Plaid's cursor-based pagination to fetch only new/modified/removed transactions since the last sync:

```python
from plaid.model.transactions_sync_request import TransactionsSyncRequest

def sync_transactions(self, account, db, trigger="manual"):
    """Incremental transaction sync using Plaid's cursor-based API."""
    start_time = datetime.utcnow()
    access_token = self.decrypt_token(account.plaid_access_token)
    cursor = account.plaid_cursor or ""

    added_count = 0
    modified_count = 0
    removed_count = 0

    try:
        has_more = True
        while has_more:
            request = TransactionsSyncRequest(
                access_token=access_token,
                cursor=cursor,
            )
            response = self.client.transactions_sync(request)

            # Process added transactions
            for txn in response.added:
                if txn.pending:
                    continue  # Skip pending transactions

                # Deduplicate by plaid_transaction_id
                existing = db.query(Transaction).filter(
                    Transaction.plaid_transaction_id == txn.transaction_id
                ).first()
                if existing:
                    continue

                new_txn = Transaction(
                    account_id=account.id,
                    plaid_transaction_id=txn.transaction_id,
                    date=txn.date,
                    description=txn.name,
                    merchant_name=txn.merchant_name or txn.name,
                    amount=txn.amount,  # Plaid: positive = expense
                    source="plaid",
                    status="pending_review",
                )
                db.add(new_txn)
                db.flush()

                # Auto-categorize
                categorize_transaction(new_txn, db)
                added_count += 1

            # Process modified transactions
            for txn in response.modified:
                existing = db.query(Transaction).filter(
                    Transaction.plaid_transaction_id == txn.transaction_id
                ).first()
                if existing:
                    existing.amount = txn.amount
                    existing.description = txn.name
                    existing.merchant_name = txn.merchant_name or txn.name
                    modified_count += 1

            # Process removed transactions
            for txn in response.removed:
                existing = db.query(Transaction).filter(
                    Transaction.plaid_transaction_id == txn.transaction_id
                ).first()
                if existing:
                    db.delete(existing)
                    removed_count += 1

            cursor = response.next_cursor
            has_more = response.has_more

        # Update account state
        account.plaid_cursor = cursor
        account.last_synced_at = datetime.utcnow()
        account.last_sync_error = None

        # Log the sync
        duration = (datetime.utcnow() - start_time).total_seconds()
        sync_log = SyncLog(
            account_id=account.id,
            trigger=trigger,
            status="success",
            added=added_count,
            modified=modified_count,
            removed=removed_count,
            duration_seconds=duration,
        )
        db.add(sync_log)
        db.commit()

        return {
            "added": added_count,
            "modified": modified_count,
            "removed": removed_count,
        }

    except Exception as e:
        # Log the failure
        sync_log = SyncLog(
            account_id=account.id,
            trigger=trigger,
            status="error",
            error_message=str(e),
            duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
        )
        db.add(sync_log)
        db.commit()
        raise
```

Key details:

- **Cursor-based pagination**: Plaid maintains a cursor that tracks your last sync position. Each call returns only what's changed since that cursor, making syncs fast and bandwidth-efficient.
- **Pending transactions skipped**: Plaid marks transactions as "pending" before they clear. We skip these to avoid duplicates (they reappear as non-pending later).
- **Deduplication**: The `plaid_transaction_id` unique constraint prevents duplicate imports.
- **Auto-categorization**: Each new transaction is immediately run through the 3-tier categorization engine (covered in Part 4).
- **Mutation retry**: Plaid sometimes returns `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION` errors. The service retries up to 3 times with the cursor reset.
- **SyncLog**: Every sync attempt (success or failure) is recorded in the `sync_log` table for the audit trail.

---

## 3.3 Accounts Router (`backend/routers/accounts.py`)

The accounts API handles listing accounts, the Plaid Link flow, manual syncing, and sync history.

### Listing Accounts

```python
@router.get("")
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.query(Account).all()
    result = []
    for acct in accounts:
        txn_count = db.query(Transaction).filter(
            Transaction.account_id == acct.id
        ).count()
        # Get date range coverage
        earliest = db.query(func.min(Transaction.date)).filter(
            Transaction.account_id == acct.id
        ).scalar()
        latest = db.query(func.max(Transaction.date)).filter(
            Transaction.account_id == acct.id
        ).scalar()
        result.append({
            "id": acct.id,
            "name": acct.name,
            "institution": acct.institution,
            "account_type": acct.account_type,
            "plaid_connection_status": acct.plaid_connection_status,
            "last_synced_at": acct.last_synced_at,
            "balance_current": acct.balance_current,
            "transaction_count": txn_count,
            "earliest_date": str(earliest) if earliest else None,
            "latest_date": str(latest) if latest else None,
        })
    return result
```

### Plaid Link Flow

Two endpoints handle the Plaid Link widget flow:

```python
@router.post("/link/create")
def create_link_token(db: Session = Depends(get_db)):
    """Create a Plaid Link token for the frontend widget."""
    plaid = PlaidService()
    link_token = plaid.create_link_token()
    return {"link_token": link_token}


@router.post("/link/exchange")
def exchange_public_token(body: dict, db: Session = Depends(get_db)):
    """Exchange the public token from Plaid Link for an access token."""
    plaid = PlaidService()
    result = plaid.exchange_public_token(
        account_id=body["account_id"],
        public_token=body["public_token"],
        db=db,
    )
    return result
```

### Sync Endpoints

```python
@router.post("/{account_id}/sync")
def sync_account(account_id: int, db: Session = Depends(get_db)):
    """Manually trigger a transaction sync for one account."""
    account = db.query(Account).get(account_id)
    if not account or account.plaid_connection_status != "connected":
        raise HTTPException(status_code=400, detail="Account not connected")

    plaid = PlaidService()
    result = plaid.sync_transactions(account, db, trigger="manual")
    return result


@router.post("/sync-all")
def sync_all_accounts(db: Session = Depends(get_db)):
    """Sync all connected accounts at once."""
    accounts = db.query(Account).filter(
        Account.plaid_connection_status == "connected"
    ).all()

    plaid = PlaidService()
    results = {}
    for account in accounts:
        try:
            results[account.name] = plaid.sync_transactions(
                account, db, trigger="manual"
            )
        except Exception as e:
            results[account.name] = {"error": str(e)}
    return results
```

### Sync History

> **Important**: This endpoint uses a literal path `/sync-history`. It MUST be defined before any parameterized path like `/{account_id}`, otherwise FastAPI will try to parse `"sync-history"` as an integer account ID.

```python
# NOTE: Literal paths MUST be defined before parameterised paths
# so FastAPI matches them first.

@router.get("/sync-history")
def get_sync_history(
    account_id: int = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Return recent sync log entries."""
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
```

### Disconnect

Disconnects an account from Plaid while preserving all transaction data:

```python
@router.post("/{account_id}/disconnect")
def disconnect_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404)

    account.plaid_connection_status = "disconnected"
    account.plaid_access_token = None
    account.plaid_cursor = None
    account.plaid_item_id = None
    account.plaid_account_id = None
    db.commit()
    return {"status": "disconnected"}
```

---

## 3.4 Balance Fetching

The service also fetches current account balances from Plaid:

```python
def fetch_balances(self, account, db):
    """Fetch current balances from Plaid."""
    access_token = self.decrypt_token(account.plaid_access_token)
    response = self.client.accounts_get(
        AccountsGetRequest(access_token=access_token)
    )

    for plaid_acct in response.accounts:
        if plaid_acct.account_id == account.plaid_account_id:
            account.balance_current = plaid_acct.balances.current
            account.balance_available = plaid_acct.balances.available
            account.balance_limit = plaid_acct.balances.limit
            account.balance_updated_at = datetime.utcnow()
            break

    db.commit()
```

---

## 3.5 OAuth Callback Handling

Some banks (like Chase, Wells Fargo) use OAuth instead of Plaid's in-widget login. For these, Plaid redirects the user to the bank's website, then back to your app. The frontend handles this redirect:

```jsx
// frontend/src/App.jsx — OAuthCallback component

function OAuthCallback() {
  const navigate = useNavigate()
  const linkToken = sessionStorage.getItem('plaid_link_token')
  const accountId = sessionStorage.getItem('plaid_account_id')

  const onSuccess = useCallback(async (publicToken) => {
    const res = await fetch('/api/accounts/link/exchange', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: parseInt(accountId),
        public_token: publicToken,
      }),
    })
    if (res.ok) {
      sessionStorage.removeItem('plaid_link_token')
      sessionStorage.removeItem('plaid_account_id')
      navigate('/accounts')
    }
  }, [accountId, navigate])

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess,
    onExit: () => navigate('/accounts'),
    receivedRedirectUri: window.location.href,
  })

  useEffect(() => {
    if (ready) open()
  }, [ready, open])

  return <div className="empty-state"><p>Completing bank connection...</p></div>
}
```

Before opening the Plaid Link widget for an OAuth bank, the frontend stores the link token and account ID in `sessionStorage` so they survive the redirect. When Plaid redirects back to `/oauth-callback`, this component picks up where it left off.

---

## What's Next

With bank accounts connected and transactions flowing in, Part 4 covers how those transactions get categorized: the 3-tier categorization engine, the review workflow, CSV import, and seed data.

→ [Part 4: Transaction Processing & Categorization](04-categorization-engine.md)
