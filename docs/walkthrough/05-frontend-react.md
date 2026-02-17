# Part 5 — Frontend & React UI

The backend handles data and logic. Now we build what users actually see and interact with — the React frontend. This part covers the complete UI: the app shell with sidebar navigation, all thirteen pages, shared components, the design system, and how everything connects to the API endpoints we built in Parts 2–4.

The frontend uses React 18 with Vite, React Router 6 for navigation, Recharts for charts, Lucide React for icons, and `react-plaid-link` for the bank connection widget. There are no CSS frameworks — the entire design system is a single handwritten CSS file with CSS custom properties (variables) for theming.

---

## 5.1 Design System (`styles.css`)

Before building any components, let's establish the visual foundation. The entire app uses a dark theme defined through CSS custom properties on `:root`:

```css
:root {
  --bg-primary: #0f1117;
  --bg-secondary: #1a1d27;
  --bg-card: #222633;
  --bg-hover: #2a2e3d;
  --text-primary: #e8eaed;
  --text-secondary: #9aa0a6;
  --text-muted: #6b7280;
  --accent: #60a5fa;
  --accent-hover: #3b82f6;
  --green: #34d399;
  --green-bg: rgba(52, 211, 153, 0.1);
  --yellow: #fbbf24;
  --yellow-bg: rgba(251, 191, 36, 0.1);
  --red: #f87171;
  --red-bg: rgba(248, 113, 113, 0.1);
  --border: #2d3244;
  --radius: 8px;
  --radius-lg: 12px;
  --shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}
```

Every color in the app references these variables. This means you could switch to a light theme by changing just these twenty values. The semantic naming is deliberate: `--green` means "positive/success," `--red` means "negative/warning," and `--yellow` means "needs attention." Each semantic color has a corresponding `-bg` variant at 10% opacity, used for tinted background badges and alerts.

The layout is a two-column design: a fixed 240px sidebar on the left, and the main content area fills the remaining space with padding:

```css
.app {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 240px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
}

.main-content {
  margin-left: 240px;
  padding: 24px 32px;
  flex: 1;
  min-height: 100vh;
}
```

The sidebar is `position: fixed` so it stays in place as the main content scrolls. Cards — the primary container for content — use the `--bg-card` background with a subtle border:

```css
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
  margin-bottom: 16px;
}
```

Buttons come in three variants — primary (blue accent), secondary (subtle), and danger (red). All share the same base styles but differ in background and text color. The `.btn` class handles padding, border-radius, font size, and hover transitions.

The stats row — used on Spending, Budget, Cash Flow, and Data pages — is a horizontal row of stat cards using flexbox. Each stat card shows a label and a large value:

```css
.stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  flex: 1;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
}
```

Every page follows the same structure: a `.page-header` with title and subtitle, optional stat cards, then one or more `.card` containers with content. This consistency makes the app feel polished without needing a component library.

---

## 5.2 App Shell and Routing (`App.jsx`)

The top-level `App` component defines the layout structure and all routes. It wraps everything in a `BrowserRouter` from React Router:

```jsx
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom'

// Page imports
import ReviewQueue from './pages/ReviewQueue'
import Spending from './pages/Spending'
import Budget from './pages/Budget'
import Accounts from './pages/Accounts'
import Categories from './pages/Categories'
import Data from './pages/Data'
import CashFlow from './pages/CashFlow'
import RecurringMonitor from './pages/RecurringMonitor'
import Investments from './pages/Investments'
import Insights from './pages/Insights'
import SettingsPage from './pages/Settings'
import DeletedTransactions from './pages/DeletedTransactions'
import SyncHistory from './pages/SyncHistory'
```

### Sidebar

The sidebar component uses `NavLink` — React Router's version of an anchor tag that automatically adds an `active` class when the current URL matches:

```jsx
function Sidebar({ pendingCount }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <h1>Budget App</h1>
        <p>Personal Finance Tracker</p>
      </div>
      <ul className="nav-links">
        <li>
          <NavLink to="/" end>
            <CheckSquare size={18} />
            <span>Review Queue</span>
            {pendingCount > 0 && (
              <span className="badge">{pendingCount}</span>
            )}
          </NavLink>
        </li>
        <li><NavLink to="/spending"><TrendingUp size={18} /><span>Spending</span></NavLink></li>
        <li><NavLink to="/budget"><Wallet size={18} /><span>Budget</span></NavLink></li>
        <li><NavLink to="/cash-flow"><BarChart3 size={18} /><span>Cash Flow</span></NavLink></li>
        <li><NavLink to="/recurring"><Repeat size={18} /><span>Recurring</span></NavLink></li>
        <li><NavLink to="/investments"><LineChart size={18} /><span>Investments</span></NavLink></li>
        <li><NavLink to="/insights"><Sparkles size={18} /><span>Insights</span></NavLink></li>
        <li><NavLink to="/accounts"><Database size={18} /><span>Accounts</span></NavLink></li>
        <li><NavLink to="/data"><FolderTree size={18} /><span>Data</span></NavLink></li>
        <li><NavLink to="/categories"><FolderTree size={18} /><span>Categories</span></NavLink></li>
        <li><NavLink to="/settings"><Settings size={18} /><span>Settings</span></NavLink></li>
      </ul>
      <div className="sidebar-footer">v0.1.7</div>
    </nav>
  )
}
```

