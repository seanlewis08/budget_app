# Part 6 — Advanced Features

With the core transaction flow working (import, categorize, review, spend), this part builds the four advanced systems that round out the app: AI-powered financial insights, investment portfolio tracking, the background sync scheduler, and historical archive imports. Each one operates semi-independently — you can use the budgeting features without investments, or skip AI entirely and categorize manually.

---

## 6.1 AI Financial Insights

The Insights feature gives you a personal financial advisor powered by Claude. It builds a comprehensive snapshot of your finances from the database, sends it to Claude along with any personal context you provide, and streams the analysis back in real time. Follow-up questions are supported through a chat interface that maintains conversation history.

### Building the Financial Snapshot (`backend/services/financial_advisor.py`)

Before Claude can analyze anything, it needs data. The `build_financial_snapshot` function assembles a nine-section summary of your financial life from the last six months. Each section answers a specific question:

```python
def build_financial_snapshot(db: Session) -> dict:
    """Build a comprehensive financial snapshot for AI analysis."""
    six_months_ago = date.today() - timedelta(days=180)

    # Fetch all confirmed transactions from the last 6 months
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.date >= six_months_ago,
            Transaction.status.in_(["auto_confirmed", "manual_confirmed"]),
        )
        .all()
    )

    snapshot = {
        "period": f"{six_months_ago} to {date.today()}",
        "income": _calc_income(transactions),
        "expenses": _calc_expenses(transactions),
        "recurring_charges": _find_recurring(transactions),
        "cash_flow": _monthly_cash_flow(transactions),
        "budget_status": _budget_status(db),
        "accounts": _account_summary(db),
        "investments": _investment_summary(),
        "savings_progress": _savings_rate(transactions),
        "top_categories": _top_spending_categories(transactions),
    }
    return snapshot
```

The key design decision is what to exclude. Internal transfers between your own accounts (rent payments from checking to landlord, credit card payments) inflate both income and expenses if counted. The function maintains an `EXCLUDED_CATEGORIES` set:

```python
EXCLUDED_CATEGORIES = {
    "credit_card_payment", "transfer", "payment", "balance",
    "internal_transfer", "account_transfer",
}
```

Any transaction whose category `short_desc` falls in this set gets filtered out of income and expense calculations. This gives you a realistic picture of money coming in versus money going out.

The `format_snapshot_for_prompt` function converts the nested dictionary into readable text. Claude processes natural language better than raw JSON, so instead of sending `{"groceries": 847.23}`, it sends `Groceries: $847.23`. The formatted snapshot typically runs 500–1,500 words depending on how many accounts and categories you have.

### The Insights Router (`backend/routers/insights.py`)

The router exposes three endpoints, each serving a different purpose:

```python
MODEL_ANALYZE = "claude-sonnet-4-5-20250929"   # Deep analysis
MODEL_CHAT    = "claude-haiku-4-5-20251001"     # Follow-up chat
```

The model split is deliberate. The initial analysis benefits from Sonnet's stronger reasoning — it catches patterns like "your restaurant spending doubled in December" or "you're paying for two overlapping streaming services." Follow-up questions like "how much exactly did I spend on streaming?" don't need that depth, so Haiku handles them at roughly one-quarter the cost.

**Snapshot caching.** Building the snapshot queries the database extensively. Since the data doesn't change between requests (no one imports transactions mid-analysis), the router caches it:

```python
_snapshot_cache = {}
_snapshot_ttl = 300  # 5 minutes

def _get_snapshot(db: Session, force_refresh: bool = False) -> dict:
    now = time.time()
    if (not force_refresh
        and "data" in _snapshot_cache
        and now - _snapshot_cache.get("timestamp", 0) < _snapshot_ttl):
        return _snapshot_cache["data"]

    snapshot = build_financial_snapshot(db)
    formatted = format_snapshot_for_prompt(snapshot)
    _snapshot_cache["data"] = formatted
    _snapshot_cache["raw"] = snapshot
    _snapshot_cache["timestamp"] = now
    return formatted
```

