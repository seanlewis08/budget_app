# Part 6 — Advanced Features

This part covers four advanced systems: AI-powered financial insights, investment portfolio tracking, the background sync scheduler, and the standalone sync daemon for scheduled background updates.

---

## 6.1 AI Financial Insights

The Insights feature uses Claude to analyze spending patterns and provide personalized financial advice through a chat interface with streaming responses.

### Backend (`backend/routers/insights.py`)

The insights system uses two Claude models:

- **Claude Sonnet 4.5** for the initial deep analysis (higher quality, more expensive)
- **Claude Haiku 4.5** for follow-up chat questions (faster, cheaper)

Both use Anthropic's prompt caching to reduce costs by ~90% on repeated calls with the same financial context.

#### Financial Snapshot

The `/api/insights/snapshot` endpoint builds a comprehensive financial snapshot from the database:

```python
@router.get("/snapshot")
def get_snapshot(db: Session = Depends(get_db)):
    """Build a financial snapshot for AI analysis."""
    # Last 6 months of spending by category
    # Monthly totals and trends
    # Top merchants by spend
    # Recurring charges
    # Income vs. expenses
    # Budget status
    return snapshot_data
```

The snapshot is cached server-side for 5 minutes to avoid redundant database queries.

#### Streaming Analysis

The `/api/insights/analyze` endpoint streams the AI analysis using Server-Sent Events (SSE):

```python
@router.post("/analyze")
async def analyze(body: dict, db: Session = Depends(get_db)):
    """Generate a full financial analysis using Claude Sonnet."""
    snapshot = _build_snapshot(db)
    context = body.get("context", "")  # Optional user context

    system_prompt = """You are a personal finance advisor analyzing spending data.
    Provide specific, actionable insights. Reference actual numbers from the data.
    Structure your analysis with clear sections:
    1. Spending Overview
    2. Notable Patterns
    3. Opportunities to Save
    4. Recommendations"""

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": f"Financial data:\n{json.dumps(snapshot)}\n\n"
                           f"Context: {context}\n\nAnalyze my finances.",
            }],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

#### Follow-up Chat

The `/api/insights/chat` endpoint handles conversational follow-ups using the same financial context but with the faster Haiku model:

```python
@router.post("/chat")
async def chat(body: dict, db: Session = Depends(get_db)):
    """Follow-up questions about finances using Claude Haiku."""
    snapshot = _build_snapshot(db)
    messages = body.get("messages", [])

    def generate():
        with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": f"You are a financial advisor. Data:\n{json.dumps(snapshot)}",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Frontend (`frontend/src/pages/Insights.jsx`)

The Insights page provides a full chat-like interface:

- **Context input**: User can provide personal context (e.g., "I'm saving for a house") before generating analysis
- **Streaming display**: Analysis text streams in real-time with a cursor indicator
- **Custom markdown renderer**: Handles headers, bold text, bullet lists, and dollar amount highlighting
- **Multi-turn chat**: Follow-up questions with conversation history
- **Persistence**: Analysis and chat history saved to `localStorage` so they survive page refreshes
- **Timestamps**: Shows when the last analysis was generated

The streaming handler on the frontend:

```jsx
const handleAnalyze = async () => {
  setIsAnalyzing(true)
  setAnalysis('')

  const response = await fetch('/api/insights/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ context }),
  })

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let fullText = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value)
    const lines = chunk.split('\n')

    for (const line of lines) {
      if (line.startsWith('data: ') && line !== 'data: [DONE]') {
        const data = JSON.parse(line.slice(6))
        fullText += data.text
        setAnalysis(fullText)
      }
    }
  }

  setIsAnalyzing(false)
  localStorage.setItem('insights_analysis', fullText)
}
```

---

## 6.2 Investment Portfolio Tracking

The investment system uses a separate SQLite database (`~/BudgetApp/investments.db`) to track holdings, prices, and investment transactions.

### Separate Database (`backend/investments_database.py`)