The Review Queue link shows a badge with the count of transactions needing attention (`pending_review` + `pending_save` statuses). This count is fetched by the parent `App` component and passed down.

### Route Definitions

The main `App` component renders the sidebar and a route switch:

```jsx
export default function App() {
  const [pendingCount, setPendingCount] = useState(0)

  const fetchPendingCount = useCallback(async () => {
    try {
      const res = await fetch('/api/transactions/pending-count')
      if (res.ok) {
        const data = await res.json()
        setPendingCount(data.count)
      }
    } catch (err) { /* ignore */ }
  }, [])

  useEffect(() => {
    fetchPendingCount()
  }, [fetchPendingCount])

  return (
    <BrowserRouter>
      <div className="app">
        <Sidebar pendingCount={pendingCount} />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<ReviewQueue onUpdate={fetchPendingCount} />} />
            <Route path="/spending" element={<Spending />} />
            <Route path="/budget" element={<Budget />} />
            <Route path="/cash-flow" element={<CashFlow />} />
            <Route path="/recurring" element={<RecurringMonitor />} />
            <Route path="/investments" element={<Investments />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/accounts" element={<Accounts onUpdate={fetchPendingCount} />} />
            <Route path="/data" element={<Data />} />
            <Route path="/categories" element={<Categories />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/deleted-transactions" element={<DeletedTransactions />} />
            <Route path="/sync-history" element={<SyncHistory />} />
            <Route path="/oauth-callback" element={<OAuthCallback />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
```

The `onUpdate` callback is passed to pages that can change the pending count — the Review Queue (when you confirm transactions) and Accounts (when a sync or CSV import brings in new transactions). When those pages finish an action, they call `onUpdate()` which re-fetches the count and updates the badge.

### The OAuth Callback Route

Plaid's OAuth flow redirects the browser to a callback URL after the user authenticates with their bank. The `OAuthCallback` component handles this by restoring the Plaid Link session from `sessionStorage` and completing the exchange:

```jsx
function OAuthCallback() {
  const navigate = useNavigate()

  useEffect(() => {
    const linkToken = sessionStorage.getItem('plaid_link_token')
    if (!linkToken) {
      navigate('/accounts')
    }
    // PlaidLink will reopen automatically with the receivedRedirectUri
  }, [navigate])

  const linkToken = sessionStorage.getItem('plaid_link_token')
  if (!linkToken) return null

  return (
    <PlaidLinkOpener
      token={linkToken}
      receivedRedirectUri={window.location.href}
      onSuccess={handleExchange}
      onExit={() => navigate('/accounts')}
    />
  )
}
```

This is only needed when running in Plaid's development or production environments where OAuth is required. In sandbox mode, the bank login happens in a modal and doesn't redirect.

---

## 5.3 Review Queue (`ReviewQueue.jsx`)

The Review Queue is the most important page in the app — it's where you categorize transactions. Every transaction that the categorization engine couldn't auto-confirm ends up here, waiting for human review.

### Fetching Transactions

The page calls `GET /api/transactions/review-queue` which returns transactions with status `pending_review` or `pending_save`:

```jsx
const fetchTransactions = async () => {
  const res = await fetch('/api/transactions/review-queue')
  if (res.ok) {
    const data = await res.json()
    // Separate into staged (pending_save) and pending (pending_review)
    setStaged(data.filter(t => t.status === 'pending_save'))
    setPending(data.filter(t => t.status === 'pending_review'))
  }
}
```

Transactions are split into two groups displayed separately:

**Staged** (yellow section at top): Transactions that have been assigned a category but not yet saved to the database. These are in the `pending_save` state. The user can review them and either commit all at once or kick individual ones back to pending.

**Pending** (main list below): Transactions waiting for initial categorization. Each one shows the AI's prediction (if available) with a question mark, and the user can accept the prediction or pick a different category.

### The Categorization Flow

Each transaction row shows the description, amount, account, and a category badge. Clicking the badge opens a `CategoryPicker` dropdown. When the user selects a category, this happens:

```jsx
const handleAccept = async (txnId, shortDesc) => {
  const res = await fetch(`/api/transactions/${txnId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category_short_desc: shortDesc }),
  })
  if (res.ok) {
    // Move from pending to staged
    fetchTransactions()
  }
}
```

The `POST /api/transactions/{id}/review` endpoint (from Part 4) updates the transaction's category and sets its status to `pending_save`. The transaction visually moves from the pending list to the staged section at the top.

### Batch Commit

The staged section has a "Save All" button that commits everything at once:

```jsx
const handleCommitAll = async () => {
  const res = await fetch('/api/transactions/commit-staged', {
    method: 'POST',
  })
  if (res.ok) {
    fetchTransactions()
    onUpdate()  // Refresh the sidebar badge count
  }
}
```

This calls the `POST /api/transactions/commit-staged` endpoint which flips all `pending_save` transactions to `confirmed`, creates merchant mappings for future auto-categorization, and returns a count of how many were committed.

### Batch Categorization

For bulk operations, the page has a "Batch Categorize" button that sends all pending transactions to Claude AI:

```jsx
const handleBatchCategorize = async () => {
  setCategorizing(true)
  const res = await fetch('/api/transactions/batch-categorize', {
    method: 'POST',
  })
  if (res.ok) {
    const data = await res.json()
    // data.categorized, data.already_done, data.failed
    fetchTransactions()
  }
  setCategorizing(false)
}
```

This sends uncategorized transactions to the 3-tier engine. Transactions that get auto-confirmed skip the queue entirely. The rest appear in the staged section with AI predictions for review.

---

## 5.4 The CategoryPicker Component (`components/CategoryPicker.jsx`)

The `CategoryPicker` is a shared dropdown used everywhere categories need to be selected — the Review Queue, the Data page, and bulk operations. It's worth examining separately because it's the most complex UI component in the app.

### Structure

It renders as a floating dropdown (absolutely positioned) that shows the full category tree — parent categories with expandable child categories:

```jsx
export default function CategoryPicker({ categoryTree, onSelect, onCancel, onTreeChanged }) {
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(new Set())
  const ref = useRef(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onCancel()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onCancel])
```

### Search Filtering

A search box at the top filters categories in real-time. The filtering is case-insensitive and matches against both parent and child display names. When searching, all matching parents auto-expand to show their matching children:

```jsx
const q = search.toLowerCase()
const filtered = q
  ? categoryTree.map(parent => ({
      ...parent,
      children: parent.children.filter(child =>
        child.display_name.toLowerCase().includes(q)
      ),
      parentMatch: parent.display_name.toLowerCase().includes(q),
    })).filter(pg => pg.parentMatch || pg.children.length > 0)
  : categoryTree
```

### Inline Category Creation

At the bottom of the dropdown is a "Create new subcategory" section. The user types a name, selects a parent, and clicks create. This calls `POST /api/categories/` to create the category, then triggers `onTreeChanged` so the dropdown refreshes with the new option. This means you never have to leave the categorization flow to create a missing category.

### How it's Used

Every place that needs category selection renders the same component:

```jsx
// In ReviewQueue — single transaction
<CategoryPicker
  categoryTree={categoryTree}
  onSelect={(shortDesc) => handleAccept(txn.id, shortDesc)}
  onCancel={() => setEditingId(null)}
  onTreeChanged={fetchCategories}
/>

// In Data page — bulk operation
<CategoryPicker
  categoryTree={categoryTree}
  onSelect={bulkAssignCategory}
  onCancel={() => setBulkPickerOpen(false)}
  onTreeChanged={fetchCategories}
/>
```

The `onSelect` callback receives the `short_desc` string of the chosen category, which is what the API expects for category assignment.

---

## 5.5 Spending Page (`Spending.jsx`)

The Spending page is the primary analytics dashboard. It shows where your money goes, broken down by category, with charts and a detailed table.

### Data Fetching

The page fetches spending data from the analytics endpoint we built in Part 4:

```jsx
const fetchSpending = async () => {
  const params = new URLSearchParams()
  if (selectedMonth) {
    params.set('start_date', `${selectedMonth}-01`)
    // Calculate end of month
    const [year, month] = selectedMonth.split('-').map(Number)
    const lastDay = new Date(year, month, 0).getDate()
    params.set('end_date', `${selectedMonth}-${lastDay}`)
  }
  if (selectedAccountId) params.set('account_id', selectedAccountId)

  const res = await fetch(`/api/transactions/spending-by-category?${params}`)
  if (res.ok) {
    const data = await res.json()
    setSpendingData(data)
  }
}
```

The `GET /api/transactions/spending-by-category` endpoint returns spending grouped by parent category, with subcategory breakdowns and totals.

### Charts

The page uses Recharts to render two visualizations:

**Pie Chart** — Shows the proportion of spending per category. Each slice uses the category's color from the database:

```jsx
<PieChart>
  <Pie
    data={chartData}
    dataKey="total"
    nameKey="category"
    innerRadius={60}
    outerRadius={100}
  >
    {chartData.map((entry, i) => (
      <Cell key={i} fill={entry.color} />
    ))}
  </Pie>
  <Tooltip formatter={(val) => formatCurrency(val)} />
</PieChart>
```

**Bar Chart** — Shows monthly spending trends using `GET /api/transactions/monthly-trend`:

```jsx
<BarChart data={trendData}>
  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
  <XAxis dataKey="month" stroke="var(--text-muted)" />
  <YAxis stroke="var(--text-muted)" tickFormatter={val => `$${val}`} />
  <Tooltip />
  <Bar dataKey="total" fill="var(--accent)" radius={[4, 4, 0, 0]} />