The `force_refresh` parameter lets the analyze endpoint always get fresh data, while the chat endpoint reuses the cached snapshot for the duration of a conversation.

**Streaming with Server-Sent Events.** Both the `/analyze` and `/chat` endpoints stream Claude's response token by token. The pattern is the same for both:

```python
@router.post("/analyze")
async def analyze(body: dict, db: Session = Depends(get_db)):
    snapshot = _get_snapshot(db, force_refresh=True)
    context = body.get("context", "")

    system_prompt = f"""You are a personal finance advisor...
    Here is the user's financial data:
    {snapshot}"""

    def generate():
        yield from _stream_anthropic(
            model=MODEL_ANALYZE,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Context: {context}\n\nAnalyze my finances."
            }],
        )

    return StreamingResponse(generate(), media_type="text/event-stream")
```

The `_stream_anthropic` helper wraps the Anthropic streaming API and formats each chunk as an SSE event:

```python
def _stream_anthropic(model, system, messages, max_tokens=4096):
    client = anthropic.Anthropic()

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield f"data: {json.dumps({'text': text})}\n\n"

    yield "data: [DONE]\n\n"
```

The `cache_control: ephemeral` annotation enables Anthropic's prompt caching. When you ask multiple follow-up questions, the system prompt (which contains your full financial snapshot) gets cached on Anthropic's servers for about five minutes. Subsequent requests with the same system prompt skip re-processing it, reducing costs by roughly 90% and cutting latency significantly.

**Follow-up chat** uses the same pattern but with a few differences: it uses the Haiku model, accepts a full `messages` array (so Claude sees the conversation history), and doesn't force-refresh the snapshot:

```python
@router.post("/chat")
async def chat(body: dict, db: Session = Depends(get_db)):
    snapshot = _get_snapshot(db)  # Uses cache
    messages = body.get("messages", [])

    system_prompt = f"You are a financial advisor. Data:\n{snapshot}"

    def generate():
        yield from _stream_anthropic(
            model=MODEL_CHAT,
            system=system_prompt,
            messages=messages,
            max_tokens=2048,
        )

    return StreamingResponse(generate(), media_type="text/event-stream")
```

The `/snapshot` endpoint returns the raw data without AI processing, which the frontend uses to show a "Financial Summary" sidebar alongside the chat.

### Graceful Degradation

If the `ANTHROPIC_API_KEY` isn't configured, the analyze endpoint returns an SSE error message explaining how to set it up. The rest of the app works normally — you can still import, categorize, and track budgets without AI.

---

## 6.2 Investment Portfolio Tracking

Investment tracking lives in a completely separate database (`~/BudgetApp/investments.db`) with its own models, sessions, and migration logic. This isolation means you can use the budgeting features without ever touching investments, and the main database stays lean for the queries that happen most often.

### Separate Database (`backend/investments_database.py`)

The investments database mirrors the main database setup exactly — same engine configuration, same WAL mode, same foreign key enforcement:

```python
DB_DIR = Path.home() / "BudgetApp"
DB_PATH = DB_DIR / "investments.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={
    "check_same_thread": False,
    "timeout": 30,
})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

A separate `get_investments_db` dependency works identically to the main `get_db`, providing database sessions to investment endpoints.

### Investment Models (`backend/models_investments.py`)

Four tables track the portfolio:

**InvestmentAccount** represents a brokerage account (Fidelity, Schwab, etc.). It links to the main database's `Account` table through `plaid_item_id` — when both your checking account and your brokerage are at the same institution, they share a Plaid connection, and the investment account reuses the encrypted access token stored on the banking side.

```python
class InvestmentAccount(InvestmentsBase):
    __tablename__ = "investment_accounts"

    id = Column(Integer, primary_key=True)
    plaid_item_id = Column(String(100))
    plaid_account_id = Column(String(100))
    account_name = Column(String(200))
    account_type = Column(String(50))        # taxable, roth, traditional_ira, 401k
    institution_name = Column(String(200))
    connection_status = Column(String(20), default="connected")
    last_synced_at = Column(DateTime)
    last_sync_error = Column(String(500))
