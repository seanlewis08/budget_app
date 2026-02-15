"""
Historical Archive Importer

Imports pre-labeled transactions from Excel archive files (2021-2024)
and raw CSV bank exports into the SQLite database.

Supported formats:
- 2024 (All_Bills.xlsx): Short_Desc + Category_2 + Account column
- 2023 (Curated_Bills.xlsx): Short_Desc + Category_2 (Discover only)
- 2022 (Budget 2022_Final.xlsx): Multi-sheet, Short_Desc + Category_2
- 2021 (Budget 2021 Final.xlsx): Multi-sheet, Specific Category / Main Category taxonomy
- Raw CSVs from YTD_downloads/: Discover, Wells Fargo, SoFi formats

All imports deduplicate against existing transactions.
Missing subcategories are auto-created from archive Category_2 → Short_Desc pairs.
"""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from ..models import Account, Category, Transaction

logger = logging.getLogger(__name__)

# ── Account Resolution Maps ──

ACCOUNT_MAP = {
    "discover": "discover",
    "wells_fargo": "wellsfargo",
    "wells_fargo_checking": "wellsfargo",
    "wellsfargo": "wellsfargo",
    "wells fargo": "wellsfargo",
    "sofi_checking": "sofi",
    "sofi checking": "sofi",
    "sofi_savings": "sofi",
    "sofi savings": "sofi",
    "sofi": "sofi",
    "care_credit": "care_credit",
    "care credit": "care_credit",
    "carecredit": "care_credit",
    "best_buy": "best_buy",
    "best buy": "best_buy",
    "bestbuy": "best_buy",
    "amex": "amex",
    "american_express": "amex",
    "american express": "amex",
}

ACCOUNT_TYPE_MAP = {
    "discover": "credit",
    "wells_fargo": "checking",
    "wells_fargo_checking": "checking",
    "wellsfargo": "checking",
    "wells fargo": "checking",
    "sofi_checking": "checking",
    "sofi checking": "checking",
    "sofi_savings": "savings",
    "sofi savings": "savings",
    "care_credit": "credit",
    "care credit": "credit",
    "carecredit": "credit",
    "best_buy": "credit",
    "best buy": "credit",
    "bestbuy": "credit",
    "amex": "credit",
    "american_express": "credit",
    "american express": "credit",
}

# Map 2021 "Secondary Category" values to our Category_2 parent names
LEGACY_CATEGORY_MAP = {
    "savings, investing, & debt": "Payment_and_Interest",
    "recreation & entertainment": "Recreation_Entertainment",
    "health & wellness": "Medical",
    "food & drink": "Food",
    "food": "Food",
    "transportation": "Transportation",
    "housing": "Housing",
    "home": "Housing",
    "utilities": "Utilities",
    "personal spending": "Personal_Spending",
    "income": "Income",
    "misc": "Misc",
    "miscellaneus": "Misc",
    "miscellaneous": "Misc",
    "people": "People",
    "government": "Government",
    "insurance": "Insurance",
    "travel": "Travel",
    "medical & healthcare": "Medical",
    "medical": "Medical",
}

# Map 2021 "Specific Category" values to our Short_Desc names
SKIP_SHEETS = {
    "summary", "account", "cat sum", "people summary",
    "short desc summary", "reoccuring", "reoccurring", "the plan",
    "subscriptions", "cash flow", "waterfall", "debts",
    "avidia deposits", "categories - wip", "personal budget - wip",
    "budget", "accounts", "category summary", "sheet1",
    # Non-data sheets in Budget 2023 and similar files
    "june plan", "student loan amort", "lasik", "hsa", "fidelity",
    "vincent", "detailed summary", "personal spending",
    "transportation", "groceries", "europe", "count_check",
    "repayment plan",
    # Non-data sheets in Budget 2022
    "discover account", "june trips",
    # Non-data sheets in Budget 2024
    "reoccurring", "categories", "check", "loan schedule",
}