</BarChart>
```

### Expandable Category Rows

Below the charts is a table of spending by category. Each parent category row is expandable — clicking it reveals the subcategory breakdown:

```jsx
{spendingData.map(cat => (
  <div key={cat.category}>
    <div className="spending-row" onClick={() => toggleExpand(cat.category)}>
      <span className="color-dot" style={{ background: cat.color }} />
      <span className="name">{cat.category}</span>
      <span className="amount">{formatCurrency(cat.total)}</span>
      <ChevronRight className={expanded.has(cat.category) ? 'rotated' : ''} />
    </div>
    {expanded.has(cat.category) && cat.subcategories.map(sub => (
      <div key={sub.name} className="spending-sub-row">
        <span className="name">{sub.name}</span>
        <span className="amount">{formatCurrency(sub.total)}</span>
      </div>
    ))}
  </div>
))}
```

The color dot next to each category name uses the `color` field from the Category model, giving visual consistency between the pie chart and the table.

---

## 5.6 Cash Flow Page (`CashFlow.jsx`)

The Cash Flow page shows income vs. expenses over time using a line chart. It fetches data from `GET /api/transactions/cash-flow`:

```jsx
const fetchCashFlow = async () => {
  const params = new URLSearchParams()
  if (selectedYear) {
    params.set('start_date', `${selectedYear}-01-01`)
    params.set('end_date', `${selectedYear}-12-31`)
  }
  const res = await fetch(`/api/transactions/cash-flow?${params}`)
  if (res.ok) setCashFlowData(await res.json())
}
```

The API returns monthly totals with `income`, `expenses`, and `net` for each month. The chart renders two lines (income in green, expenses in red) with the net shown in stat cards above:

```jsx
<LineChart data={cashFlowData}>
  <Line type="monotone" dataKey="income" stroke="var(--green)" strokeWidth={2} />
  <Line type="monotone" dataKey="expenses" stroke="var(--red)" strokeWidth={2} />
  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
  <XAxis dataKey="month" />
  <YAxis tickFormatter={val => `$${Math.abs(val)}`} />
  <Tooltip />
</LineChart>
```

The stat cards at the top show total income, total expenses, and net savings for the selected period.

---

## 5.7 Budget Page (`Budget.jsx`)

The Budget page lets users set monthly spending targets and tracks progress against them. It's one of the simpler pages — no charts library, just custom CSS progress bars.

### Fetching Budgets

```jsx
const fetchBudgets = async () => {
  const res = await fetch(`/api/budgets/?month=${selectedMonth}`)
  if (res.ok) setBudgets(await res.json())
}
```

The `GET /api/budgets/?month=YYYY-MM` endpoint (from the budgets router) returns each budget with `budgeted`, `spent`, `remaining`, and `percent_used` fields pre-calculated by the backend.

### Adding a Budget

Users pick a parent category and enter a dollar amount:

```jsx
const addBudget = async () => {
  const res = await fetch('/api/budgets/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      category_short_desc: newBudget.category_short_desc,
      month: selectedMonth,
      amount: parseFloat(newBudget.amount),
    }),
  })
  if (res.ok) fetchBudgets()
}
```

### Progress Bars

Each budget renders as a horizontal bar showing spending progress:

```jsx
const getBarColor = (percent) => {
  if (percent >= 100) return 'red'
  if (percent >= 75) return 'yellow'
  return 'green'
}

<div className="budget-bar">
  <div
    className={`budget-bar-fill ${getBarColor(budget.percent_used)}`}
    style={{ width: `${Math.min(budget.percent_used, 100)}%` }}
  />