```

**Security** represents a financial instrument — a stock, ETF, mutual fund, or cash equivalent. Not every security has a ticker symbol (some mutual funds are identified only by CUSIP), so the `ticker` field is nullable:

```python
class Security(InvestmentsBase):
    __tablename__ = "securities"

    id = Column(Integer, primary_key=True)
    plaid_security_id = Column(String(100), unique=True)
    ticker = Column(String(20))
    name = Column(String(200))
    security_type = Column(String(50))    # stock, etf, mutual_fund, cash_equivalent
    sector = Column(String(100))
    close_price = Column(Float)
    close_price_as_of = Column(Date)
    price_source = Column(String(20))     # plaid, yfinance, manual
```

**Holding** represents a position — how many shares of a security you own in a given account. The unique constraint on `(investment_account_id, security_id, as_of_date)` enables daily snapshots: each day you sync, a new row records that day's position. Over time, these snapshots let you chart portfolio performance:

```python
class Holding(InvestmentsBase):
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True)
    investment_account_id = Column(Integer, ForeignKey("investment_accounts.id"))
    security_id = Column(Integer, ForeignKey("securities.id"))
    quantity = Column(Float)
    cost_basis = Column(Float)
    current_value = Column(Float)
    as_of_date = Column(Date)

    __table_args__ = (
        UniqueConstraint("investment_account_id", "security_id", "as_of_date"),
    )
```

**InvestmentTransaction** records buys, sells, dividends, and transfers with Plaid deduplication:

```python
class InvestmentTransaction(InvestmentsBase):
    __tablename__ = "investment_transactions"

    id = Column(Integer, primary_key=True)
    plaid_investment_transaction_id = Column(String(100), unique=True)
    investment_account_id = Column(Integer, ForeignKey("investment_accounts.id"))
    security_id = Column(Integer, ForeignKey("securities.id"))
    date = Column(Date)
    type = Column(String(50))    # buy, sell, dividend, transfer, capital_gain
    quantity = Column(Float)
    price = Column(Float)
    amount = Column(Float)
    fees = Column(Float)
```

### Investment API (`backend/routers/investments.py`)

The investments router is the largest in the app, with endpoints organized into five groups:

**Portfolio summary** (`GET /summary`) computes totals from the latest holding snapshot. It finds the most recent `as_of_date` in the holdings table, sums up current values and cost bases, then compares against the previous snapshot date to calculate day change:

```python
@router.get("/summary")
def portfolio_summary(inv_db: Session = Depends(get_investments_db)):
    latest_date = inv_db.query(func.max(Holding.as_of_date)).scalar()
    if not latest_date:
        return {"total_value": 0, "total_cost_basis": 0, ...}

    holdings = inv_db.query(Holding).filter(
        Holding.as_of_date == latest_date
    ).all()

    total_value = sum(h.current_value or 0 for h in holdings)
    total_cost_basis = sum(h.cost_basis or 0 for h in holdings)
    total_gain_loss = total_value - total_cost_basis

    # Day change: compare latest snapshot to previous one
    prev_date = inv_db.query(func.max(Holding.as_of_date)).filter(
        Holding.as_of_date < latest_date
    ).scalar()
    ...
```

**Holdings** (`GET /holdings`) returns every position with computed fields like gain/loss percentage and portfolio weight. Each holding joins to its Security (for ticker and price) and InvestmentAccount (for the account name).

**Performance** (`GET /performance`) returns a date series of daily portfolio values for charting. It groups holdings by `as_of_date` and sums their values, giving you a time series you can plot against a benchmark.

**Allocation** (`GET /allocation`) breaks down the portfolio two ways: by security type (stock, ETF, mutual fund) and by sector (technology, healthcare, etc.). Both return name-value-percentage triples for pie/donut charts.

**Account management** includes Plaid linking for investment accounts, manual account creation, manual holding entry (for brokerages that don't support Plaid), and sync triggers.

### Manual Entry

Not every brokerage supports Plaid's investment product. The manual entry flow lets you create an account and add holdings by ticker:

```python
@router.post("/accounts/manual")
def create_manual_account(data: ManualAccountRequest, inv_db):
    inv_account = InvestmentAccount(
        account_name=data.account_name,
        account_type=data.account_type,
        institution_name=data.institution_name,
        connection_status="manual",
    )
    inv_db.add(inv_account)
    inv_db.commit()

