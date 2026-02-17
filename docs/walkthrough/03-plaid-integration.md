# Part 3 — Plaid Integration & Account Management

In Parts 1 and 2, we built the project foundation and database layer. Now we're going to connect real bank accounts. By the end of this part, the app will automatically pull transactions from your bank, encrypt sensitive tokens at rest, handle the full Plaid Link flow (including OAuth banks), sync incrementally using cursors, and run background jobs to keep your data fresh.

Plaid integration is optional — the app works perfectly fine with just CSV imports. But automatic syncing is what makes this a true "set it and forget it" personal finance tool. If you don't want to set up Plaid, you can skip this part and come back later. The app degrades gracefully: if Plaid credentials aren't configured, bank syncing is simply disabled and everything else works normally.

---

## 3.1 How Plaid Works

Plaid acts as a middleman between your app and your bank. Instead of each bank having its own API (they don't), Plaid provides a single, consistent API that works with thousands of banks. Here's the full flow:

```
1. Your backend asks Plaid for a temporary "link token"
2. Your frontend opens the Plaid Link widget with that token
3. The user logs into their bank inside Plaid's secure widget
4. Plaid returns a "public token" to the frontend
5. The frontend sends the public token to your backend
6. Your backend exchanges it for a permanent "access token"
7. Your backend uses the access token to pull transactions
```

The key security detail: your app never sees the user's bank password. The Plaid Link widget is hosted by Plaid, and the bank credentials go directly from the user to Plaid to the bank. Your app only receives tokens — the access token is the permanent key that lets you fetch data.

You'll need a Plaid account to use this. The sandbox environment is free and provides realistic test data. For real bank connections, you need a development or production plan. Sign up at [dashboard.plaid.com](https://dashboard.plaid.com).

---

## 3.2 The Plaid Service (`backend/services/plaid_service.py`)

All Plaid interactions go through a single service class. This is the largest service file in the app (~960 lines) because it handles a lot: client initialization, token encryption, link token creation, token exchange, account matching, transaction syncing with deduplication, balance fetching, and investment syncing.

Let's walk through each piece.

### Client Initialization

The Plaid client is lazily initialized — it's only created the first time something tries to use it. If Plaid credentials aren't configured, it returns `None` instead of crashing:

```python
import os
import logging
import plaid
from plaid.api import plaid_api
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid import Configuration, ApiClient
from cryptography.fernet import Fernet
from typing import Optional

logger = logging.getLogger(__name__)


class PlaidService:
    """Wraps the Plaid API client with encryption and business logic."""

    def __init__(self):
        self._client: Optional[plaid_api.PlaidApi] = None
        self._fernet: Optional[Fernet] = None

    @property
    def client(self) -> Optional[plaid_api.PlaidApi]:
        """Lazy-init the Plaid API client. Returns None if credentials are missing."""
        if self._client is None:
            env = os.getenv("PLAID_ENV", "sandbox").lower().strip()
            host = {
                "sandbox": plaid.Environment.Sandbox,
                "development": plaid.Environment.Production,
                "production": plaid.Environment.Production,
            }.get(env, plaid.Environment.Sandbox)

            # Use the correct secret for the environment
            if env in ("production", "development"):
                secret = (
                    os.getenv("PLAID_PRODUCTION_SECRET")
                    or os.getenv("PLAID_SECRET")
                )
            else:
                secret = os.getenv("PLAID_SECRET")

            if not secret:
                logger.warning(
                    "Plaid credentials not configured — bank syncing disabled. "
                    "Add PLAID_SECRET to ~/BudgetApp/.env to enable."
                )
                return None

            configuration = plaid.Configuration(
                host=host,
                api_key={
                    "clientId": os.getenv("PLAID_CLIENT_ID"),
                    "secret": secret,
                },
            )
            api_client = plaid.ApiClient(configuration)
            self._client = plaid_api.PlaidApi(api_client)
        return self._client

    def _require_client(self):
        """Raise a clear error if Plaid is not configured."""
        if not self.client:
            raise ValueError(
                "Plaid is not configured. Add your PLAID_CLIENT_ID and "
                "PLAID_SECRET to ~/BudgetApp/.env to enable bank syncing."
            )
```

The **graceful degradation** here is important. Instead of crashing the entire app when Plaid credentials are missing, the `client` property returns `None` and logs a warning. Any method that actually needs Plaid calls `_require_client()` first, which raises a clear error message. This means the app starts fine without Plaid credentials — CSV import, categorization, budgets, and everything else still works.

Notice the environment handling: Plaid has three environments (sandbox, development, production), each with different API endpoints and secrets. The service automatically picks the right secret based on the configured environment. Development and production share a secret naming convention where the production secret takes priority.

### Token Encryption

Plaid access tokens grant full access to a user's bank data — they can fetch transactions, balances, and account details. Storing them in plaintext in the database would be a serious security risk. If someone got a copy of your database file, they could access your bank.

We solve this with Fernet symmetric encryption from Python's `cryptography` library:

```python
@property
def fernet(self) -> Fernet:
    """Lazy-init Fernet encryption. Persists key to ~/BudgetApp/.encryption_key."""
    if self._fernet is None:
        from pathlib import Path

        key = os.getenv("PLAID_TOKEN_ENCRYPTION_KEY")

        # If not in env, try the persistent key file
        key_file = Path.home() / "BudgetApp" / ".encryption_key"
        if not key and key_file.exists():
            key = key_file.read_text().strip()

        # Generate new key and persist it
        if not key:
            key = Fernet.generate_key().decode()
            key_file.parent.mkdir(exist_ok=True)
            key_file.write_text(key)
            key_file.chmod(0o600)  # Owner-only read/write
            logger.warning(
                "Generated new encryption key — saved to %s. "
                "Existing Plaid tokens (if any) will need to be re-linked.",
                key_file,
            )

        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return self._fernet

def encrypt_token(self, token: str) -> str:
    """Encrypt a Plaid access token for storage."""
    return self.fernet.encrypt(token.encode()).decode()

def decrypt_token(self, encrypted: str) -> str:
    """Decrypt a stored Plaid access token."""
    try:
        return self.fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        raise ValueError(
            "Cannot decrypt Plaid token — encryption key has changed. "
            "Please disconnect and re-link this account."
        )
```

The encryption key is loaded from three places in priority order:

1. **Environment variable** (`PLAID_TOKEN_ENCRYPTION_KEY`) — useful for CI/CD or explicit configuration
2. **Persistent key file** (`~/BudgetApp/.encryption_key`) — the default for most users
3. **Auto-generated** — if no key exists anywhere, one is created and saved to the key file

The key file gets `chmod 0o600` (owner read/write only), matching the convention for SSH keys and other sensitive files. If the key is ever lost or changed, existing tokens can't be decrypted — the user needs to disconnect and re-link their bank accounts. The `decrypt_token` method catches this and gives a clear error message.

### Link Token Creation

The Plaid Link widget needs a temporary token to start. This token is short-lived and tied to a specific user and set of Plaid products:

```python
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions

def create_link_token(self, account_id: int, redirect_uri: Optional[str] = None) -> str:
    """Create a link_token for the Plaid Link widget."""
    self._require_client()
    kwargs = dict(
        products=[Products("transactions")],
        client_name="Budget App",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(
            client_user_id=str(account_id),
        ),
        transactions=LinkTokenTransactions(
            days_requested=730,  # Max: 2 years of historical data
        ),
    )

    if redirect_uri:
        kwargs["redirect_uri"] = redirect_uri

    request = LinkTokenCreateRequest(**kwargs)
    response = self.client.link_token_create(request)
    return response["link_token"]
```

The `days_requested=730` parameter tells Plaid we want up to 2 years of historical transactions on the initial sync. Without this, Plaid defaults to 90 days.

The `redirect_uri` parameter is needed for OAuth-based banks (like Chase and Wells Fargo). These banks redirect the user to their own website for login instead of using Plaid's in-widget form. The redirect URI tells Plaid where to send the user back after they log in. This must match a URI configured in your Plaid dashboard.

### Token Exchange and Account Linking

After the user completes the Plaid Link widget, the frontend sends a temporary `public_token` to the backend. The backend exchanges it for a permanent `access_token`:

```python
def exchange_public_token(self, public_token: str, account, db: Session):
    """Exchange a public_token from Plaid Link for an access_token."""
    self._require_client()

    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = self.client.item_public_token_exchange(request)

    access_token = response["access_token"]
    item_id = response["item_id"]
    encrypted_token = self.encrypt_token(access_token)

    # Fetch Plaid accounts to match by type
    plaid_accounts = []
    try:
        balance_req = AccountsBalanceGetRequest(access_token=access_token)
        balance_resp = self.client.accounts_balance_get(balance_req)
        plaid_accounts = balance_resp["accounts"]
    except Exception as e:
        logger.warning(f"Could not fetch initial balances: {e}")

    # Link the primary account
    account.plaid_access_token = encrypted_token
    account.plaid_item_id = item_id
    account.plaid_connection_status = "connected"
```

After getting the access token, the service does something clever — it automatically links sibling accounts at the same institution:

```python
    # Auto-link sibling accounts at the same institution
    siblings_linked = []
    if plaid_accounts and account.institution:
        siblings = (
            db.query(Account)
            .filter(Account.institution == account.institution)
            .filter(Account.id != account.id)
            .filter(Account.plaid_connection_status != "connected")
            .all()
        )
        for sibling in siblings:
            matched_sibling = self._match_plaid_account(sibling, plaid_accounts)
            if matched_sibling:
                if matched_sibling["account_id"] != account.plaid_account_id:
                    sibling.plaid_access_token = encrypted_token
                    sibling.plaid_item_id = item_id
                    sibling.plaid_account_id = matched_sibling["account_id"]
                    sibling.plaid_connection_status = "connected"
                    siblings_linked.append(sibling.name)
```

This means that when you log into SoFi (which has both Checking and Savings), connecting one account automatically connects the other. The user doesn't need to go through the Plaid Link flow twice for the same bank.

The account matching logic uses the account type as the primary signal — it maps our types ("checking", "savings", "credit") to Plaid's types ("depository", "credit") and subtypes ("checking", "savings", "credit card"):

```python
def _match_plaid_account(self, account, plaid_accounts):
    """Match our Account to the right Plaid account by type."""
    type_map = {
        "checking": "depository",
        "savings": "depository",
        "credit": "credit",
    }
    subtype_map = {
        "checking": "checking",
        "savings": "savings",
        "credit": "credit card",
    }

    expected_type = type_map.get(account.account_type)
    expected_subtype = subtype_map.get(account.account_type)

    # First pass: match both type AND subtype
    for pa in plaid_accounts:
        if (str(pa.get("type")) == expected_type and
                str(pa.get("subtype")) == expected_subtype):
            return pa

    # Second pass: match just type
    for pa in plaid_accounts:
        if str(pa.get("type")) == expected_type:
            return pa

    # Fallback: first account
    return plaid_accounts[0] if plaid_accounts else None
```

---

## 3.3 Transaction Sync — The Heart of the Service

This is the most complex method in the entire app. It handles incremental syncing, deduplication across multiple sources, pending-to-posted transitions, and automatic categorization.

### Cursor-Based Pagination

Plaid's transaction sync API uses cursors instead of date ranges. You pass your last cursor, and Plaid returns everything that's changed since then — new transactions, modified transactions, and removed transactions. This is much more efficient than re-downloading everything each time.

```python
def sync_transactions(self, account, db, _retry_count=0, trigger="manual"):
    """Cursor-based transaction sync for one account."""
    self._require_client()
    from ..models import Transaction, SyncLog
    from .categorize import categorize_transaction

    sync_start = time.time()
    access_token = self.decrypt_token(account.plaid_access_token)
    cursor = account.plaid_cursor or ""

    added_count = 0
    modified_count = 0
    removed_count = 0
    has_more = True

    while has_more:
        request = TransactionsSyncRequest(
            access_token=access_token,
            cursor=cursor,
            options=TransactionsSyncRequestOptions(
                include_original_description=True,
                account_id=account.plaid_account_id,
            ),
        )

        try:
            response = self.client.transactions_sync(request)
        except plaid.ApiException as e:
            # Handle mutation-during-pagination by resetting cursor
            if "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION" in str(e.body):
                if _retry_count < 3:
                    account.plaid_cursor = ""
                    db.commit()
                    return self.sync_transactions(
                        account, db, _retry_count=_retry_count + 1, trigger="retry"
                    )
            raise

        # Process added, modified, removed transactions
        for txn_data in response.get("added", []):
            result = self._upsert_transaction(txn_data, account, db, is_new=True)
            if result:
                added_count += result

        for txn_data in response.get("modified", []):
            result = self._upsert_transaction(txn_data, account, db, is_new=False)
            if result:
                modified_count += result

        for removed in response.get("removed", []):
            txn_id = removed.get("transaction_id")
            if txn_id:
                existing = db.query(Transaction).filter(
                    Transaction.plaid_transaction_id == txn_id
                ).first()
                if existing:
                    db.delete(existing)
                    removed_count += 1

        # Save cursor progress after each page
        cursor = response["next_cursor"]
        account.plaid_cursor = cursor
        db.commit()

        has_more = response.get("has_more", False)
```

A few important details here:

**Committing after each page** (not just at the end) serves two purposes. First, it releases the SQLite write lock between pages, so the UI can still read data during a long sync. Second, it saves cursor progress — if the sync fails halfway through, the next attempt picks up where it left off instead of re-downloading everything.

**The mutation retry** handles a specific Plaid error: `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION`. This happens when Plaid's data changes while you're paginating through it. The fix is to reset the cursor and start over. We retry up to 3 times before giving up.

**The `include_original_description` option** tells Plaid to include the raw bank description alongside its cleaned-up name. We prefer the raw description because it's what the categorization engine trains on — bank-specific formats like "STARBUCKS #12345 SAN FRANCISCO CA" contain patterns that help with matching.

**The `account_id` filter** tells Plaid to only return transactions for one specific account. Without this, a single Plaid item (bank login) would return transactions for all accounts at that bank, and we'd need to sort them ourselves.

### The Upsert Logic

The `_upsert_transaction` method handles the tricky part — figuring out whether a Plaid transaction is new, a duplicate, or an update to something we already have:

```python
def _upsert_transaction(self, txn_data, account, db, is_new):
    """Insert or update a single Plaid transaction."""
    from ..models import Transaction
    from .categorize import categorize_transaction

    plaid_txn_id = txn_data.get("transaction_id")

    # Skip transactions belonging to a different account
    txn_plaid_account_id = txn_data.get("account_id")
    if account.plaid_account_id and txn_plaid_account_id:
        if txn_plaid_account_id != account.plaid_account_id:
            return 0

    # Parse transaction data
    txn_date = txn_data.get("date")
    original_desc = txn_data.get("original_description")
    plaid_name = txn_data.get("name", "")
    description = original_desc or plaid_name
    merchant_name = txn_data.get("merchant_name") or plaid_name
    amount = float(txn_data.get("amount", 0))
```

The method checks for matches in four layers, in priority order:

**Layer 1 — Existing Plaid transaction** (same `transaction_id`): Update amount, date, and pending status. Never overwrite user-confirmed categories.

**Layer 2 — Pending-to-posted transition**: When a pending transaction clears, Plaid sends it as a new transaction with a `pending_transaction_id` pointing to the old pending record. We find the old record and upgrade it.

**Layer 3 — Cross-source dedup** (Plaid vs archive import): If you imported historical data from CSV and then connected Plaid, the same transaction would exist twice. We match by account + date (±2 days) + amount and merge them, keeping the existing category assignment.

**Layer 4 — Same-account dedup**: After a cursor reset, Plaid may re-send transactions we already have under different transaction IDs. We catch these by matching on account + date + amount.

**Layer 5 — Brand new transaction**: No match found anywhere. Create a new record and run it through the categorization engine.

This layered dedup approach means the app handles all sorts of real-world scenarios: pending transactions that clear days later, CSV-imported data that overlaps with Plaid data, and cursor resets that re-send old transactions.

### Protecting User Decisions

Throughout the upsert logic, there's a consistent pattern:

```python
if existing.status not in ("confirmed", "pending_save"):
    existing.description = description
    existing.merchant_name = merchant_name
```

This check appears everywhere a Plaid update might overwrite existing data. If the user has confirmed a category or staged a change, we never overwrite their description or merchant name. This preserves manual edits — if you renamed "STARBUCKS #12345 SAN FRANCISCO CA" to "Coffee with Mom," that edit survives future syncs.

---

## 3.4 Balance Fetching

Separately from transaction syncing, the service can fetch current account balances:

```python
def get_account_balances(self, account, db):
    """Fetch current balances from Plaid and store on the Account."""
    access_token = self.decrypt_token(account.plaid_access_token)

    request = AccountsBalanceGetRequest(access_token=access_token)
    response = self.client.accounts_balance_get(request)

    for pa in response["accounts"]:
        if pa["account_id"] == account.plaid_account_id:
            account.balance_current = pa["balances"]["current"]
            account.balance_available = pa["balances"].get("available")
            account.balance_limit = pa["balances"].get("limit")
            account.balance_updated_at = datetime.utcnow()
            break

    db.commit()
```

This is a separate API call from transaction sync because balances can change independently (e.g., a direct deposit hitting your account before the transaction appears). The Accounts page has a "Refresh Balances" button that calls this directly.

---

## 3.5 Investment Syncing

The service also handles investment accounts — brokerage accounts, IRAs, 401(k)s. This uses a different Plaid product (`investments` instead of `transactions`) and stores data in the separate investments database.

### Holdings Sync

```python
def sync_investment_holdings(self, access_token_encrypted, inv_account, inv_db):
    """Fetch holdings + securities from Plaid and upsert into investments DB."""
    self._require_client()
    from ..models_investments import Security, Holding

    access_token = self.decrypt_token(access_token_encrypted)
    request = InvestmentsHoldingsGetRequest(access_token=access_token)
    response = self.client.investments_holdings_get(request)

    today = date.today()

    # 1. Upsert securities (stocks, ETFs, mutual funds)
    security_map = {}
    for ps in response.get("securities", []):
        plaid_sec_id = ps.get("security_id")
        existing = inv_db.query(Security).filter(
            Security.plaid_security_id == plaid_sec_id
        ).first()

        if existing:
            # Update price and name
            existing.name = ps.get("name") or existing.name
            if ps.get("close_price") is not None:
                existing.close_price = float(ps["close_price"])
                existing.close_price_as_of = datetime.utcnow()
                existing.price_source = "plaid"
            security_map[plaid_sec_id] = existing
        else:
            # Create new security record
            sec = Security(
                plaid_security_id=plaid_sec_id,
                ticker=ps.get("ticker_symbol"),
                name=ps.get("name") or ps.get("ticker_symbol") or "Unknown",
                security_type=str(ps.get("type", "")).lower() or "stock",
                close_price=float(ps["close_price"]) if ps.get("close_price") else None,
                close_price_as_of=datetime.utcnow() if ps.get("close_price") else None,
                price_source="plaid" if ps.get("close_price") else None,
            )
            inv_db.add(sec)
            inv_db.flush()
            security_map[plaid_sec_id] = sec

    # 2. Upsert holdings (daily snapshot)
    for ph in response.get("holdings", []):
        # Filter to this account
        if inv_account.plaid_account_id and ph.get("account_id") != inv_account.plaid_account_id:
            continue

        security = security_map.get(ph.get("security_id"))
        if not security:
            continue

        # Upsert today's snapshot
        existing = inv_db.query(Holding).filter(
            Holding.investment_account_id == inv_account.id,
            Holding.security_id == security.id,
            Holding.as_of_date == today,
        ).first()

        quantity = float(ph.get("quantity", 0))
        cost_basis = float(ph["cost_basis"]) if ph.get("cost_basis") else None

        if existing:
            existing.quantity = quantity
            existing.cost_basis = cost_basis
            existing.current_value = float(ph["institution_value"]) if ph.get("institution_value") else None
        else:
            holding = Holding(
                investment_account_id=inv_account.id,
                security_id=security.id,
                quantity=quantity,
                cost_basis=cost_basis,
                cost_basis_per_unit=cost_basis / quantity if cost_basis and quantity > 0 else None,
                current_value=float(ph["institution_value"]) if ph.get("institution_value") else None,
                as_of_date=today,
            )
            inv_db.add(holding)

    inv_db.commit()
```

The holding sync creates daily snapshots — one row per security per account per day. This accumulation of snapshots over time enables portfolio performance charts.

### Investment Transactions Sync

Investment transactions (buys, sells, dividends, transfers) use offset-based pagination instead of cursors:

```python
def sync_investment_transactions(self, access_token_encrypted, inv_account, inv_db,
                                  start_date=None, end_date=None):
    """Fetch investment transactions from Plaid."""
    # Defaults to 2 years of history
    if not start_date:
        start_date = date.today() - timedelta(days=730)
    if not end_date:
        end_date = date.today()

    offset = 0
    while True:
        request = InvestmentsTransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options={"offset": offset, "count": 100},
        )
        response = self.client.investments_transactions_get(request)

        for txn_data in response.get("investment_transactions", []):
            # Dedup by plaid_investment_transaction_id
            # Map Plaid subtypes to simpler types (buy, sell, dividend, etc.)
            # Create InvestmentTransaction records
            ...

        offset += len(response.get("investment_transactions", []))
        if offset >= response.get("total_investment_transactions", 0):
            break

    inv_db.commit()
```

The service maps Plaid's granular subtypes (like "qualified dividend", "non-qualified dividend", "dividend reinvestment") to simpler categories that make sense for display: `buy`, `sell`, `dividend`, `dividend_reinvestment`, `capital_gain`, `transfer`, and `fee`.

---

## 3.6 The Accounts API (`backend/routers/accounts.py`)

The accounts router exposes all account management as REST endpoints. Let's walk through the key ones.

### Listing Accounts

```python
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
```

This endpoint gathers date range statistics in a single SQL query using `GROUP BY` instead of querying per-account. This is an important optimization — if you have 4 accounts with thousands of transactions each, you don't want 4 separate count queries.

### The Plaid Link Flow

Two endpoints handle the frontend widget:

```python
@router.post("/link/token")
def create_link_token(req: LinkTokenRequest, db: Session = Depends(get_db)):
    """Create a Plaid Link token for the frontend widget."""
    from ..services.plaid_service import plaid_service

    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    link_token = plaid_service.create_link_token(
        account.id, redirect_uri=req.redirect_uri
    )
    return {"link_token": link_token}


@router.post("/link/exchange")
def exchange_public_token(req: LinkExchangeRequest, db: Session = Depends(get_db)):
    """Exchange the public_token from Plaid Link for an access_token."""
    from ..services.plaid_service import plaid_service

    account = db.query(Account).get(req.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

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
            except Exception:
                pass

    return result
```

The exchange endpoint does three things in sequence: exchanges the token, triggers an initial sync for the primary account, and syncs any sibling accounts that were auto-linked. This means the user connects their bank and immediately sees their transactions — no waiting for the next scheduled sync.

### Manual Sync and Sync-All

```python
@router.post("/{account_id}/sync", response_model=SyncResult)
def sync_account(account_id: int, db: Session = Depends(get_db)):
    """Manually trigger a transaction sync for one account."""
    from ..services.plaid_service import plaid_service

    account = db.query(Account).get(account_id)
    if not account or account.plaid_connection_status != "connected":
        raise HTTPException(status_code=400, detail="Account not connected")

    result = plaid_service.sync_transactions(account, db, trigger="manual")
    return result


@router.post("/sync-all")
def sync_all_accounts(db: Session = Depends(get_db)):
    """Sync all connected accounts. Used by the scheduler and 'Sync All' button."""
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
```

### Sync History

```python
# NOTE: Literal paths (/sync-history) MUST be defined before
#       parameterised paths (/{account_id}) so FastAPI matches them first.

@router.get("/sync-history")
def get_sync_history(account_id: int = None, limit: int = 50, db: Session = Depends(get_db)):
    """Return recent sync log entries for all or a specific account."""
    from ..models import SyncLog

    query = db.query(SyncLog).order_by(SyncLog.started_at.desc())
    if account_id:
        query = query.filter(SyncLog.account_id == account_id)
    return query.limit(limit).all()
```

The comment about route ordering is a real gotcha in FastAPI. If `/{account_id}` is defined before `/sync-history`, FastAPI will try to parse `"sync-history"` as an integer and return a 422 error. Literal path segments must always come before parameterized ones.

### Disconnect and Delete

```python
@router.post("/{account_id}/disconnect")
def disconnect_account(account_id: int, db: Session = Depends(get_db)):
    """Disconnect a Plaid-linked account. Preserves all transaction data."""
    account = db.query(Account).get(account_id)
    account.plaid_access_token = None
    account.plaid_item_id = None
    account.plaid_cursor = None
    account.plaid_account_id = None
    account.plaid_connection_status = "disconnected"
    # Clear balance data too
    account.balance_current = None
    account.balance_available = None
    account.balance_limit = None
    db.commit()
    return {"status": "disconnected"}


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Permanently remove an account and all its transactions."""
    from ..models import SyncLog

    account = db.query(Account).get(account_id)
    txn_count = db.query(Transaction).filter(Transaction.account_id == account_id).delete()
    log_count = db.query(SyncLog).filter(SyncLog.account_id == account_id).delete()
    db.delete(account)
    db.commit()
    return {"status": "deleted", "transactions_removed": txn_count}
```

Disconnect preserves all transaction data but removes the Plaid connection — useful if your bank credentials expire and you want to re-link without losing history. Delete is permanent — it removes the account and all associated transactions and sync logs.

---

## 3.7 The Background Scheduler (`backend/services/sync_scheduler.py`)

The scheduler keeps your data fresh automatically using APScheduler. It runs three background jobs:

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()

def start_scheduler():
    """Start the background sync scheduler."""
    if scheduler.running:
        return

    # Bank transaction sync — every 4 hours
    scheduler.add_job(
        sync_all_accounts_job,
        trigger=IntervalTrigger(hours=4),
        id="plaid_sync_all",
        replace_existing=True,
    )

    # Investment holdings + transactions — every 6 hours
    scheduler.add_job(
        sync_investments_job,
        trigger=IntervalTrigger(hours=6),
        id="investment_sync",
        replace_existing=True,
    )

    # Stock price refresh — every 30 minutes during market hours
    scheduler.add_job(
        fetch_prices_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="9-16",
            minute="0,30",
            timezone="US/Eastern",
        ),
        id="price_refresh",
        replace_existing=True,
    )

    scheduler.start()