</div>
```

The bar turns yellow at 75% and red at 100%. The remaining amount is displayed to the right — green if under budget, red if over.

---

## 5.8 Recurring Monitor (`RecurringMonitor.jsx`)

The Recurring Monitor shows month-by-month spending for categories flagged as recurring (subscriptions, rent, utilities, etc.). It fetches data from `GET /api/transactions/recurring-monitor`:

```jsx
const fetchRecurringData = async () => {
  const res = await fetch(`/api/transactions/recurring-monitor?year=${year}`)
  if (res.ok) setData(await res.json())
}
```

The API returns a matrix: each row is a recurring subcategory, each column is a month, and each cell is the total spent that month. The frontend renders this as a horizontally scrolling table.

### Category Filter

The page includes a custom category filter dropdown that lets you show/hide individual recurring categories. This uses a checkbox-tree UI:

```jsx
function CategoryFilterDropdown({ recurringParents, enabledCategories, ... }) {
  // Each parent row has a checkbox with three states:
  // checked (all children enabled), unchecked (none), indeterminate (some)
  <input
    type="checkbox"
    checked={allChecked}
    ref={el => { if (el) el.indeterminate = someChecked && !allChecked }}
    onChange={() => toggleParentCheckbox(parent)}
  />
}
```

The `indeterminate` state on the checkbox is set via a `ref` callback because HTML doesn't have an `indeterminate` attribute — you can only set it through JavaScript.

### Month-over-Month Changes

Each cell in the table shows not just the amount but also a visual indicator if the amount changed significantly from the previous month. This helps catch subscription price increases or unexpected charges.

---

## 5.9 Accounts Page (`Accounts.jsx`)

The Accounts page handles three things: managing bank accounts, connecting to Plaid, and importing CSV files.

### Account Cards

Each account renders as a card showing its name, type (checking/savings/credit), connection status, balance, last sync time, transaction count, and date coverage:

```jsx
function AccountCard({ account, onRefresh }) {
  const Icon = accountIcons[account.account_type] || Landmark
  const status = statusColors[account.plaid_connection_status]
  const isConnected = account.plaid_connection_status === 'connected'

  return (
    <div className="acct-card">
      <div className="acct-card-header">
        <Icon size={20} />
        <div className="acct-card-info">
          <div className="acct-card-name">{account.name}</div>
          <div className="acct-card-type">{account.account_type}</div>
        </div>
        <div className="acct-status-badge" style={statusStyles}>
          {isConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
          {account.plaid_connection_status}
        </div>
      </div>
      {/* Balances, sync info, action buttons */}
    </div>
  )
}
```

Connected accounts show Sync Now, Refresh Balances, and Disconnect buttons. Disconnected accounts show a Link Bank button that initiates the Plaid flow.

### The Plaid Link Button

Connecting a bank account is a two-step process:

1. **Create a link token** by calling `POST /api/accounts/link/token` — this gives us a one-time-use token from Plaid.
2. **Open Plaid Link** — the `react-plaid-link` library opens a modal where the user logs into their bank.
3. **Exchange the token** — when the user completes the bank login, Plaid gives us a `public_token`. We send it to `POST /api/accounts/link/exchange` which converts it to a permanent `access_token`.

The implementation splits this into two components to handle a React hooks constraint:

```jsx
function PlaidLinkButton({ accountId, onSuccess }) {
  const [linkToken, setLinkToken] = useState(null)

  const fetchLinkToken = async () => {
    const res = await fetch('/api/accounts/link/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accountId }),
    })
    const data = await res.json()
    if (res.ok) setLinkToken(data.link_token)
  }

  return (
    <>
      <button onClick={fetchLinkToken}>Link Bank</button>
      {linkToken && (
        <PlaidLinkOpener token={linkToken} onSuccess={onSuccess} />
      )}
    </>
  )
}

function PlaidLinkOpener({ token, onSuccess, onExit }) {
  const { open, ready } = usePlaidLink({ token, onSuccess, onExit })
  useEffect(() => { if (ready) open() }, [ready, open])
  return null  // Renders nothing — just triggers Plaid Link
}
```

The `PlaidLinkOpener` is a separate component because `usePlaidLink` is a hook that must be called unconditionally. We only mount `PlaidLinkOpener` after we have a token, which triggers the `useEffect` to open the Plaid modal.

If the user's Plaid credentials aren't configured, the button shows a helpful error message explaining how to add them to `~/BudgetApp/.env` and suggesting CSV import as an alternative.

### CSV Import

Below the account cards is a drag-and-drop CSV upload zone:

```jsx
<div
  className="upload-zone"
  onDragOver={(e) => e.preventDefault()}
  onDrop={handleDrop}
  onClick={() => fileRef.current?.click()}
>
  <Upload size={40} />
  <p>Drop a CSV file here or click to browse</p>
</div>
```

The upload supports two modes:

- **Auto-detect** (default) — calls `POST /api/import/csv/auto-detect` which examines the CSV headers and matches against known bank formats.
- **Manual selection** — the user picks their bank from a dropdown, which calls `POST /api/import/csv?bank={name}` with the specific parser.

After upload, it shows a success message with import counts (new transactions, skipped duplicates, detected bank format) or an error message.

### Add Account Form

Users can also create accounts manually (for CSV-only use) via an inline form that calls `POST /api/accounts/`:

```jsx
function AddAccountForm({ onCreated, onCancel }) {
  const handleSubmit = async (e) => {
    e.preventDefault()
    const res = await fetch('/api/accounts/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.trim(),
        institution: institution.trim().toLowerCase(),
        account_type: accountType,
      }),
    })
    if (res.ok) onCreated(await res.json())
  }
  // Name, institution, type (checking/savings/credit) inputs
}
```

---

## 5.10 Data Page (`Data.jsx`)

The Data page is a full transaction browser — a paginated, filterable, sortable table of every transaction in the database. Think of it as the raw data view compared to the Spending page's analytical view.

### Filter System

The page offers five filters that all compose together:

```jsx
// Year selector (in the header)
<select value={selectedYear} onChange={handleYearChange}>
  <option value="">All Years</option>
  {availableYears.map(y => <option key={y.year} value={y.year}>{y.year}</option>)}
</select>

// Account, source, category, and search (in the card header)
<select value={selectedAccountId} onChange={handleAccountChange}>...</select>
<select value={selectedSource} onChange={...}>
  <option value="">All Sources</option>
  <option value="plaid_sync">Plaid</option>
  <option value="csv_import">CSV</option>
  <option value="archive_import">Archive</option>
