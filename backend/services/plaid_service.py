"""
Plaid API Service

Handles all Plaid interactions:
- Link token creation for the frontend widget
- Public token → access token exchange
- Cursor-based transaction sync
- Balance fetching
- Token encryption at rest (Fernet)
"""

import os
import logging
from datetime import datetime, date
from typing import Optional

import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.transactions_sync_request_options import TransactionsSyncRequestOptions
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.investments_transactions_get_request import InvestmentsTransactionsGetRequest

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class PlaidService:
    """Wraps the Plaid API client with encryption and business logic."""

    def __init__(self):
        self._client: Optional[plaid_api.PlaidApi] = None
        self._fernet: Optional[Fernet] = None

    # ── Client Initialization ──

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

            logger.info(f"Initializing Plaid client for '{env}' environment")

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
                logger.info("Loaded encryption key from %s", key_file)

            # Generate new key and persist it
            if not key:
                key = Fernet.generate_key().decode()
                key_file.parent.mkdir(exist_ok=True)
                key_file.write_text(key)
                key_file.chmod(0o600)
                logger.warning(
                    "Generated new encryption key — saved to %s. "
                    "Existing Plaid tokens (if any) will need to be re-linked.",
                    key_file,
                )

            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        return self._fernet

    # ── Token Encryption ──

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

    # ── Link Token (for frontend Plaid Link widget) ──

    def create_link_token(
        self, account_id: int, redirect_uri: Optional[str] = None
    ) -> str:
        """
        Create a link_token for the Plaid Link widget.
        The account_id is used as a client_user_id for tracking.

        redirect_uri is required for OAuth institutions (e.g. Wells Fargo)
        in production. Must match an allowed URI in Plaid dashboard.
        """
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

        # Include redirect_uri for OAuth banks (required in production)
        if redirect_uri:
            kwargs["redirect_uri"] = redirect_uri

        request = LinkTokenCreateRequest(**kwargs)
        response = self.client.link_token_create(request)
        return response["link_token"]

    # ── Token Exchange ──

    def exchange_public_token(self, public_token: str, account, db: Session):
        """
        Exchange a public_token from Plaid Link for an access_token.
        Encrypts and stores the token on the Account model.

        Also detects sibling accounts at the same institution and links
        them to the same Plaid item (e.g. SoFi checking + savings).
        """
        self._require_client()
        from ..models import Account

        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = self.client.item_public_token_exchange(request)

        access_token = response["access_token"]
        item_id = response["item_id"]
        encrypted_token = self.encrypt_token(access_token)

        # Fetch Plaid accounts to match by type/subtype
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
        account.last_sync_error = None

        if plaid_accounts:
            matched = self._match_plaid_account(account, plaid_accounts)
            if matched:
                account.plaid_account_id = matched["account_id"]
                account.balance_current = matched["balances"]["current"]
                account.balance_available = matched["balances"].get("available")
                account.balance_limit = matched["balances"].get("limit")
                account.balance_updated_at = datetime.utcnow()

        # Auto-link sibling accounts at the same institution
        # (e.g. linking SoFi checking also links SoFi savings)
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
                    # Make sure this Plaid account isn't already assigned
                    if matched_sibling["account_id"] != account.plaid_account_id:
                        sibling.plaid_access_token = encrypted_token
                        sibling.plaid_item_id = item_id
                        sibling.plaid_account_id = matched_sibling["account_id"]
                        sibling.plaid_connection_status = "connected"
                        sibling.last_sync_error = None
                        sibling.balance_current = matched_sibling["balances"]["current"]
                        sibling.balance_available = matched_sibling["balances"].get("available")
                        sibling.balance_limit = matched_sibling["balances"].get("limit")
                        sibling.balance_updated_at = datetime.utcnow()
                        siblings_linked.append(sibling.name)
                        logger.info(
                            f"Auto-linked sibling {sibling.name} "
                            f"(plaid_account_id={matched_sibling['account_id']})"
                        )

        db.commit()
        logger.info(f"Account {account.name} linked to Plaid item {item_id}")
        if siblings_linked:
            logger.info(f"Also linked siblings: {', '.join(siblings_linked)}")

        return {
            "item_id": item_id,
            "status": "connected",
            "siblings_linked": siblings_linked,
        }

    def _match_plaid_account(self, account, plaid_accounts):
        """
        Try to match our Account to the right Plaid account.
        Uses account type as the primary signal.
        """
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

        # First pass: match both type and subtype
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

    # ── Transaction Sync ──

    def sync_transactions(self, account, db: Session, _retry_count: int = 0, trigger: str = "manual") -> dict:
        """
        Cursor-based transaction sync for one account.
        Deduplicates by plaid_transaction_id, runs categorization on new ones.

        Handles TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION by resetting the
        cursor and retrying (up to 3 times).

        Returns: {"added": int, "modified": int, "removed": int}
        """
        self._require_client()
        import time as _time
        from ..models import Transaction, SyncLog
        from .categorize import categorize_transaction

        MAX_MUTATION_RETRIES = 3
        sync_start = _time.time()

        if not account.plaid_access_token:
            raise ValueError(f"Account {account.name} has no Plaid access token")

        access_token = self.decrypt_token(account.plaid_access_token)
        cursor = account.plaid_cursor or ""

        added_count = 0
        modified_count = 0
        removed_count = 0
        skipped_account = 0
        has_more = True
        page = 0

        logger.info(
            f"Starting sync for {account.name} "
            f"(plaid_account_id={account.plaid_account_id}, cursor={'<empty>' if not cursor else cursor[:20] + '...'})"
        )

        while has_more:
            page += 1
            # Build options: include raw bank descriptions and filter by account
            sync_options = TransactionsSyncRequestOptions(
                include_original_description=True,
            )
            if account.plaid_account_id:
                sync_options = TransactionsSyncRequestOptions(
                    include_original_description=True,
                    account_id=account.plaid_account_id,
                )

            request = TransactionsSyncRequest(
                access_token=access_token,
                cursor=cursor,
                options=sync_options,
            )

            try:
                response = self.client.transactions_sync(request)
            except plaid.ApiException as e:
                error_body = e.body if hasattr(e, "body") else str(e)
                error_str = str(error_body)

                # Handle mutation-during-pagination: reset cursor and retry
                if "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION" in error_str:
                    if _retry_count < MAX_MUTATION_RETRIES:
                        logger.warning(
                            f"Mutation during pagination for {account.name} "
                            f"(attempt {_retry_count + 1}/{MAX_MUTATION_RETRIES}). "
                            f"Resetting cursor and retrying..."
                        )
                        # Reset cursor to empty to restart from scratch
                        account.plaid_cursor = ""
                        db.commit()
                        return self.sync_transactions(account, db, _retry_count=_retry_count + 1, trigger="retry")
                    else:
                        logger.error(
                            f"Mutation during pagination for {account.name} — "
                            f"exhausted {MAX_MUTATION_RETRIES} retries"
                        )

                account.last_sync_error = error_str[:500]
                if "ITEM_LOGIN_REQUIRED" in error_str:
                    account.plaid_connection_status = "item_login_required"

                # Log the failed sync
                sync_log = SyncLog(
                    account_id=account.id,
                    trigger=trigger if _retry_count == 0 else "retry",
                    status="error",
                    added=added_count,
                    modified=modified_count,
                    removed=removed_count,
                    error_message=error_str[:500],
                    duration_seconds=round(_time.time() - sync_start, 2),
                )
                db.add(sync_log)
                db.commit()
                logger.error(f"Plaid sync error for {account.name}: {error_body}")
                raise

            raw_added = response.get("added", [])
            raw_modified = response.get("modified", [])
            raw_removed = response.get("removed", [])

            logger.info(
                f"  Page {page}: {len(raw_added)} added, "
                f"{len(raw_modified)} modified, {len(raw_removed)} removed, "
                f"has_more={response.get('has_more', False)}"
            )

            # Process added transactions
            for txn_data in raw_added:
                result = self._upsert_transaction(
                    txn_data, account, db, is_new=True
                )
                if result:
                    added_count += result
                else:
                    skipped_account += 1

            # Process modified transactions
            for txn_data in raw_modified:
                result = self._upsert_transaction(
                    txn_data, account, db, is_new=False
                )
                if result:
                    modified_count += result
                else:
                    skipped_account += 1

            # Process removed transactions
            for removed in raw_removed:
                txn_id = removed.get("transaction_id")
                if txn_id:
                    existing = db.query(Transaction).filter(
                        Transaction.plaid_transaction_id == txn_id
                    ).first()
                    if existing:
                        db.delete(existing)
                        removed_count += 1

            # Commit each page to release the SQLite write lock
            # and save cursor progress (so we can resume on failure)
            cursor = response["next_cursor"]
            account.plaid_cursor = cursor
            db.commit()

            has_more = response.get("has_more", False)

        # Update account state
        account.last_synced_at = datetime.utcnow()
        account.last_sync_error = None

        # Log the successful sync
        sync_log = SyncLog(
            account_id=account.id,
            trigger=trigger if _retry_count == 0 else "retry",
            status="success",
            added=added_count,
            modified=modified_count,
            removed=removed_count,
            duration_seconds=round(_time.time() - sync_start, 2),
        )
        db.add(sync_log)
        db.commit()

        logger.info(
            f"Synced {account.name}: +{added_count} ~{modified_count} "
            f"-{removed_count} (skipped {skipped_account} for other accounts)"
        )
        return {
            "added": added_count,
            "modified": modified_count,
            "removed": removed_count,
        }

    def _upsert_transaction(self, txn_data, account, db: Session, is_new: bool) -> int:
        """
        Insert or update a single Plaid transaction.
        Returns 1 if a record was created/updated, 0 if skipped.

        Features:
        - Filters by plaid_account_id (multi-account institutions)
        - Uses original_description as primary description field
        - Handles pending→posted transition via pending_transaction_id
        - Cross-source dedup: merges with archive_import if same date+amount+account
        """
        from ..models import Transaction
        from .categorize import categorize_transaction
        from datetime import timedelta

        plaid_txn_id = txn_data.get("transaction_id")
        if not plaid_txn_id:
            return 0

        # Skip transactions belonging to a different Plaid account
        # (e.g. savings txns when syncing the checking account)
        txn_plaid_account_id = txn_data.get("account_id")
        if account.plaid_account_id and txn_plaid_account_id:
            if txn_plaid_account_id != account.plaid_account_id:
                return 0

        # Parse Plaid transaction data
        txn_date = txn_data.get("date")
        if isinstance(txn_date, str):
            txn_date = date.fromisoformat(txn_date)

        # Use original_description (raw bank text) as primary,
        # fall back to Plaid's cleaned name
        original_desc = txn_data.get("original_description")
        plaid_name = txn_data.get("name", "")
        description = original_desc or plaid_name
        merchant_name = txn_data.get("merchant_name") or plaid_name

        # Plaid: positive = money leaving account (expense), negative = income
        amount = float(txn_data.get("amount", 0))
        is_pending = txn_data.get("pending", False)

        # ── 1. Check for existing Plaid transaction (same transaction_id) ──
        existing = db.query(Transaction).filter(
            Transaction.plaid_transaction_id == plaid_txn_id
        ).first()

        if existing:
            # Update existing transaction (e.g. amount/date changed)
            # but NEVER overwrite user-confirmed categories
            existing.date = txn_date
            existing.amount = amount
            existing.is_pending = is_pending
            # Only update description/merchant if user hasn't confirmed
            # (preserves any manual edits on confirmed transactions)
            if existing.status not in ("confirmed", "pending_save"):
                existing.description = description
                existing.merchant_name = merchant_name
            db.flush()
            return 1

        # ── 2. Pending→posted transition ──
        # When a pending transaction posts, Plaid sends it as a new txn
        # with pending_transaction_id pointing to the old pending record.
        pending_txn_id = txn_data.get("pending_transaction_id")
        if pending_txn_id:
            pending_match = db.query(Transaction).filter(
                Transaction.plaid_transaction_id == pending_txn_id
            ).first()
            if pending_match:
                # Upgrade the pending record to posted
                # Preserve user-confirmed category
                pending_match.plaid_transaction_id = plaid_txn_id
                pending_match.date = txn_date
                pending_match.amount = amount
                pending_match.is_pending = False
                if pending_match.status not in ("confirmed", "pending_save"):
                    pending_match.description = description
                    pending_match.merchant_name = merchant_name
                db.flush()
                return 1

        # ── 3. Cross-source dedup (Plaid vs archive_import) ──
        # Look for an archive-imported transaction with same account, date
        # (±2 days tolerance), and amount that doesn't already have a Plaid ID.
        archive_match = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == account.id,
                Transaction.source == "archive_import",
                Transaction.plaid_transaction_id.is_(None),
                Transaction.amount == amount,
                Transaction.date >= txn_date - timedelta(days=2),
                Transaction.date <= txn_date + timedelta(days=2),
            )
            .first()
        )
        if archive_match:
            # Merge: link archive record to Plaid, update fields
            archive_match.plaid_transaction_id = plaid_txn_id
            archive_match.date = txn_date
            archive_match.is_pending = is_pending
            # Preserve category and description on confirmed transactions
            if archive_match.status not in ("confirmed", "pending_save"):
                archive_match.merchant_name = merchant_name
                if original_desc:
                    archive_match.description = description
            else:
                # Still update merchant_name if not set
                if not archive_match.merchant_name:
                    archive_match.merchant_name = merchant_name
            # Keep existing category assignment from archive
            logger.info(
                f"  Merged Plaid txn with archive: {description[:50]} "
                f"${amount} on {txn_date}"
            )
            db.flush()
            return 1

        # ── 4. Dedup check: same account + date + amount already exists? ──
        # After a cursor reset, Plaid may re-send transactions we already have
        # under a different transaction_id. Don't create duplicates.
        dupe_match = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == account.id,
                Transaction.date == txn_date,
                Transaction.amount == amount,
                Transaction.plaid_transaction_id.isnot(None),
            )
            .first()
        )
        if dupe_match:
            # Link the new Plaid ID but preserve everything else
            logger.info(
                f"  Dedup: linking new plaid_txn_id to existing txn "
                f"({dupe_match.plaid_transaction_id} → {plaid_txn_id}): "
                f"{description[:50]} ${amount} on {txn_date}"
            )
            dupe_match.plaid_transaction_id = plaid_txn_id
            if dupe_match.status not in ("confirmed", "pending_save"):
                dupe_match.description = description
                dupe_match.merchant_name = merchant_name
            db.flush()
            return 1

        # ── 5. Brand new transaction — run categorization engine ──
        cat_result = categorize_transaction(description, amount, db, use_ai=True)

        txn = Transaction(
            account_id=account.id,
            plaid_transaction_id=plaid_txn_id,
            date=txn_date,
            description=description,
            merchant_name=merchant_name,
            amount=amount,
            is_pending=is_pending,
            source="plaid_sync",
            categorization_tier=cat_result["tier"],
        )

        # Apply categorization result
        if cat_result["category_id"]:
            if cat_result["status"] == "auto_confirmed":
                txn.category_id = cat_result["category_id"]
                txn.status = "auto_confirmed"
            else:
                txn.predicted_category_id = cat_result["category_id"]
                txn.status = "pending_review"
        else:
            txn.status = "pending_review"

        db.add(txn)
        db.flush()
        return 1

    # ── Balance Fetching ──

    def get_account_balances(self, account, db: Session) -> dict:
        """Fetch current balances from Plaid and store on the Account."""
        if not account.plaid_access_token:
            raise ValueError(f"Account {account.name} has no Plaid access token")

        access_token = self.decrypt_token(account.plaid_access_token)

        request = AccountsBalanceGetRequest(access_token=access_token)
        response = self.client.accounts_balance_get(request)

        plaid_accounts = response["accounts"]
        matched = None

        if account.plaid_account_id:
            # Match by stored Plaid account ID
            for pa in plaid_accounts:
                if pa["account_id"] == account.plaid_account_id:
                    matched = pa
                    break

        if not matched:
            matched = self._match_plaid_account(account, plaid_accounts)

        if matched:
            account.balance_current = matched["balances"]["current"]
            account.balance_available = matched["balances"].get("available")
            account.balance_limit = matched["balances"].get("limit")
            account.balance_updated_at = datetime.utcnow()
            if not account.plaid_account_id:
                account.plaid_account_id = matched["account_id"]
            db.commit()

            return {
                "current": account.balance_current,
                "available": account.balance_available,
                "limit": account.balance_limit,
                "updated_at": account.balance_updated_at.isoformat(),
            }

        raise ValueError("Could not match Plaid account to local account")

    # ── Investment Link Token ──

    def create_link_token_investments(
        self, user_id: int, redirect_uri: Optional[str] = None
    ) -> str:
        """Create a link_token that requests the investments product."""
        self._require_client()
        kwargs = dict(
            products=[Products("investments")],
            client_name="Budget App",
            country_codes=[CountryCode("US")],
            language="en",
            user=LinkTokenCreateRequestUser(
                client_user_id=str(user_id),
            ),
        )
        if redirect_uri:
            kwargs["redirect_uri"] = redirect_uri

        request = LinkTokenCreateRequest(**kwargs)
        response = self.client.link_token_create(request)
        return response["link_token"]

    # ── Investment Holdings Sync ──

    def sync_investment_holdings(self, access_token_encrypted: str, inv_account, inv_db) -> dict:
        """
        Fetch holdings + securities from Plaid and upsert into the investments DB.
        Creates a daily snapshot of each holding.
        Returns: {"securities_upserted": int, "holdings_upserted": int}
        """
        self._require_client()
        from ..models_investments import Security, Holding
        from datetime import date as date_type

        access_token = self.decrypt_token(access_token_encrypted)

        request = InvestmentsHoldingsGetRequest(access_token=access_token)
        response = self.client.investments_holdings_get(request)

        plaid_securities = response.get("securities", [])
        plaid_holdings = response.get("holdings", [])
        plaid_accounts = response.get("accounts", [])

        today = date_type.today()

        # 1. Upsert securities
        security_map = {}  # plaid_security_id -> Security record
        for ps in plaid_securities:
            plaid_sec_id = ps.get("security_id")
            if not plaid_sec_id:
                continue

            existing = inv_db.query(Security).filter(
                Security.plaid_security_id == plaid_sec_id
            ).first()

            ticker = ps.get("ticker_symbol")
            name = ps.get("name") or ticker or "Unknown"
            sec_type = str(ps.get("type", "")).lower().replace(" ", "_") or "stock"
            close_price = ps.get("close_price")
            close_price_date = ps.get("close_price_as_of")

            if existing:
                existing.name = name
                if ticker:
                    existing.ticker = ticker
                existing.security_type = sec_type
                if close_price is not None:
                    existing.close_price = float(close_price)
                    existing.close_price_as_of = datetime.utcnow()
                    existing.price_source = "plaid"
                if ps.get("iso_currency_code"):
                    pass  # All USD for now
                security_map[plaid_sec_id] = existing
            else:
                sec = Security(
                    plaid_security_id=plaid_sec_id,
                    ticker=ticker,
                    name=name,
                    security_type=sec_type,
                    close_price=float(close_price) if close_price else None,
                    close_price_as_of=datetime.utcnow() if close_price else None,
                    price_source="plaid" if close_price else None,
                )
                inv_db.add(sec)
                inv_db.flush()
                security_map[plaid_sec_id] = sec

        # 2. Upsert holdings (daily snapshot)
        holdings_upserted = 0
        for ph in plaid_holdings:
            plaid_sec_id = ph.get("security_id")
            plaid_acct_id = ph.get("account_id")

            # Filter to this account
            if inv_account.plaid_account_id and plaid_acct_id != inv_account.plaid_account_id:
                continue

            security = security_map.get(plaid_sec_id)
            if not security:
                continue

            quantity = float(ph.get("quantity", 0))
            cost_basis = ph.get("cost_basis")
            cost_basis = float(cost_basis) if cost_basis is not None else None
            institution_value = ph.get("institution_value")
            current_value = float(institution_value) if institution_value is not None else None

            cost_per_unit = None
            if cost_basis and quantity > 0:
                cost_per_unit = cost_basis / quantity

            # Upsert for today's snapshot
            existing_holding = inv_db.query(Holding).filter(
                Holding.investment_account_id == inv_account.id,
                Holding.security_id == security.id,
                Holding.as_of_date == today,
            ).first()

            if existing_holding:
                existing_holding.quantity = quantity
                existing_holding.cost_basis = cost_basis
                existing_holding.cost_basis_per_unit = cost_per_unit
                existing_holding.current_value = current_value
            else:
                holding = Holding(
                    investment_account_id=inv_account.id,
                    security_id=security.id,
                    quantity=quantity,
                    cost_basis=cost_basis,
                    cost_basis_per_unit=cost_per_unit,
                    current_value=current_value,
                    as_of_date=today,
                )
                inv_db.add(holding)
            holdings_upserted += 1

        inv_account.last_synced_at = datetime.utcnow()
        inv_account.last_sync_error = None
        inv_db.commit()

        logger.info(
            f"Investment holdings sync: {len(security_map)} securities, "
            f"{holdings_upserted} holdings for {inv_account.account_name}"
        )
        return {
            "securities_upserted": len(security_map),
            "holdings_upserted": holdings_upserted,
        }

    # ── Investment Transactions Sync ──

    def sync_investment_transactions(
        self, access_token_encrypted: str, inv_account, inv_db,
        start_date=None, end_date=None
    ) -> dict:
        """
        Fetch investment transactions (buys, sells, dividends, etc.) from Plaid.
        Deduplicates by plaid_investment_transaction_id.
        Returns: {"added": int, "skipped": int}
        """
        self._require_client()
        from ..models_investments import Security, InvestmentTransaction
        from datetime import timedelta
        from datetime import date as date_type

        access_token = self.decrypt_token(access_token_encrypted)

        if not start_date:
            start_date = date_type.today() - timedelta(days=730)
        if not end_date:
            end_date = date_type.today()

        # Build security lookup
        all_securities = {s.plaid_security_id: s for s in inv_db.query(Security).all()}

        added = 0
        skipped = 0
        offset = 0
        total_count = None

        while True:
            request = InvestmentsTransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options={"offset": offset, "count": 100},
            )

            try:
                response = self.client.investments_transactions_get(request)
            except plaid.ApiException as e:
                error_body = e.body if hasattr(e, "body") else str(e)
                inv_account.last_sync_error = str(error_body)[:500]
                inv_db.commit()
                logger.error(f"Plaid investment txn error: {error_body}")
                raise

            inv_txns = response.get("investment_transactions", [])
            if total_count is None:
                total_count = response.get("total_investment_transactions", 0)

            for txn_data in inv_txns:
                plaid_inv_txn_id = txn_data.get("investment_transaction_id")
                if not plaid_inv_txn_id:
                    continue

                # Skip if already exists
                existing = inv_db.query(InvestmentTransaction).filter(
                    InvestmentTransaction.plaid_investment_transaction_id == plaid_inv_txn_id
                ).first()
                if existing:
                    skipped += 1
                    continue

                # Filter to this account
                plaid_acct_id = txn_data.get("account_id")
                if inv_account.plaid_account_id and plaid_acct_id != inv_account.plaid_account_id:
                    continue

                # Resolve security
                plaid_sec_id = txn_data.get("security_id")
                security = all_securities.get(plaid_sec_id) if plaid_sec_id else None

                txn_date = txn_data.get("date")
                if isinstance(txn_date, str):
                    txn_date = date_type.fromisoformat(txn_date)

                txn_type = str(txn_data.get("type", "")).lower() or "cash"
                subtype = str(txn_data.get("subtype", "")).lower()
                # Map Plaid subtypes to simpler types
                if subtype in ("dividend", "qualified dividend", "non-qualified dividend"):
                    txn_type = "dividend"
                elif subtype == "dividend reinvestment":
                    txn_type = "dividend_reinvestment"
                elif subtype in ("buy", "buy to cover"):
                    txn_type = "buy"
                elif subtype in ("sell", "sell short"):
                    txn_type = "sell"
                elif subtype in ("long-term capital gain", "short-term capital gain"):
                    txn_type = "capital_gain"
                elif subtype in ("contribution", "deposit"):
                    txn_type = "transfer"
                elif subtype == "fee":
                    txn_type = "fee"

                inv_txn = InvestmentTransaction(
                    investment_account_id=inv_account.id,
                    security_id=security.id if security else None,
                    plaid_investment_transaction_id=plaid_inv_txn_id,
                    date=txn_date,
                    type=txn_type,
                    quantity=float(txn_data.get("quantity", 0)) if txn_data.get("quantity") else None,
                    price=float(txn_data.get("price", 0)) if txn_data.get("price") else None,
                    amount=float(txn_data.get("amount", 0)),
                    fees=float(txn_data.get("fees") or 0),
                    notes=txn_data.get("name"),
                )
                inv_db.add(inv_txn)
                added += 1

            offset += len(inv_txns)
            if offset >= total_count or len(inv_txns) == 0:
                break

        inv_db.commit()
        logger.info(
            f"Investment transactions sync: +{added} skipped={skipped} "
            f"for {inv_account.account_name}"
        )
        return {"added": added, "skipped": skipped}


# Module-level singleton
plaid_service = PlaidService()