LEGACY_SHORT_DESC_MAP = {
    "streaming services": "subscriptions",
    "resteraunts": "restaurant",
    "conveinence store": "conv_store",
    "home maintenance": "home_supplies",
    "office supplies": "desk_supplies",
    "walmart/target run": "walmart_target",
    "personal debt": "student_loan",
    "sporting events": "live_event",
    "study material (pre nationwide)": "learning",
    "gifts/donations": "gift",
    "hobbies": "misc_other",
    "merchandise": "purchases",
    "securities": "investment",
    "self care": "self_care",
    "eye care": "vision",
    "maintenance": "car",
    "family activities": "family",
    "clothes": "clothing",
    "electricity": "electric",
    "credit": "credit_card_payment",
    "rent": "rent",
    "gas": "gas",
    "groceries": "groceries",
    "water": "water",
    "video games": "video_games",
    "home supplies": "home_supplies",
}


# ── Category Management ──

def ensure_categories_exist(
    short_desc_to_parent: dict[str, str],
    db: Session,
) -> dict[str, int]:
    """
    Given a mapping of {short_desc: Category_2_parent}, ensure all subcategories
    exist in the database. Creates any missing ones.

    Returns: dict mapping short_desc (lowercase) → category_id
    """
    # Build parent lookup: Category_2 name → parent category id
    parents = db.query(Category).filter(Category.parent_id.is_(None)).all()
    parent_lookup = {}
    for p in parents:
        parent_lookup[p.short_desc.lower()] = p.id
        parent_lookup[p.display_name.lower().replace(" ", "_").lower()] = p.id

    # Build existing category lookup from ALL categories (parents + children)
    # to avoid UNIQUE constraint violations on short_desc
    all_cats = db.query(Category).all()
    cat_lookup = {cat.short_desc.lower(): cat.id for cat in all_cats}

    created_count = 0
    for sd_raw, parent_raw in short_desc_to_parent.items():
        sd = sd_raw.strip().lower()
        if not sd or sd == "nan" or sd == "balance":
            continue
        if sd in cat_lookup:
            continue

        # Find parent
        parent_key = parent_raw.strip().lower().replace(" ", "_") if parent_raw else None
        parent_id = None
        if parent_key:
            parent_id = parent_lookup.get(parent_key)
            if not parent_id:
                # Try without underscores
                parent_id = parent_lookup.get(parent_key.replace("_", " "))
            if not parent_id:
                # Create the parent too
                new_parent = Category(
                    short_desc=parent_key,
                    display_name=parent_raw.strip().replace("_", " "),
                    parent_id=None,
                    color="#AEB6BF",
                )
                db.add(new_parent)
                db.flush()
                parent_lookup[parent_key] = new_parent.id
                parent_id = new_parent.id
                logger.info(f"  Created parent category: {parent_raw}")

        if not parent_id:
            parent_id = parent_lookup.get("misc")

        # Create subcategory
        display = sd.replace("_", " ").title()
        new_cat = Category(
            short_desc=sd,
            display_name=display,
            parent_id=parent_id,
        )
        db.add(new_cat)
        db.flush()
        cat_lookup[sd] = new_cat.id
        created_count += 1

    if created_count:
        db.commit()
        logger.info(f"  Created {created_count} new subcategories from archive data")

    return cat_lookup


def _build_lookups(db: Session) -> tuple[dict, dict]:
    """Build category and account lookup dicts."""
    subcats = db.query(Category).filter(Category.parent_id.isnot(None)).all()
    cat_lookup = {cat.short_desc.lower(): cat.id for cat in subcats}

    accounts = db.query(Account).all()
    acct_lookup = {}
    for acct in accounts:
        # Key by institution+type for unique lookups
        acct_lookup[f"{acct.institution}:{acct.account_type}"] = acct
        acct_lookup[acct.institution] = acct
        acct_lookup[acct.name.lower()] = acct

    return cat_lookup, acct_lookup


# Display names for auto-created accounts
ACCOUNT_DISPLAY_NAMES = {
    "care_credit": "Care Credit",
    "best_buy": "Best Buy",
    "amex": "American Express",
    "discover": "Discover",
    "wellsfargo": "Wells Fargo",
    "sofi": "SoFi",
}