@router.post("/accounts/{account_id}/holdings")
def add_manual_holding(account_id, data: ManualHoldingRequest, inv_db):
    # Find or create the Security by ticker
    security = inv_db.query(Security).filter(
        Security.ticker == data.ticker.upper()
    ).first()
    if not security:
        security = Security(
            ticker=data.ticker.upper(),
            name=data.name or data.ticker.upper(),
            security_type="equity",
        )
        inv_db.add(security)
        inv_db.flush()

    # Fetch current price from Yahoo Finance
    current_price = security.close_price
    if not current_price:
        current_price = fetch_price_for_ticker(data.ticker.upper())
        ...

    holding = Holding(
        investment_account_id=account_id,
        security_id=security.id,
        quantity=data.quantity,
        cost_basis=cost_basis_per_share * data.quantity,
        current_value=current_price * data.quantity,
        as_of_date=date.today(),
    )
    inv_db.add(holding)
    inv_db.commit()
```

When you add a holding manually, the system immediately tries to fetch its current price from Yahoo Finance so your portfolio value is accurate from the start.

### Live Price Fetcher (`backend/services/price_fetcher.py`)

Stock prices go stale fast. The price fetcher uses `yfinance` to batch-update all securities that have ticker symbols:

```python
def fetch_all_prices(inv_db: Session) -> dict:
    securities = inv_db.query(Security).filter(
        Security.ticker.isnot(None)
    ).all()

    tickers = list(set(s.ticker for s in securities if s.ticker))
    if not tickers:
        return {"updated": 0, "failed": 0, "tickers": []}

    # Batch download — one API call for all tickers
    data = yf.download(tickers, period="1d", progress=False)

    updated = 0
    for security in securities:
        try:
            price = float(data["Close"][security.ticker].iloc[-1])
            security.close_price = price
            security.close_price_as_of = date.today()
            security.price_source = "yfinance"
            updated += 1
        except (KeyError, IndexError):
            continue

    inv_db.commit()
    return {"updated": updated, ...}
```

The batch download is important — `yfinance` makes a single HTTP request for all tickers instead of one per ticker, which is dramatically faster when you hold 20+ securities.

The `is_market_open` function checks whether the US stock market is currently open (weekdays, 9:30 AM–4:00 PM Eastern). The scheduler uses this to avoid wasting API calls on evenings and weekends:

```python
def is_market_open() -> bool:
    et = datetime.now(ZoneInfo("US/Eastern"))
    if et.weekday() >= 5:  # Saturday or Sunday
        return False
    market_open = et.replace(hour=9, minute=30, second=0)
    market_close = et.replace(hour=16, minute=0, second=0)
    return market_open <= et <= market_close
```

---

## 6.3 Budget System

The budget system is intentionally simple. Each budget is a row mapping a parent category to a monthly dollar limit. Spending is computed at query time by summing confirmed transactions — there's no running total to maintain or reconcile.

### Budget Router (`backend/routers/budgets.py`)

The `GET /` endpoint fetches all budgets and calculates current spending in a single query:

```python
@router.get("/")
def list_budgets(month: str = None, db: Session = Depends(get_db)):
    if not month:
        month = date.today().strftime("%Y-%m")

    year, mo = month.split("-")
    start = date(int(year), int(mo), 1)
    end = (start + timedelta(days=32)).replace(day=1)

    budgets = db.query(Budget).all()
    results = []

    for b in budgets:
        # Sum spending for this category's children
        spent = (
            db.query(func.sum(Transaction.amount))
            .join(Category, Transaction.category_id == Category.id)
            .filter(
                Category.parent_id == b.category_id,
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.status.in_(["auto_confirmed", "manual_confirmed"]),
                Transaction.amount > 0,
            )
            .scalar() or 0
        )

        results.append({
            "id": b.id,
            "category_id": b.category_id,
            "category_name": b.category.display_name,
            "amount": b.amount,
            "spent": round(float(spent), 2),
            "remaining": round(b.amount - float(spent), 2),
            "pct": round(float(spent) / b.amount * 100, 1) if b.amount > 0 else 0,
        })

    return sorted(results, key=lambda x: x["pct"], reverse=True)