Mirrors the main database setup but points to `investments.db`:

```python
DB_DIR = Path.home() / "BudgetApp"
DB_PATH = DB_DIR / "investments.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={
    "check_same_thread": False,
    "timeout": 30,
})

# WAL mode + foreign keys (same as main DB)
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

InvestmentsSessionLocal = sessionmaker(bind=engine)
InvestmentsBase = declarative_base()
```

### Investment Models (`backend/models_investments.py`)

Four models track the investment portfolio:

**InvestmentAccount**: Links to the main Account table via `plaid_item_id` for access token reuse.

```python
class InvestmentAccount(InvestmentsBase):
    __tablename__ = "investment_accounts"

    id = Column(Integer, primary_key=True)
    plaid_item_id = Column(String(100))     # Links to Account.plaid_item_id
    account_name = Column(String(200))
    account_type = Column(String(50))       # taxable, roth, traditional_ira, 401k
    plaid_account_id = Column(String(100))
    last_synced_at = Column(DateTime)
    connection_status = Column(String(20), default="connected")
```

**Security**: Represents a financial instrument (stock, ETF, mutual fund).

```python
class Security(InvestmentsBase):
    __tablename__ = "securities"

    id = Column(Integer, primary_key=True)
    plaid_security_id = Column(String(100), unique=True)
    ticker = Column(String(20))           # nullable — some funds lack tickers
    name = Column(String(200))
    security_type = Column(String(50))    # stock, etf, mutual_fund, cash_equivalent
    sector = Column(String(100))
    close_price = Column(Float)
    close_price_as_of = Column(Date)
    price_source = Column(String(20))     # plaid, yfinance, manual
```

**Holding**: A position in a security. Daily snapshots enable performance charting.

```python
class Holding(InvestmentsBase):
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True)
    investment_account_id = Column(Integer, ForeignKey("investment_accounts.id"))
    security_id = Column(Integer, ForeignKey("securities.id"))
    quantity = Column(Float)
    cost_basis = Column(Float)
    cost_basis_per_unit = Column(Float)
    current_value = Column(Float)
    as_of_date = Column(Date)

    # Unique constraint enables daily snapshots
    __table_args__ = (
        UniqueConstraint("investment_account_id", "security_id", "as_of_date"),
    )
```

**InvestmentTransaction**: Buys, sells, dividends, and transfers.

```python
class InvestmentTransaction(InvestmentsBase):
    __tablename__ = "investment_transactions"

    id = Column(Integer, primary_key=True)
    investment_account_id = Column(Integer, ForeignKey("investment_accounts.id"))
    security_id = Column(Integer, ForeignKey("securities.id"))
    plaid_investment_transaction_id = Column(String(100), unique=True)
    date = Column(Date)
    type = Column(String(50))  # buy, sell, dividend, transfer, capital_gain, cash
    quantity = Column(Float)
    price = Column(Float)
    amount = Column(Float)
    fees = Column(Float)
```

### Plaid Investment Sync

The Plaid service reuses the access token from the main Account table (since both checking and investment accounts live under the same Plaid item for the same institution):

```python
def sync_investments(self, account, inv_db):
    """Sync investment holdings and transactions from Plaid."""
    access_token = self.decrypt_token(account.plaid_access_token)

    # 1. Fetch holdings
    response = self.client.investments_holdings_get(
        InvestmentsHoldingsGetRequest(access_token=access_token)
    )

    # 2. Upsert securities
    for sec in response.securities:
        existing = inv_db.query(Security).filter(
            Security.plaid_security_id == sec.security_id
        ).first()
        if existing:
            existing.close_price = sec.close_price
            existing.close_price_as_of = sec.close_price_as_of
        else:
            inv_db.add(Security(
                plaid_security_id=sec.security_id,
                ticker=sec.ticker_symbol,
                name=sec.name,
                security_type=sec.type,
                close_price=sec.close_price,
            ))

    # 3. Upsert holdings (today's snapshot)
    for holding in response.holdings:
        # Creates or updates today's holding snapshot
        ...

    # 4. Fetch investment transactions
    response = self.client.investments_transactions_get(
        InvestmentsTransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
        )
    )

    # 5. Deduplicate and insert
    for txn in response.investment_transactions:
        existing = inv_db.query(InvestmentTransaction).filter(
            InvestmentTransaction.plaid_investment_transaction_id == txn.investment_transaction_id
        ).first()
        if not existing:
            inv_db.add(InvestmentTransaction(...))

    inv_db.commit()
```