def _ensure_account(inst: str, acct_type: str, acct_lookup: dict, db: Session):
    """Find or auto-create an account. Returns the Account object."""
    # Try composite key first
    key = f"{inst}:{acct_type}"
    if key in acct_lookup:
        return acct_lookup[key]

    # Try institution fallback
    acct = acct_lookup.get(inst)
    if acct and acct.account_type == acct_type:
        return acct

    # Try iterating all values for a match
    for a in acct_lookup.values():
        if hasattr(a, 'institution') and a.institution == inst and a.account_type == acct_type:
            return a

    # Auto-create the account
    display = ACCOUNT_DISPLAY_NAMES.get(inst, inst.replace("_", " ").title())
    if acct_type == "credit":
        name = f"{display} Card"
    elif acct_type == "savings":
        name = f"{display} Savings"
    else:
        name = f"{display} Checking"

    new_acct = Account(
        name=name,
        institution=inst,
        account_type=acct_type,
    )
    db.add(new_acct)
    db.flush()
    acct_lookup[key] = new_acct
    acct_lookup[inst] = new_acct
    acct_lookup[name.lower()] = new_acct
    logger.info(f"  Auto-created account: {name} ({inst}/{acct_type})")
    return new_acct


# ── Excel Import ──

def import_archive_excel(
    file_path: str,
    db: Session,
    default_account: Optional[str] = None,
) -> dict:
    """
    Import a curated Excel archive file.

    Returns: {"imported": int, "skipped_duplicates": int, "uncategorized": int, "errors": int}
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(f"Importing archive: {path.name}")

    # Phase 1: Scan for Short_Desc → Category_2 pairs and ensure categories exist
    sd_to_parent = _scan_categories_from_excel(file_path)
    cat_lookup = ensure_categories_exist(sd_to_parent, db)

    # Refresh lookups after category creation
    cat_lookup, acct_lookup = _build_lookups(db)

    # Phase 2: Import transactions
    xls = pd.ExcelFile(file_path)
    sheet_names = xls.sheet_names

    total_result = {"imported": 0, "skipped_duplicates": 0, "uncategorized": 0, "errors": 0, "skipped_balance": 0}

    for sheet in sheet_names:
        if sheet.lower() in SKIP_SHEETS:
            continue
        df = pd.read_excel(file_path, sheet_name=sheet)
        if len(df) < 2:
            continue

        # Auto-detect header row if columns are all unnamed/NaN
        # (e.g. Budget 2024.xlsx Data sheet has headers at row 3)
        df = _fix_header_row(df, file_path, sheet)

        sheet_account = _guess_account_from_sheet(sheet)
        result = _import_dataframe(
            df, db, cat_lookup, acct_lookup,
            default_account=sheet_account or default_account,
        )
        _merge_results(total_result, result)
        logger.info(f"  Sheet '{sheet}': +{result['imported']} imported, "
                    f"{result['skipped_duplicates']} dupes, {result['uncategorized']} uncategorized")

    db.commit()
    logger.info(
        f"Archive import complete: {total_result['imported']} imported, "
        f"{total_result['skipped_duplicates']} duplicates, "
        f"{total_result['uncategorized']} uncategorized (pending review), "
        f"{total_result['skipped_balance']} balance rows skipped"
    )
    return total_result


def _fix_header_row(df: pd.DataFrame, file_path: str, sheet_name: str) -> pd.DataFrame:
    """
    Auto-detect and fix misplaced header rows.

    Some Excel files (e.g. Budget 2024.xlsx) have blank rows before the actual
    column headers. If all columns are "Unnamed" or NaN, scan the first rows
    for recognizable column names and re-read with the correct header.
    """
    # Check if current columns look valid
    named_cols = [c for c in df.columns if not str(c).startswith("Unnamed") and str(c) != "nan"]
    if len(named_cols) >= 2:
        return df  # Headers look fine

    # Scan first 10 rows for a row containing known column names
    known_headers = {"amount", "description", "trans_date", "trans. date", "trans date",
                     "date", "transaction date", "short_desc", "category_2"}
    for i in range(min(10, len(df))):
        row_vals = {str(v).lower().strip() for v in df.iloc[i].tolist() if pd.notna(v)}
        matches = row_vals & known_headers
        if len(matches) >= 2:
            # Found the header row — re-read the sheet with correct header
            header_row = i + 1  # +1 because row 0 in data was row 1 in Excel (pandas already skipped row 0 as header)
            logger.info(f"  Sheet '{sheet_name}': detected headers at row {header_row}, re-reading")
            new_df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
            return new_df

    return df


def _scan_categories_from_excel(file_path: str) -> dict[str, str]:
    """Scan an Excel file for Short_Desc → Category_2 pairs."""
    pairs = {}
    xls = pd.ExcelFile(file_path)

    for sheet in xls.sheet_names:
        if sheet.lower() in SKIP_SHEETS:
            continue
        try:
            df = pd.read_excel(file_path, sheet_name=sheet)
            # Fix misplaced headers (e.g. Budget 2024.xlsx)
            df = _fix_header_row(df, file_path, sheet)
            cols = {str(c).lower().strip(): c for c in df.columns}

            sd_col = cols.get("short_desc")
            c2_col = cols.get("category_2")

            # 2021 fallback: Specific Category → Short_Desc equivalent
            if not sd_col:
                sd_col = cols.get("specific category")

            # 2021 fallback: Secondary Category → Category_2 equivalent
            if not c2_col:
                c2_col = cols.get("secondary category")
                if not c2_col:
                    c2_col = cols.get("main category")

            if sd_col and c2_col:
                for _, row in df[[sd_col, c2_col]].dropna().iterrows():
                    sd = str(row[sd_col]).strip().lower()
                    c2 = str(row[c2_col]).strip()
                    if sd and sd != "nan" and c2 and c2 != "nan":
                        # Map legacy names
                        sd = LEGACY_SHORT_DESC_MAP.get(sd, sd)
                        c2_mapped = LEGACY_CATEGORY_MAP.get(c2.lower(), c2)
                        pairs[sd] = c2_mapped
            elif sd_col:
                # No parent info, map to Misc
                for val in df[sd_col].dropna().unique():
                    sd = str(val).strip().lower()
                    sd = LEGACY_SHORT_DESC_MAP.get(sd, sd)
                    if sd and sd != "nan":
                        pairs.setdefault(sd, "Misc")

        except Exception as e:
            logger.debug(f"Skipping sheet {sheet} for category scan: {e}")

    return pairs


def _import_dataframe(
    df: pd.DataFrame,
    db: Session,
    cat_lookup: dict,
    acct_lookup: dict,
    default_account: Optional[str] = None,
) -> dict:
    """Import a single DataFrame of transactions."""
    result = {"imported": 0, "skipped_duplicates": 0, "uncategorized": 0, "errors": 0, "skipped_balance": 0}

    col_map = _normalize_columns(df.columns.tolist())

    # Prefer debit_amount over amount when both exist (WF 2022: Amount has absolute
    # values while Debit_Amount preserves sign). Also handles WF 2023 which only has
    # Debit_Amount and no Amount column.
    if col_map.get("debit_amount"):
        col_map["amount"] = col_map["debit_amount"]

    if not col_map.get("date") or not col_map.get("amount"):
        logger.warning(f"Missing required columns (date/amount). Found: {df.columns.tolist()}")
        return result

    # Use description or description2
    if not col_map.get("description"):
        if "description2" in {str(c).lower().strip() for c in df.columns}:
            for c in df.columns:
                if str(c).lower().strip() == "description2":
                    col_map["description"] = c
                    break
        else:
            logger.warning(f"Missing description column. Found: {df.columns.tolist()}")
            return result

    for _, row in df.iterrows():
        try:
            # Parse date
            raw_date = row[col_map["date"]]
            txn_date = _parse_date(raw_date)
            if not txn_date:
                result["errors"] += 1
                continue

            # Parse description
            description = str(row[col_map["description"]]).strip()
            if not description or description == "nan":
                # Try description2 fallback
                if col_map.get("description2"):
                    description = str(row[col_map["description2"]]).strip()
                if not description or description == "nan":
                    continue

            # Parse amount
            amount_val = row[col_map["amount"]]
            if pd.isna(amount_val):
                # Try debit_amount fallback (2022 WF)
                if col_map.get("debit_amount"):
                    amount_val = row[col_map["debit_amount"]]
                if pd.isna(amount_val):
                    continue
            amount = float(amount_val)

            # Determine account early so we can normalize signs
            account = _resolve_account(row, col_map, acct_lookup, default_account, db=db)

            # Normalize sign convention.
            # App convention: positive = expense, negative = income.
            # Bank accounts (checking/savings) use reversed signs: positive = deposit, negative = debit.
            # Most credit cards (Discover, Care Credit, Best Buy) match: positive = purchase.
            # AMEX uses bank-style signs (negative = purchase), so it also needs flipping.
            needs_flip = (
                (account and account.account_type in ("checking", "savings"))
                or (account and account.institution == "amex")
            )
            if needs_flip:
                amount = -amount

            # Skip balance/zero rows
            short_desc_val = None
            if col_map.get("short_desc"):
                sd_raw = str(row[col_map["short_desc"]]).strip().lower()
                if sd_raw and sd_raw != "nan":
                    short_desc_val = LEGACY_SHORT_DESC_MAP.get(sd_raw, sd_raw)

            if short_desc_val == "balance" or (description.lower() == "balance" and amount > 0):
                result["skipped_balance"] += 1
                continue

            # Skip payment rows that are just transfers between accounts
            if short_desc_val == "payment" and description.lower().startswith("internet payment"):
                result["skipped_balance"] += 1
                continue

            # Resolve category
            category_id = None
            if short_desc_val:
                category_id = cat_lookup.get(short_desc_val)

            if not category_id and col_map.get("category_2"):
                c2 = str(row[col_map["category_2"]]).strip().lower()
                if c2 and c2 != "nan":
                    category_id = cat_lookup.get(c2)

            if not category_id and col_map.get("specific_category"):
                sc = str(row[col_map["specific_category"]]).strip().lower()
                sc = LEGACY_SHORT_DESC_MAP.get(sc, sc)
                if sc and sc != "nan":
                    category_id = cat_lookup.get(sc)

            # Determine status based on whether we found a category
            if category_id:
                status = "auto_confirmed"
            else:
                status = "pending_review"
                result["uncategorized"] += 1

            # Account was already resolved above (for sign normalization)
            if not account:
                result["errors"] += 1
                continue

            # Deduplicate
            existing = (
                db.query(Transaction)
                .filter(
                    Transaction.account_id == account.id,
                    Transaction.date == txn_date,
                    Transaction.description == description,
                    Transaction.amount == amount,
                )
                .first()
            )
            if existing:
                result["skipped_duplicates"] += 1
                continue

            txn = Transaction(
                account_id=account.id,
                date=txn_date,
                description=description,
                merchant_name=description[:200],
                amount=amount,
                category_id=category_id,
                predicted_category_id=category_id,
                status=status,
                source="archive_import",
                is_pending=False,
            )
            db.add(txn)
            result["imported"] += 1

        except Exception as e:
            logger.warning(f"Row import error: {e}")
            result["errors"] += 1

    db.flush()
    return result


# ── CSV Import ──

def import_csv(
    file_path: str,
    db: Session,
    institution: str,
    account_type: str = "checking",
) -> dict:
    """
    Import a raw CSV bank export. These have no categories,
    so all transactions come in as pending_review.

    Supports: Discover, Wells Fargo, SoFi CSV formats.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(f"Importing CSV: {path.name} ({institution})")

    _, acct_lookup = _build_lookups(db)

    # Resolve account
    inst = ACCOUNT_MAP.get(institution.lower(), institution.lower())
    acct_type = ACCOUNT_TYPE_MAP.get(institution.lower(), account_type)
    account = None
    for a in acct_lookup.values():
        if a.institution == inst and a.account_type == acct_type:
            account = a
            break
    if not account:
        account = acct_lookup.get(inst)
    if not account:
        raise ValueError(f"No account found for institution: {institution}")

    # Detect format and read
    if "wellsfargo" in institution.lower() or "wells_fargo" in institution.lower():
        df = _read_wellsfargo_csv(file_path)
    else:
        df = pd.read_csv(file_path)

    result = {"imported": 0, "skipped_duplicates": 0, "uncategorized": 0, "errors": 0, "skipped_balance": 0}

    col_map = _normalize_columns(df.columns.tolist())
    if not col_map.get("date") or not col_map.get("amount"):
        logger.warning(f"Missing required columns. Found: {df.columns.tolist()}")
        return result

    desc_col = col_map.get("description")
    if not desc_col:
        logger.warning(f"Missing description column. Found: {df.columns.tolist()}")
        return result

    for _, row in df.iterrows():
        try:
            txn_date = _parse_date(row[col_map["date"]])
            if not txn_date:
                result["errors"] += 1
                continue

            description = str(row[desc_col]).strip()
            if not description or description == "nan":
                continue

            amount = float(row[col_map["amount"]])

            # Normalize sign convention for bank accounts (checking/savings).
            # Bank exports use: positive = deposit/income, negative = debit/expense.
            # App convention: positive = expense, negative = income.
            if account and account.account_type in ("checking", "savings"):
                amount = -amount

            # Deduplicate
            existing = (
                db.query(Transaction)
                .filter(
                    Transaction.account_id == account.id,
                    Transaction.date == txn_date,
                    Transaction.description == description,
                    Transaction.amount == amount,
                )
                .first()
            )
            if existing:
                result["skipped_duplicates"] += 1
                continue

            txn = Transaction(
                account_id=account.id,
                date=txn_date,
                description=description,
                merchant_name=description[:200],
                amount=amount,
                category_id=None,
                predicted_category_id=None,
                status="pending_review",
                source="csv_import",
                is_pending=False,
            )
            db.add(txn)
            result["imported"] += 1
            result["uncategorized"] += 1

        except Exception as e:
            logger.warning(f"CSV row error: {e}")
            result["errors"] += 1

    db.commit()
    logger.info(f"CSV import: {result['imported']} imported, {result['skipped_duplicates']} duplicates")
    return result