```

The query joins through the Category table to sum all child categories under each budget's parent. A "Food" budget with a $600 limit captures spending from subcategories like groceries, restaurants, and coffee shops.

The sorting by percentage descending puts the most over-budget categories first, which is what you want to see at a glance.

**Creating and updating budgets** uses an upsert pattern — if a budget for that category already exists, update the amount; otherwise create a new one:

```python
@router.post("/")
def upsert_budget(req: BudgetCreate, db: Session = Depends(get_db)):
    existing = db.query(Budget).filter(
        Budget.category_id == req.category_id
    ).first()

    if existing:
        existing.amount = req.amount
        db.commit()
        return {"status": "updated", "id": existing.id}
    else:
        budget = Budget(category_id=req.category_id, amount=req.amount)
        db.add(budget)
        db.commit()
        return {"status": "created", "id": budget.id}
```

This means the frontend doesn't need to know whether it's creating or editing — it always sends the same POST request.

---

## 6.4 Background Sync Scheduler

When the app is running, a background scheduler keeps data fresh without manual intervention. It uses APScheduler's `BackgroundScheduler`, which runs jobs in a thread pool alongside the FastAPI server.

### Scheduler Configuration (`backend/services/sync_scheduler.py`)

Three jobs run on different schedules:

```python
def start_scheduler():
    # Bank transaction sync — every 4 hours
    scheduler.add_job(
        sync_all_accounts_job,
        trigger=IntervalTrigger(hours=4),
        id="plaid_sync_all",
        name="Sync all Plaid accounts",
        replace_existing=True,
    )

    # Investment holdings + transactions — every 6 hours
    scheduler.add_job(
        sync_investments_job,
        trigger=IntervalTrigger(hours=6),
        id="investment_sync",
        name="Sync investment accounts",
        replace_existing=True,
    )

    # Stock prices — weekdays during market hours
    scheduler.add_job(
        fetch_prices_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="9-16",
            minute="0,30",
            timezone="US/Eastern",
        ),
        id="price_refresh",
        name="Refresh stock prices",
        replace_existing=True,
    )

    scheduler.start()
```

The bank sync uses a simple interval trigger — every four hours regardless of the time of day. The price refresh uses a cron trigger that only fires on weekdays during market hours (9:00 AM–4:30 PM Eastern), running every 30 minutes. There's no point fetching prices at midnight or on Sunday.

Each job function creates its own database session, does its work, and closes the session in a `finally` block. This is important because APScheduler runs jobs in a thread pool, and SQLAlchemy sessions aren't thread-safe:

```python
def sync_all_accounts_job():
    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(
            Account.plaid_connection_status == "connected"
        ).all()

        for account in accounts:
            try:
                result = plaid_service.sync_transactions(
                    account, db, trigger="scheduled"
                )
                logger.info(f"  {account.name}: +{result['added']}")
            except Exception as e:
                logger.error(f"  {account.name}: sync failed — {e}")
    finally:
        db.close()
```

Notice the per-account try/except inside the loop. If one account fails (maybe its Plaid connection expired), the other accounts still get synced. Without this, a single broken connection would prevent all accounts from updating.

The investment sync job is more complex because it needs two database sessions — one for `investments.db` and one for `budget.db` (to look up encrypted access tokens). Both sessions are opened at the start and closed in `finally`.

### Lifecycle Integration

The scheduler hooks into FastAPI's lifespan events in `main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_investments_db()
    start_scheduler()
    yield
    stop_scheduler()