### Live Price Fetcher (`backend/services/price_fetcher.py`)

Fetches real-time stock prices using `yfinance` during market hours:

```python
import yfinance as yf
from datetime import datetime
import pytz

class PriceFetcher:
    @staticmethod
    def is_market_open():
        """Check if US stock market is currently open."""
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        if now.weekday() >= 5:  # Saturday/Sunday
            return False
        market_open = now.replace(hour=9, minute=30, second=0)
        market_close = now.replace(hour=16, minute=0, second=0)
        return market_open <= now <= market_close

    @staticmethod
    def fetch_all_prices(db):
        """Batch-fetch prices for all securities with tickers."""
        securities = db.query(Security).filter(
            Security.ticker.isnot(None)
        ).all()

        tickers = [s.ticker for s in securities]
        if not tickers:
            return

        # yfinance batch download
        data = yf.download(tickers, period="1d", progress=False)

        for security in securities:
            try:
                price = data['Close'][security.ticker].iloc[-1]
                security.close_price = float(price)
                security.close_price_as_of = datetime.now().date()
                security.price_source = "yfinance"
            except (KeyError, IndexError):
                continue

        db.commit()
```

### Investment API Endpoints (`backend/routers/investments.py`)

Key endpoints:

- `GET /api/investments/summary` — Portfolio totals: value, cost basis, gain/loss, day change
- `GET /api/investments/holdings` — All holdings with per-security metrics
- `GET /api/investments/performance?months=12` — Date series for the performance chart
- `GET /api/investments/allocation` — Breakdown by security type and sector
- `GET /api/investments/transactions` — Investment transaction history with type filtering
- `POST /api/investments/link-token` — Plaid link token with investments product
- `POST /api/investments/link/exchange` — Exchange token and create InvestmentAccount
- `POST /api/investments/accounts/{id}/sync` — Manual sync trigger
- `POST /api/investments/refresh-prices` — Manual price refresh via yfinance

### Frontend (`frontend/src/pages/Investments.jsx`)

The investments page has five sections stacked vertically:

1. **Portfolio Overview**: Stat cards showing total value, cost basis, gain/loss ($ and %), and day change
2. **Holdings Table**: Sortable by any column (ticker, shares, price, value, gain/loss, weight %). Green/red coloring on gain/loss columns
3. **Charts Row**: Performance line chart (portfolio vs. SPY benchmark) and allocation donut chart side by side
4. **Transaction History**: Filterable by type (buy, sell, dividend) with pagination
5. **Account Management**: Cards per investment account with sync buttons, plus "Link Investment Account" button for new Plaid connections

---

## 6.3 Background Sync Scheduler

The APScheduler-based scheduler runs three background jobs while the app is open:

### `backend/services/sync_scheduler.py`

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

def start_scheduler():
    """Start background sync jobs."""

    # Sync bank transactions every 4 hours
    scheduler.add_job(
        sync_all_accounts_job,
        'interval',
        hours=4,
        id='sync_transactions',
    )

    # Sync investment holdings every 6 hours
    scheduler.add_job(
        sync_investments_job,
        'interval',
        hours=6,
        id='sync_investments',
    )

    # Fetch stock prices every 30 min (weekdays, market hours only)
    scheduler.add_job(
        fetch_prices_job,
        'interval',
        minutes=30,
        id='fetch_prices',
    )

    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)