```

**Transaction sync every 4 hours** balances freshness with API rate limits. Plaid's sandbox doesn't have rate limits, but production does — 4 hours is a safe interval.

**Investment sync every 6 hours** is less frequent because portfolio positions change less often than bank transactions.

**Price refresh every 30 minutes during market hours** uses a cron trigger that only fires on weekdays between 9:30 AM and 4:30 PM Eastern. This uses Yahoo Finance (`yfinance`) to get real-time stock prices — covered in Part 6.

Each job wraps its Plaid calls in try/except so that a failure for one account doesn't stop the sync for other accounts, and a missing-credentials error doesn't crash the scheduler:

```python
def sync_all_accounts_job():
    """Background job: sync all connected bank accounts."""
    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(
            Account.plaid_connection_status == "connected"
        ).all()

        for account in accounts:
            try:
                result = plaid_service.sync_transactions(account, db, trigger="scheduled")
            except Exception as e:
                logger.error(f"  {account.name}: sync failed — {e}")
    finally:
        db.close()
```

---

## 3.8 OAuth Callback Handling

Some banks (Chase, Wells Fargo, and others) use OAuth for authentication. Instead of entering credentials inside the Plaid widget, the user is redirected to the bank's website. After logging in, the bank redirects back to your app.

The frontend handles this with a dedicated route at `/oauth-callback`:

```jsx
// In frontend/src/App.jsx

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