```

When the server starts, the scheduler starts. When the server shuts down (Ctrl+C, or Electron closing), the scheduler shuts down gracefully with `scheduler.shutdown(wait=False)`. The `wait=False` means it doesn't block waiting for any currently-running job to finish — it just stops scheduling new ones.

---

## 6.5 Standalone Sync Daemon (`backend/sync_daemon.py`)

The background scheduler only runs while the app is open. If you only open the app once a week, you'll have a week of un-synced transactions to process. The sync daemon solves this — it runs independently of the desktop app, syncing transactions on a schedule (typically via macOS LaunchAgent or cron).

### How It Works

The daemon is a standalone Python script that imports the same database and Plaid modules as the main app:

```python
from backend.database import SessionLocal, init_db
from backend.models import Account
from backend.services.plaid_service import PlaidService

def sync_all():
    """Sync all connected Plaid accounts once."""
    init_db()
    db = SessionLocal()
    plaid = PlaidService()

    accounts = db.query(Account).filter(
        Account.plaid_connection_status == "connected"
    ).all()

    for account in accounts:
        try:
            result = plaid.sync_transactions(account, db, trigger="scheduled")
            logger.info(f"  {account.name}: +{result['added']} new")
        except Exception as e:
            logger.error(f"  {account.name}: FAILED — {e}")
    db.close()
```

It writes to the same `budget.db` file, so the next time you open the desktop app, all the recent transactions are already there waiting to be reviewed.

### Git Backup

After each sync, the daemon can optionally commit `budget.db` to a private Git repository. This gives you versioned backups of your financial data:

```python
def backup_database():
    git_dir = BUDGET_DIR / ".git"
    if not git_dir.exists():
        logger.warning("Git backup not configured.")
        return False

    db_size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    txn_count = _get_transaction_count()

    _run_git("add", "budget.db")

    # Only commit if there are actual changes
    status = _run_git("status", "--porcelain", "budget.db")
    if not status.strip():
        logger.info("No database changes to back up.")
        return True

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"Backup {timestamp} — {txn_count} transactions, {db_size_mb:.1f} MB"
    _run_git("commit", "-m", msg)
    _run_git("push", "origin", "main")
```

The commit message includes the transaction count and database size, so your Git history becomes a log of your database growth:

```
Backup 2025-02-16 07:28 — 3247 transactions, 12.3 MB
Backup 2025-02-15 19:28 — 3241 transactions, 12.3 MB
Backup 2025-02-15 07:28 — 3238 transactions, 12.2 MB
```

### Running It

The daemon supports three modes:

```bash
# One-shot: sync + backup, then exit
python3 -m backend.sync_daemon

# One-shot without backup
python3 -m backend.sync_daemon --no-backup

# Continuous: sync every 12 hours (or custom interval)
python3 -m backend.sync_daemon --loop --interval 8
```

For automatic scheduling on macOS, create a LaunchAgent plist at `~/Library/LaunchAgents/com.budgetapp.sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.budgetapp.sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/python3</string>
        <string>-m</string>
        <string>backend.sync_daemon</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/budget-app</string>
    <key>StartInterval</key>
    <integer>43200</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>~/BudgetApp/logs/sync.log</string>