def sync_all_accounts_job():
    """Sync all connected bank accounts."""
    db = SessionLocal()
    plaid = PlaidService()
    accounts = db.query(Account).filter(
        Account.plaid_connection_status == "connected"
    ).all()
    for account in accounts:
        try:
            plaid.sync_transactions(account, db, trigger="scheduled")
        except Exception as e:
            logger.error(f"Scheduled sync failed for {account.name}: {e}")
    db.close()


def fetch_prices_job():
    """Refresh stock prices (only during market hours)."""
    if not PriceFetcher.is_market_open():
        return
    inv_db = InvestmentsSessionLocal()
    PriceFetcher.fetch_all_prices(inv_db)
    inv_db.close()
```

The scheduler is started during FastAPI's `lifespan` startup and stopped during shutdown.

---

## 6.4 Standalone Sync Daemon (`backend/sync_daemon.py`)

For syncing transactions when the app isn't open, a standalone daemon runs as a macOS LaunchAgent (or cron job):

```python
#!/usr/bin/env python3
"""
Budget App Sync Daemon — runs independently of the Electron app.
Designed for macOS LaunchAgent (or cron job) scheduling.
"""

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
            logger.info(f"  {account.name}: +{result['added']} new, "
                        f"{result['modified']} updated, {result['removed']} removed")
        except Exception as e:
            logger.error(f"  {account.name}: FAILED — {e}")
    db.close()


def backup_database():
    """Commit and push budget.db to a private Git repository."""
    # Stage, commit with descriptive message, push to origin
    ...


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously, syncing every 12 hours")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip Git backup after sync")
    args = parser.parse_args()

    if args.loop:
        while True:
            sync_all()
            if not args.no_backup:
                backup_database()
            time.sleep(12 * 3600)
    else:
        sync_all()
        if not args.no_backup:
            backup_database()
```

### macOS LaunchAgent Setup

To run the daemon automatically every 12 hours, create a LaunchAgent plist:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.seanlewis.budgetapp.sync</string>

    <key>ProgramArguments</key>
    <array>
        <string>/path/to/python3</string>
        <string>-m</string>
        <string>backend.sync_daemon</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/path/to/budget-app</string>

    <key>StartInterval</key>
    <integer>43200</integer>  <!-- 12 hours in seconds -->

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>~/BudgetApp/logs/sync.log</string>

    <key>StandardErrorPath</key>
    <string>~/BudgetApp/logs/sync.log</string>
</dict>
</plist>
```

Install and start the agent:

```bash
cp com.seanlewis.budgetapp.sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.seanlewis.budgetapp.sync.plist
```

The daemon writes to `~/BudgetApp/logs/sync.log` and syncs to the same `budget.db` used by the desktop app.

### Git Backup

The daemon can optionally back up `budget.db` to a private Git repository after each sync:

```bash
# One-time setup
cd ~/BudgetApp
git init
git remote add origin git@github.com:YOUR_USER/budget-app-data.git
echo "logs/" > .gitignore
git add .gitignore budget.db
git commit -m "Initial database backup"
git push -u origin main
```

After each sync, the daemon commits with a descriptive message:

```
Backup 2025-02-16 07:28 — 3247 transactions, 12.3 MB
```

---

## 6.5 Archive Import (`backend/routers/archive.py`)

For importing historical data from before Plaid was connected, the archive system handles Excel/CSV exports:

- `GET /api/archive/scan` — Scans `~/BudgetApp/` for importable files
- `POST /api/archive/import` — Imports an archive file with deduplication
- `GET /api/archive/coverage` — Shows data coverage by year and source

This enables building a complete financial history spanning years, even if Plaid was only connected recently.

---

## What's Next

With all features built, Part 7 wraps everything in an Electron desktop application and covers the build and packaging process.

→ [Part 7: Electron Desktop App & Deployment](07-electron-and-deployment.md)