The flow is: before opening the Plaid Link widget for an OAuth bank, the frontend stores the `link_token` and `account_id` in `sessionStorage`. When the bank redirects back to `/oauth-callback`, this component retrieves those stored values and completes the exchange. The `receivedRedirectUri: window.location.href` tells the Plaid SDK that this is a redirect completion, not a new link session.

---

## 3.9 Graceful Degradation

The entire Plaid integration is designed so that a missing configuration doesn't break anything. Here's the chain:

1. **No credentials** → `plaid_service.client` returns `None` → logs a warning, doesn't crash
2. **Scheduler runs** → no connected accounts → `sync_all_accounts_job` returns immediately
3. **User clicks Connect** → `_require_client()` raises `ValueError` → frontend shows a helpful error message
4. **AI categorization unavailable** → Tiers 1 and 2 still work → transaction goes to review queue
5. **CSV import** → works independently of Plaid → full categorization still runs

The Settings page (Part 5) provides a UI for entering Plaid credentials. Once saved, they're loaded into the environment on the next restart, and bank syncing becomes available.

---

## What's Next

With bank accounts connected and transactions flowing in, Part 4 covers the categorization engine — the three tiers of automatic categorization, how the review queue works, CSV import, and how the system learns from your confirmations.

→ [Part 4: Transaction Processing & Categorization](04-categorization-engine.md)