</dict>
</plist>
```

Load it with `launchctl load ~/Library/LaunchAgents/com.budgetapp.sync.plist` and it runs every 12 hours (43,200 seconds), including immediately on load. All output goes to `~/BudgetApp/logs/sync.log`.

One-time Git backup setup:

```bash
cd ~/BudgetApp
git init
git remote add origin git@github.com:YOUR_USER/budget-app-data.git
echo "logs/" > .gitignore
git add .gitignore budget.db
git commit -m "Initial database backup"
git push -u origin main
```

---

## 6.6 Archive Import

If you have years of historical transaction data in Excel spreadsheets or CSV files from before you set up Plaid, the archive importer brings it all into the database. This is what lets you have a complete financial picture going back years, not just from the day you connected your bank.

### The Import Service (`backend/services/archive_importer.py`)

The archive importer handles five different file formats spanning four years (2021–2024), each with different column names, sheet structures, and category taxonomies. The core challenge is normalization — making all these different formats produce the same `Transaction` records.

**Account resolution.** Different files refer to the same account in different ways — "Wells Fargo," "wells_fargo," "WF," or just a sheet named "Wells." Two lookup dictionaries handle this:

```python
ACCOUNT_MAP = {
    "discover": "discover",
    "wells_fargo": "wellsfargo",
    "wells fargo": "wellsfargo",
    "sofi_checking": "sofi",
    "sofi_savings": "sofi",
    "care_credit": "care_credit",
    "amex": "amex",
    "american_express": "amex",
    ...
}

ACCOUNT_TYPE_MAP = {
    "discover": "credit",
    "wellsfargo": "checking",
    "sofi_checking": "checking",
    "sofi_savings": "savings",
    "care_credit": "credit",
    ...
}
```

If an account doesn't exist in the database yet, the importer creates it automatically using the display name lookup:

```python
def _ensure_account(inst, acct_type, acct_lookup, db):
    # Try existing accounts first
    key = f"{inst}:{acct_type}"
    if key in acct_lookup:
        return acct_lookup[key]

    # Auto-create
    display = ACCOUNT_DISPLAY_NAMES.get(inst, inst.replace("_", " ").title())
    name = f"{display} Card" if acct_type == "credit" else f"{display} Checking"

    new_acct = Account(name=name, institution=inst, account_type=acct_type)
    db.add(new_acct)
    db.flush()
    acct_lookup[key] = new_acct
    return new_acct
```

**Category resolution.** Archive files have their own category systems. The 2021 files use "Secondary Category" and "Specific Category"; the 2022–2024 files use "Category_2" and "Short_Desc." Legacy names are mapped to the app's canonical names:

```python
LEGACY_CATEGORY_MAP = {
    "savings, investing, & debt": "Payment_and_Interest",
    "recreation & entertainment": "Recreation_Entertainment",
    "health & wellness": "Medical",
    "food & drink": "Food",
    ...
}

LEGACY_SHORT_DESC_MAP = {
    "streaming services": "subscriptions",
    "resteraunts": "restaurant",   # Fixing original typo
    "conveinence store": "conv_store",
    ...
}
```

The import happens in two phases:

1. **Category scan:** Walk through every sheet, extract all Short_Desc → Category_2 pairs, and create any missing subcategories in the database. This ensures that when Phase 2 tries to assign categories to transactions, every category already exists.

2. **Transaction import:** Walk through every sheet again, parse each row into a transaction, resolve its account and category, check for duplicates, and insert.

**Column normalization** handles the varying column names across formats:

```python
def _normalize_columns(columns):
    col_map = {}
    for col in columns:
        cl = str(col).lower().strip()
        if cl in ("trans_date", "trans. date", "date", "transaction date"):
            if "date" not in col_map:
                col_map["date"] = col
        elif cl == "amount":
            col_map["amount"] = col
        elif cl == "short_desc":
            col_map["short_desc"] = col
        elif cl == "specific category":
            col_map["specific_category"] = col
            if "short_desc" not in col_map:
                col_map["short_desc"] = col
        ...
    return col_map
```

**Sign normalization** is subtle. The app convention is positive = expense, negative = income. But bank account exports (checking, savings) use the opposite: positive = deposit, negative = debit. Credit card exports (Discover, Care Credit) use positive = purchase, which matches the app convention. American Express is an exception — it uses bank-style signs. The importer flips signs accordingly:

```python
needs_flip = (
    (account and account.account_type in ("checking", "savings"))
    or (account and account.institution == "amex")
)
if needs_flip:
    amount = -amount
```

**Deduplication** uses the same logic as the Plaid sync — matching on account, date, description, and amount:

```python
existing = db.query(Transaction).filter(
    Transaction.account_id == account.id,
    Transaction.date == txn_date,
    Transaction.description == description,
    Transaction.amount == amount,
).first()
if existing:
    result["skipped_duplicates"] += 1
    continue