</select>
<DataCategoryFilter categoryTree={categoryTree} value={selectedCategory} onChange={...} />
<input type="text" placeholder="Search descriptions..." onChange={handleSearchInput} />
```

Available years come from `GET /api/transactions/years`. The account dropdown filters to only show accounts that have data in the selected year.

All filters are persisted to `sessionStorage` so they survive page navigation (but not browser close). Search uses a debounced input — it waits 300ms after the user stops typing before fetching:

```jsx
const handleSearchInput = (val) => {
  setSearchInput(val)
  clearTimeout(searchTimerRef.current)
  searchTimerRef.current = setTimeout(() => {
    setSearch(val)
    setOffset(0)
  }, 300)
}
```

### Multi-Select and Bulk Actions

Rows can be selected individually (click) or in ranges (shift-click):

```jsx
const toggleSelect = (id, e) => {
  const currentIndex = sortedTransactions.findIndex(t => t.id === id)
  if (e?.shiftKey && lastClickedIndexRef.current != null) {
    // Select range between last click and current
    const start = Math.min(lastClickedIndexRef.current, currentIndex)
    const end = Math.max(lastClickedIndexRef.current, currentIndex)
    const rangeIds = sortedTransactions.slice(start, end + 1).map(t => t.id)
    setSelectedIds(prev => {
      const next = new Set(prev)
      rangeIds.forEach(rid => next.add(rid))
      return next
    })
  } else {
    // Toggle single selection
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  lastClickedIndexRef.current = currentIndex
}
```

When transactions are selected, a bulk action bar appears with "Categorize" and "Delete" buttons. Bulk categorize opens the `CategoryPicker` and applies the chosen category to all selected transactions via `POST /api/transactions/bulk-review`. Bulk delete calls `POST /api/transactions/bulk-delete`.

### Inline Category Editing

Each transaction's category cell is clickable. Clicking it opens a `CategoryPicker` dropdown anchored to that cell, allowing you to change the category without leaving the page:

```jsx
<span
  className="data-cat-badge clickable"
  onClick={() => setEditingTxnId(editingTxnId === txn.id ? null : txn.id)}
>
  {txn.category_name || (txn.predicted_category_name ? `${txn.predicted_category_name}?` : '—')}
</span>
{editingTxnId === txn.id && (
  <CategoryPicker
    categoryTree={categoryTree}
    onSelect={(shortDesc) => handleCategoryChange(txn.id, shortDesc)}
    onCancel={() => setEditingTxnId(null)}
  />
)}
```

Predicted categories (from the AI) show with a `?` suffix and a different visual style to distinguish them from confirmed categories.

---

## 5.11 Categories Page (`Categories.jsx`)

The Categories page provides a tree editor for managing the category hierarchy. It's the administrative interface for the `Category` model.

### Tree Rendering

Categories are displayed as an expandable tree. Parent categories (those without a `parent_id`) show at the top level. Clicking the arrow expands to show subcategories:

```jsx
{categoryTree.map(parent => (
  <div key={parent.id} className="cat-tree-parent">
    <div className="cat-tree-row" onClick={() => toggleExpand(parent.id)}>
      {expanded.has(parent.id) ? <ChevronDown /> : <ChevronRight />}
      <span className="cat-color-dot" style={{ background: parent.color }} />
      <span className="cat-name">{parent.display_name}</span>
      <span className="cat-short-desc">{parent.short_desc}</span>
      <div className="cat-actions">
        <button onClick={() => startEdit(parent)}>
          <Pencil size={14} />
        </button>
        <button onClick={() => startAddChild(parent)}>
          <Plus size={14} />
        </button>
      </div>
    </div>
    {expanded.has(parent.id) && parent.children.map(child => (
      <div key={child.id} className="cat-tree-child">
        {/* Child row with edit, move, delete buttons */}
      </div>
    ))}
  </div>
))}
```

### Inline Editing

Clicking the edit button on a category replaces the row with an inline form (`CategoryForm`) that lets you change the display name, short key, color, and flags (is_recurring, is_income):

```jsx
function CategoryForm({ initial, isSubcategory, onSave, onCancel }) {
  const [displayName, setDisplayName] = useState(initial?.display_name || '')
  const [shortDesc, setShortDesc] = useState(initial?.short_desc || '')
  const [autoSlug, setAutoSlug] = useState(!initial)

  const handleDisplayNameChange = (val) => {
    setDisplayName(val)
    if (autoSlug) {
      // Auto-generate short_desc from display name
      setShortDesc(val.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''))
    }
  }
}
```

For new categories, the `short_desc` is auto-generated from the display name as you type (e.g., "Coffee Shops" → "coffee_shops"). Once you manually edit the short_desc, auto-generation stops.

### Move to Parent

Subcategories can be moved between parent categories using a dropdown picker. This calls `PATCH /api/categories/{id}` with the new `parent_id`, which triggers a re-render of the tree.

### Collapse/Expand All

Buttons at the top let you collapse or expand all parent categories at once, useful when the tree gets large.

---

## 5.12 Investments Page (`Investments.jsx`)

The Investments page tracks your investment portfolio using the separate `investments.db` database. It shows account summaries, holdings by account, allocation charts, and recent investment transactions.

### Data Fetching

The page fetches from three endpoints:

```jsx
const fetchData = async () => {
  const [acctRes, holdingsRes, txnRes] = await Promise.all([
    fetch('/api/investments/accounts'),
    fetch('/api/investments/holdings'),
    fetch('/api/investments/transactions?limit=50'),
  ])
  if (acctRes.ok) setAccounts(await acctRes.json())
  if (holdingsRes.ok) setHoldings(await holdingsRes.json())
  if (txnRes.ok) setTransactions(await txnRes.json())
}
```

### Portfolio Summary

Stat cards show total portfolio value, today's change (dollar and percent), and total cost basis. Each value is formatted with color coding — green for gains, red for losses:

```jsx
<div className="stat-card">
  <div className="label">Total Value</div>
  <div className="value">{fmt(totalValue)}</div>
