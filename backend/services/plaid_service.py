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
    def client(self) -> plaid_api.PlaidApi:
        """Lazy-init the Plaid API client."""
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
                raise ValueError(
                    f"No Plaid secret found for environment '{env}'. "
                    f"Set PLAID_PRODUCTION_SECRET (for production) or "
                    f"PLAID_SECRET (for sandbox) in your .env file."
                )

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

    def sync_transactions(self, account, db: Session) -> dict:
        """
        Cursor-based transaction sync for one account.
        Deduplicates by plaid_transaction_id, runs categorization on new ones.

        Returns: {"added": int, "modified": int, "removed": int}
        """
        from ..models import Transaction
        from .categorize import categorize_transaction

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
                account.last_sync_error = str(error_body)[:500]
                if "ITEM_LOGIN_REQUIRED" in str(error_body):
                    account.plaid_connection_status = "item_login_required"
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
            existing.date = txn_date
            existing.description = description
            existing.merchant_name = merchant_name
            existing.amount = amount
            existing.is_pending = is_pending
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
                pending_match.plaid_transaction_id = plaid_txn_id
                pending_match.date = txn_date
                pending_match.description = description
                pending_match.merchant_name = merchant_name
                pending_match.amount = amount
                pending_match.is_pending = False
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
            archive_match.merchant_name = merchant_name
            archive_match.is_pending = is_pending
            # Keep the archive description if original_description isn't available
            if original_desc:
                archive_match.description = description
            # Keep existing category assignment from archive
            logger.info(
                f"  Merged Plaid txn with archive: {description[:50]} "
                f"${amount} on {txn_date}"
            )
            db.flush()
            return 1

        # ── 4. Brand new transaction — run categorization engine ──
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


# Module-level singleton
plaid_service = PlaidService()