```

This means you can safely import the same archive file twice — duplicates are skipped.

**Header detection.** Some Excel files have blank rows before the actual column headers. The `_fix_header_row` function scans the first 10 rows looking for recognizable column names (like "Amount" or "Date") and re-reads the sheet with the correct header row:

```python
def _fix_header_row(df, file_path, sheet_name):
    named_cols = [c for c in df.columns
                  if not str(c).startswith("Unnamed")]
    if len(named_cols) >= 2:
        return df  # Headers look fine

    known_headers = {"amount", "description", "date", "short_desc", ...}
    for i in range(min(10, len(df))):
        row_vals = {str(v).lower().strip() for v in df.iloc[i] if pd.notna(v)}
        if len(row_vals & known_headers) >= 2:
            return pd.read_excel(file_path, sheet_name=sheet_name, header=i+1)
    return df
```

### Archive Router (`backend/routers/archive.py`)

Three endpoints expose the import functionality:

- `GET /api/archive/scan` — Scans `~/BudgetApp/` for importable Excel and CSV files, returning them organized by year and type
- `POST /api/archive/import` — Imports a specific file, returning counts of imported, skipped, and uncategorized transactions
- `GET /api/archive/coverage` — Shows a coverage report: which years have data and from what sources (Plaid, archive, CSV)

The coverage endpoint is particularly useful — it shows you at a glance where your financial history has gaps:

```python
@router.get("/coverage")
def get_data_coverage(db):
    results = db.query(
        func.strftime("%Y", Transaction.date).label("year"),
        Transaction.source,
        func.count(Transaction.id).label("count"),
        func.min(Transaction.date).label("earliest"),
        func.max(Transaction.date).label("latest"),
    ).group_by(
        func.strftime("%Y", Transaction.date),
        Transaction.source,
    ).order_by(func.strftime("%Y", Transaction.date)).all()

    # Group by year, with per-source breakdowns
    ...
```

This might return something like: 2021 has 423 transactions from `archive_import`, 2022 has 891 from `archive_import`, 2023 has 1,247 from `archive_import`, 2024 has 890 from `archive_import` and 540 from `plaid`, and 2025 has 312 from `plaid`. That tells you exactly where your Plaid history starts and confirms the archives filled in everything before it.

---

## 6.7 Cost Optimization Strategy

Running an AI-powered financial app involves real API costs. Here's how Budget App minimizes them:

**Model selection by task.** The initial financial analysis uses Claude Sonnet ($3/$15 per million tokens), which has the reasoning depth to spot patterns and give nuanced advice. Follow-up questions use Claude Haiku ($0.25/$1.25 per million), which is fast enough for conversational responses. The typical cost for a full analysis session (one deep analysis plus 3–4 follow-ups) is under $0.05.

**Prompt caching.** The financial snapshot that goes in the system prompt averages 1,000–1,500 tokens. With `cache_control: ephemeral`, the first request in a conversation pays full price, but follow-ups get a 90% discount on the cached portion. For a five-message chat session, this saves roughly $0.02 — small individually, but it adds up with daily use.

**Server-side snapshot caching.** The five-minute TTL on the financial snapshot means that during an active chat session, the database is queried once, not once per message.

**Smart price fetching.** Stock prices are only refreshed during US market hours on weekdays. Outside those times, the scheduler doesn't even make the API call. The `yfinance` batch download fetches all tickers in a single request rather than one per security.

**Tiered categorization.** The three-tier categorization system means Claude (the most expensive tier) only gets called for transactions that can't be categorized by the free amount-based rules or merchant pattern matching. In practice, 60–80% of transactions are categorized before AI is ever involved.

---

## What's Next

With all features built, Part 7 wraps everything in an Electron desktop application and covers the build and packaging process — from `npm start` during development to a distributable `.dmg` file.

→ [Part 7: Electron Desktop App & Deployment](07-electron-and-deployment.md)