</div>
<div className="stat-card">
  <div className="label">Today's Change</div>
  <div className={`value ${todayChange >= 0 ? 'green' : 'red'}`}>
    {fmtSigned(todayChange)} ({fmtPct(todayChangePct)})
  </div>
</div>
```

### Holdings Table

Holdings are grouped by account and sorted by current value. Each row shows the ticker symbol, quantity, cost basis, current value, and gain/loss:

```jsx
{holdings.map(h => (
  <tr key={h.id}>
    <td className="ticker">{h.ticker_symbol}</td>
    <td>{fmtShares(h.quantity)}</td>
    <td>{fmt(h.cost_basis)}</td>
    <td>{fmt(h.current_value)}</td>
    <td className={h.gain_loss >= 0 ? 'green' : 'red'}>
      {fmtSigned(h.gain_loss)} ({fmtPct(h.gain_loss_pct)})
    </td>
  </tr>
))}
```

### Allocation Pie Chart

A Recharts `PieChart` shows asset allocation by holding:

```jsx
<PieChart>
  <Pie data={allocationData} dataKey="value" nameKey="ticker">
    {allocationData.map((_, i) => (
      <Cell key={i} fill={COLORS[i % COLORS.length]} />
    ))}
  </Pie>
</PieChart>
```

### Adding Investment Accounts

The page supports both Plaid-linked and manual investment accounts. Manual entry lets you create an account and add holdings with ticker, quantity, and cost basis. The backend's price fetcher then automatically looks up current prices from Yahoo Finance.

---

## 5.13 Insights Page (`Insights.jsx`)

The Insights page is the AI-powered financial advisor. It uses Server-Sent Events (SSE) to stream Claude's analysis in real-time.

### Running an Analysis

The user clicks "Run Analysis" which streams from `POST /api/insights/analyze`:

```jsx
const runAnalysis = async () => {
  setAnalyzing(true)
  setAnalysis('')

  let fullText = ''
  await streamFromEndpoint(
    '/api/insights/analyze',
    { context: userContext },
    (token) => {       // onToken: append each chunk
      fullText += token
      setAnalysis(fullText)
    },
    () => {            // onDone: finalize
      setAnalyzing(false)
      setChatHistory([{ role: 'assistant', content: fullText }])
    },
    (errMsg) => {      // onError
      setError(errMsg)
      setAnalyzing(false)
    },
  )
}
```

### SSE Streaming

The `streamFromEndpoint` helper reads from the response body as a stream and parses SSE events:

```jsx
const streamFromEndpoint = async (url, body, onToken, onDone, onError) => {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim()
        if (data === '[DONE]') { onDone(); return }
        const event = JSON.parse(data)
        if (event.type === 'text') onToken(event.content)
        if (event.type === 'error') { onError(event.content); return }
      }
    }
  }
  onDone()
}
```

This reads the response as a stream of chunks, buffers them until it has complete lines, and parses each `data:` line as a JSON event. The text appears progressively in the UI as Claude generates it.

### Markdown Rendering

The `renderMarkdown` function converts Claude's response (which uses markdown) into React elements:

```jsx
function renderMarkdown(text) {
  const lines = text.split('\n')
  // Handles: ## headers → <h3>
  //          **bold** → <strong>
  //          - bullets → <ul><li>
  //          $amounts → colored <span>
  for (const line of lines) {
    if (trimmed.startsWith('## ')) {
      elements.push(<h3 className="insights-section-header">{trimmed.slice(3)}</h3>)
    }
    // ... etc
  }
}
```

Dollar amounts are auto-highlighted: positive amounts (prefixed with `+$`) get green styling, negative amounts get red.

### Follow-up Chat

After the initial analysis, a chat interface appears. Users can ask follow-up questions ("What if I cancel Netflix?", "How much am I spending on groceries?") which stream from `POST /api/insights/chat`:

```jsx
const sendMessage = async () => {
  const newHistory = [...chatHistory, { role: 'user', content: chatInput }]
  setChatHistory(newHistory)

  await streamFromEndpoint(
    '/api/insights/chat',
    { message: chatInput, history: chatHistory, context: userContext },
    (token) => setChatStreamText(prev => prev + token),
    () => setChatHistory(prev => [...prev, { role: 'assistant', content: responseText }]),
    (errMsg) => { /* handle error */ },
  )
}
```

The chat sends the full conversation history so Claude has context. Analysis and chat are persisted to `localStorage` so they survive page navigation.

---

## 5.14 Settings Page (`Settings.jsx`)

The Settings page is where users configure API keys and app preferences without needing to edit files.

### Loading and Saving

Settings are fetched from `GET /api/settings/` and saved to `POST /api/settings/`:

```jsx
const loadSettings = async () => {
  const res = await fetch('/api/settings/')
  if (res.ok) {
    const data = await res.json()
    for (const [key, info] of Object.entries(data)) {
      newSettings[key] = info.value || ''
      meta[key] = { is_set: info.is_set, source: info.source }
    }
  }
}