def _read_wellsfargo_csv(file_path: str) -> pd.DataFrame:
    """Read Wells Fargo CSV which has no header row."""
    df = pd.read_csv(file_path, header=None)
    # WF format: date, amount, *, unknown, description
    if len(df.columns) >= 5:
        df.columns = ["Date", "Amount", "Flag", "Extra", "Description"]
    elif len(df.columns) == 4:
        df.columns = ["Date", "Amount", "Flag", "Description"]
    else:
        df.columns = [f"col_{i}" for i in range(len(df.columns))]
        df.rename(columns={"col_0": "Date", "col_1": "Amount", "col_2": "Description"}, inplace=True)
    return df


# ── Column Normalization ──

def _normalize_columns(columns: list) -> dict:
    """Map varying column names to standard field names."""
    col_map = {}

    for col in columns:
        cl = str(col).lower().strip()

        # Date columns (prefer transaction date)
        if cl in ("trans_date", "trans. date", "trans date", "date", "transaction date", "trans. date"):
            if "date" not in col_map:
                col_map["date"] = col
        elif cl == "post date":
            if "date" not in col_map:
                col_map["date"] = col

        # Description
        elif cl == "description":
            col_map["description"] = col
        elif cl == "description2":
            col_map["description2"] = col

        # Amount
        elif cl == "amount":
            col_map["amount"] = col
        elif cl == "debit_amount":
            col_map["debit_amount"] = col

        # Category fields
        elif cl == "short_desc":
            col_map["short_desc"] = col
        elif cl == "category_2":
            col_map["category_2"] = col
        elif cl == "specific category":
            col_map["specific_category"] = col
            if "short_desc" not in col_map:
                col_map["short_desc"] = col  # Use as Short_Desc equivalent
        elif cl == "secondary category":
            if "category_2" not in col_map:
                col_map["category_2"] = col
        elif cl == "main category":
            col_map["main_category"] = col
            if "category_2" not in col_map:
                col_map["category_2"] = col

        # Account
        elif cl == "account":
            col_map["account"] = col

        # Primary (2021 WF — for filtering non-transaction rows)
        elif cl == "primary":
            col_map["primary"] = col

    return col_map