const handleSave = async () => {
  const payload = {}
  for (const key of dbKeys) {
    payload[key] = settings[key]
  }
  await fetch('/api/settings/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings: payload }),
  })
}
```

### Source Badges

Each setting shows a badge indicating where its current value comes from:

```jsx
const sourceLabel = (key) => {
  const meta = settingsMeta[key]
  if (meta.source === 'database') return <span className="settings-source-badge db">Saved in app</span>
  if (meta.source === 'env') return <span className="settings-source-badge env">From .env file</span>
  return <span className="settings-source-badge none">Not set</span>
}
```

This helps users understand whether a value was saved through the UI, loaded from a `.env` file, or isn't configured at all.

### Settings Sections

The page is organized into cards:

- **Plaid** — Client ID, sandbox/production secrets, environment, recovery code, encryption key
- **AI Categorization** — Anthropic API key, auto-confirm threshold
- **Email Notifications** — Enable/disable toggle, Gmail address, app password, batch interval (Phase 3 — not fully implemented yet)
- **Database** — Shows the database location (`~/BudgetApp/budget.db`) as read-only info

At the bottom, a link to **Deleted Transactions** shows a badge with the count of soft-deleted transactions.

---

## 5.15 Supporting Pages

Three smaller pages round out the frontend:

### Deleted Transactions (`DeletedTransactions.jsx`)

Accessed from Settings, this page lists all soft-deleted transactions (stored in the `DeletedTransaction` model). Users can restore individual transactions (moves them back to the `Transaction` table) or purge them permanently. It supports multi-select with shift-click for bulk operations.

### Sync History (`SyncHistory.jsx`)

Accessed from the Accounts page, this shows a chronological log of all Plaid sync operations. Each entry shows the account name, trigger type (scheduled, manual, initial), result (success/error), transaction counts (added/modified/removed), and duration. Entries are grouped by date.

### OAuth Callback

A minimal page (defined inline in `App.jsx`) that handles Plaid's OAuth redirect by restoring the link session and completing the token exchange.

---

## 5.16 Frontend Entry Point (`main.jsx`)

The entry point is minimal — it mounts the React app and imports the global stylesheet:

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

`React.StrictMode` is a development-only wrapper that helps catch common bugs by double-invoking effects and render functions. It has no effect in production builds.

---

## 5.17 Common Patterns Across Pages

Several patterns repeat throughout the frontend worth noting:

### Utility Functions

Nearly every page defines local helper functions for formatting:

```jsx
function formatCurrency(amount) {
  if (amount == null) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD'
  }).format(amount)
}

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric'
  })
}
```

The `+ 'T00:00:00'` on date strings prevents timezone offset issues — without it, `new Date('2024-01-15')` would be interpreted as UTC midnight, which could show as the previous day in Western Hemisphere timezones.

### Fetch Pattern

Every API call follows the same pattern:

```jsx
const fetchSomething = async () => {
  try {
    const res = await fetch('/api/something')
    if (res.ok) {
      const data = await res.json()
      setSomething(data)
    }
  } catch (err) {
    console.error('Failed:', err)
  }
}

useEffect(() => { fetchSomething() }, [])
```

All URLs use relative paths starting with `/api/` — in development, Vite's proxy (from Part 1) forwards these to the FastAPI backend. In production, Electron serves both frontend and backend from the same origin, so relative paths work naturally.

### Optimistic Updates

Several pages update local state immediately after a successful API call rather than re-fetching:

```jsx
const handleCategoryChange = async (txnId, shortDesc) => {
  const res = await fetch(`/api/transactions/${txnId}/review`, { ... })
  if (res.ok) {
    // Update local state instead of re-fetching
    setTransactions(prev =>
      prev.map(txn =>
        txn.id === txnId
          ? { ...txn, category_name: displayName, status: 'confirmed' }
          : txn
      )
    )
  }
}
```

This makes the UI feel instant — the change appears immediately without waiting for a full data refresh.

---

## What's Next

With the frontend complete, Part 6 covers the advanced features that tie everything together: the financial advisor backend, investment syncing and price fetching, budget and notification systems, and the archive importer. These features build on the foundation of Parts 2–5 to add the intelligence that makes the app genuinely useful.

→ [Part 6: Advanced Features](06-advanced-features.md)