# ── Helpers ──

def _parse_date(val) -> Optional[date]:
    """Parse a date value from various formats."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None

    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()

    if isinstance(val, pd.Timestamp):
        return val.date()

    val_str = str(val).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%m-%d-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue

    return None


def _guess_account_from_sheet(sheet_name: str) -> Optional[str]:
    """Guess account identifier from an Excel sheet name."""
    sn = sheet_name.lower()
    if "discover" in sn and "account" not in sn:
        return "discover"
    if "wells" in sn or "wf" in sn:
        return "wellsfargo"
    if "sofi" in sn and "check" in sn:
        return "sofi_checking"
    if "sofi" in sn and "sav" in sn:
        return "sofi_savings"
    if "care" in sn and "credit" in sn:
        return "care_credit"
    if "best" in sn and "buy" in sn:
        return "best_buy"
    if "amex" in sn or "american" in sn and "express" in sn:
        return "amex"
    return None


def _resolve_account(row, col_map: dict, acct_lookup: dict, default: Optional[str], db: Session = None) -> Optional:
    """Figure out which Account object to use for this row. Auto-creates if db is provided."""
    if col_map.get("account"):
        acct_name = str(row[col_map["account"]]).strip().lower()
        if acct_name and acct_name != "nan":
            inst = ACCOUNT_MAP.get(acct_name)
            if inst:
                acct_type = ACCOUNT_TYPE_MAP.get(acct_name, "credit")
                if db:
                    return _ensure_account(inst, acct_type, acct_lookup, db)
                for a in acct_lookup.values():
                    if hasattr(a, 'institution') and a.institution == inst and (not acct_type or a.account_type == acct_type):
                        return a
                return acct_lookup.get(inst)

    if default:
        inst = ACCOUNT_MAP.get(default.lower(), default.lower())
        acct_type = ACCOUNT_TYPE_MAP.get(default.lower(), "credit")
        if db:
            return _ensure_account(inst, acct_type, acct_lookup, db)
        for a in acct_lookup.values():
            if hasattr(a, 'institution') and a.institution == inst and (not acct_type or a.account_type == acct_type):
                return a
        return acct_lookup.get(inst)

    return None


def _merge_results(total: dict, partial: dict):
    """Add partial results into total."""
    for key in total:
        total[key] += partial.get(key, 0)


# ── Folder Scanner ──

def scan_archive_folder(base_path: str) -> list[dict]:
    """
    Scan the Budget archive folder and return importable files.
    """
    base = Path(base_path)
    files = []

    # Archive folder: curated Excel files
    archive_dir = base / "Archive"
    if archive_dir.exists():
        for year_dir in sorted(archive_dir.iterdir()):
            if year_dir.is_dir() and year_dir.name.isdigit():
                year = int(year_dir.name)
                for f in year_dir.glob("*.xlsx"):
                    if f.name.startswith("~$"):
                        continue
                    files.append({
                        "path": str(f),
                        "filename": f.name,
                        "year": year,
                        "type": "excel_archive",
                        "folder": f"Archive/{year_dir.name}",
                    })

    # Top-level Budget files
    for f in base.glob("Budget *.xlsx"):
        if f.name.startswith("~$"):
            continue
        # Extract year from filename
        for part in f.stem.split():
            if part.isdigit() and len(part) == 4:
                files.append({
                    "path": str(f),
                    "filename": f.name,
                    "year": int(part),
                    "type": "excel_archive",
                    "folder": ".",
                })
                break

    # YTD_downloads: raw CSV files
    ytd_dir = base / "YTD_downloads"
    if ytd_dir.exists():
        for year_dir in sorted(ytd_dir.iterdir()):
            if year_dir.is_dir() and year_dir.name.isdigit():
                year = int(year_dir.name)
                for f in year_dir.glob("*.csv"):
                    files.append({
                        "path": str(f),
                        "filename": f.name,
                        "year": year,
                        "type": "csv_download",
                        "folder": f"YTD_downloads/{year_dir.name}",
                    })

    return sorted(files, key=lambda x: (x["year"], x["filename"]))
