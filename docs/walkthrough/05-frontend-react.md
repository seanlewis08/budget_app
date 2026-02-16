# Part 5 — Frontend & React UI

This part covers the entire React frontend: the app shell, routing, all 13+ pages, shared components, and CSS styling. The frontend uses React 18, React Router 6, Recharts for data visualization, and Lucide React for icons.

---

## 5.1 App Shell and Routing (`App.jsx`)

The app has a fixed sidebar navigation and a main content area. The top-level `App` component wraps everything in a `BrowserRouter`:

```jsx
import React, { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import { usePlaidLink } from 'react-plaid-link'
import {
  LayoutDashboard, CheckSquare, TrendingUp, Wallet, Settings,
  FolderTree, Database, BarChart3, Repeat, LineChart, Sparkles
} from 'lucide-react'

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

The sidebar uses `NavLink` for active-state highlighting and shows a badge with the count of pending + staged transactions:

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
            Review Queue
            {pendingCount > 0 && (
              <span className="badge">{pendingCount}</span>
            )}
          </NavLink>
        </li>
        <li><NavLink to="/spending"><TrendingUp size={18} />Spending</NavLink></li>
        <li><NavLink to="/cash-flow"><BarChart3 size={18} />Cash Flow</NavLink></li>
        <li><NavLink to="/recurring"><Repeat size={18} />Recurring</NavLink></li>
        <li><NavLink to="/budget"><Wallet size={18} />Budget</NavLink></li>
        <li><NavLink to="/accounts"><LayoutDashboard size={18} />Accounts</NavLink></li>
        <li><NavLink to="/investments"><LineChart size={18} />Investments</NavLink></li>
        <li><NavLink to="/insights"><Sparkles size={18} />Insights</NavLink></li>
        <li><NavLink to="/data"><Database size={18} />Data</NavLink></li>
        <li><NavLink to="/categories"><FolderTree size={18} />Categories</NavLink></li>
        <li><NavLink to="/settings"><Settings size={18} />Settings</NavLink></li>
      </ul>
    </nav>
  )
}
```

### Stats Polling

The `AppContent` component polls `/api/stats` every 30 seconds to keep the sidebar badge up to date:

```jsx
function AppContent() {
  const [stats, setStats] = useState({
    total_transactions: 0,
    pending_review: 0,
    pending_save: 0,
    confirmed: 0,
  })

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/stats')
      if (res.ok) setStats(await res.json())
    } catch (err) {
      console.error('Failed to fetch stats:', err)
    }
  }

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="app">
      <Sidebar pendingCount={stats.pending_review + (stats.pending_save || 0)} />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<ReviewQueue stats={stats} onUpdate={fetchStats} />} />
          <Route path="/spending" element={<Spending />} />
          <Route path="/cash-flow" element={<CashFlow />} />
          <Route path="/recurring" element={<RecurringMonitor />} />
          <Route path="/budget" element={<Budget />} />
          <Route path="/accounts" element={<Accounts onUpdate={fetchStats} />} />
          <Route path="/investments" element={<Investments />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/data" element={<Data />} />
          <Route path="/categories" element={<Categories />} />
          <Route path="/oauth-callback" element={<OAuthCallback />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/deleted-transactions" element={<DeletedTransactions />} />
          <Route path="/sync-history" element={<SyncHistory />} />
        </Routes>
      </main>
    </div>
  )
}
```

---

## 5.2 Review Queue (`ReviewQueue.jsx`)

The primary workflow page. This is where users spend most of their time categorizing incoming transactions.

**Features (948 lines):**

- **Pending section**: Transactions awaiting categorization, shown with AI predictions and confidence badges
- **Staged section**: Transactions that have been categorized but not yet committed
- **CategoryPicker**: A hierarchical dropdown component that shows parent → child categories
- **Batch categorization**: Select multiple transactions (with shift-click range selection), pick a category, and categorize all at once
- **Sort control**: Toggle between newest-first and oldest-first
- **Search**: Filter pending transactions by description text
- **Category filter**: Filter to show only transactions predicted for a specific category
- **Confidence indicators**: Color-coded badges showing how certain the AI prediction is

The two-phase review pattern works like this:

1. User clicks a pending transaction and picks a category → moves to "staged" (status: `pending_save`)
2. User reviews all staged transactions → clicks "Save All" → committed (status: `confirmed`)

This prevents accidental commits and lets users batch their work.

---

## 5.3 Spending (`Spending.jsx`)

Monthly spending analysis with interactive charts.

**Features (502 lines):**

- **Month selector**: Navigate between months
- **Bar chart**: Monthly spending trend using Recharts `BarChart`
- **Pie chart**: Category distribution using Recharts `PieChart`
- **Category table**: Grouped by parent category (e.g., "Food" expands to show Groceries, Fast Food, Restaurant), with amounts and percentages
- **Transaction drill-down**: Click a category row to see individual transactions
- **Sparkline trends**: Tiny line charts showing 6-month spending trends per category
- **Inline recategorization**: Change a transaction's category directly from the spending view

The sparkline component is reusable:

```jsx
function Sparkline({ data, width = 60, height = 20, color = '#6c5ce7' }) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const points = data.map((v, i) =>
    `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`
  ).join(' ')
  return (
    <svg width={width} height={height}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  )
}
```

---

## 5.4 Cash Flow (`CashFlow.jsx`)

Biweekly cash flow analysis showing income vs. expenses over time.

**Features (868 lines):**

- **Area chart**: Stacked income (green) and expense (red) areas over biweekly periods using Recharts `AreaChart`
- **Year selector**: Switch between years
- **Expense drivers**: Top spending categories ranked by amount with sparkline trends
- **Income drivers**: Income sources with sparkline trends
- **Drill-down**: Click any category to see its transactions for the selected period
- **Side-by-side view**: Income and expense breakdowns shown in parallel columns
- **Excluded categories**: Section listing categories excluded from cash flow analysis (like balance adjustments)

---

## 5.5 Recurring Monitor (`RecurringMonitor.jsx`)

Tracks subscription and recurring charges across months.

**Features:**

- **Monthly grid**: Rows are recurring categories, columns are months. Each cell shows the charge amount for that month
- **Category filter**: Toggle which recurring categories to show/hide
- **Change indicators**: Up/down arrows showing month-to-month changes in amounts
- **Net totals**: Row showing net recurring spend per month (inflows minus outflows)
- **Transaction drill-down**: Click a cell to see the specific transactions for that category/month
- **Inline recategorization**: Move transactions to different categories directly

---

## 5.6 Budget (`Budget.jsx`)

Set monthly budget targets and track progress against actual spending.

**Features (206 lines):**

- **Budget list**: Shows each budgeted category with a progress bar
- **Progress colors**: Green (under 75%), yellow (75–100%), red (over budget)
- **Totals row**: Sum of all budgets vs. sum of all spending
- **Add/edit budget**: Form to set a budget amount for a category + month
- **Month selector**: Navigate between months

```jsx
// Progress bar coloring logic
const getProgressColor = (percent) => {
  if (percent > 100) return '#e74c3c'  // Over budget — red
  if (percent > 75) return '#f39c12'   // Warning — yellow
  return '#2ecc71'                     // On track — green
}
```

---

## 5.7 Accounts (`Accounts.jsx`)

Bank account management and CSV import.

**Features:**

- **Account cards**: One card per bank account showing name, institution, connection status, current balance, transaction count, and date coverage
- **Plaid Link**: "Connect" button opens the Plaid Link widget for linking bank accounts
- **Sync buttons**: Individual sync per account and "Sync All" button
- **Balance refresh**: Pull latest balances from Plaid
- **Disconnect**: Unlink an account from Plaid (preserves transaction data)
- **CSV import**: Drag-and-drop file upload with bank format auto-detection (Discover, SoFi Checking, SoFi Savings, Wells Fargo)
- **Sync history link**: Navigation card that opens the dedicated sync history page

The Plaid Link integration:

```jsx
const { open, ready } = usePlaidLink({
  token: linkToken,
  onSuccess: async (publicToken) => {
    await fetch('/api/accounts/link/exchange', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: selectedAccount,
        public_token: publicToken,
      }),
    })
    fetchAccounts()
  },
  onExit: () => setLinkToken(null),
})
```

---

## 5.8 Data Browser (`Data.jsx`)

A full-featured transaction browser for exploring and managing all data.

**Features (805 lines):**

- **Filtering**: By category (hierarchical picker), year, account, source (plaid/csv/archive), and status
- **Full-text search**: Debounced search across descriptions and merchant names
- **Multi-select**: Checkbox selection with shift-click for range selection
- **Bulk categorization**: Categorize multiple selected transactions at once
- **Bulk delete**: Delete multiple transactions (with soft-delete to audit log)
- **Pagination**: Configurable page size (25, 50, 100, All)
- **Sort toggle**: Date ascending/descending
- **Status indicators**: Color-coded status badges (pending, staged, confirmed, auto-confirmed)
- **Individual delete**: Trash icon per row with confirmation

---

## 5.9 Categories (`Categories.jsx`)

Manage the two-level category taxonomy.

**Features (713 lines):**

- **Tree view**: Parent categories expand to show children
- **Create**: Add new parent or child categories with custom display names and colors
- **Rename**: Inline editing of display names
- **Move**: Drag a subcategory to a different parent
- **Merge**: Combine two categories (moves all transactions, mappings, rules, and budgets to the target)
- **Delete**: Remove empty categories (prevents deletion if transactions exist)
- **Toggle recurring**: Mark/unmark categories as recurring
- **Expand/collapse all**: Bulk toggle for the tree view
- **Portal-based dropdowns**: CategoryPicker uses React portals for proper z-index layering

---

## 5.10 Settings (`Settings.jsx`)

Application configuration.

**Features:**

- **AI categorization**: Set the Anthropic API key and auto-confirm confidence threshold
- **Email notifications**: Configure Gmail integration for transaction alerts (email address, app password, recipient, batch interval)
- **Database location**: Shows the path to `~/BudgetApp/budget.db`
- **Deleted transactions link**: Navigation card to the dedicated deleted transactions page (with count badge)

---

## 5.11 Deleted Transactions (`DeletedTransactions.jsx`)

Standalone page for managing the soft-delete audit log.

**Features:**

- **Table**: Shows deleted transactions with original date, description, amount, account, category, and deletion timestamp
- **Restore individual**: Put a deleted transaction back in the main table
- **Restore bulk**: Select and restore multiple at once
- **Purge individual**: Permanently remove from the audit log (trash icon)
- **Clear all**: Permanently remove all deleted transactions with a confirmation dialog
- **Back navigation**: Arrow link to Settings

---

## 5.12 Sync History (`SyncHistory.jsx`)

Standalone page showing the audit trail of all Plaid sync operations.

**Features:**

- **Date grouping**: Sync logs grouped by date with separator rows
- **Summary header**: Total successful/failed sync counts
- **Status icons**: Checkmark for success, X for error, clock for pending
- **Trigger badges**: Color-coded labels (scheduled, manual, initial, retry)
- **Change metrics**: Added/modified/removed transaction counts per sync
- **Duration**: How long each sync took
- **Error messages**: Displayed for failed syncs
- **Refresh button**: Manually reload the sync history
- **Back navigation**: Arrow link to Accounts

---

## 5.13 CSS Styling (`frontend/src/styles.css`)

The app uses a dark theme with CSS custom properties (no CSS framework). The stylesheet is approximately 1500+ lines covering all components.

### Design System

```css
:root {
  --bg-primary: #0f1117;
  --bg-secondary: #1a1d27;
  --bg-tertiary: #242836;
  --text-primary: #e4e6eb;
  --text-secondary: #8b8fa3;
  --accent: #6c5ce7;
  --accent-hover: #5a4bd1;
  --green: #2ecc71;
  --red: #e74c3c;
  --yellow: #f39c12;
  --border: #2a2e3d;
}
```

### Layout

```css
.app {
  display: flex;
  min-height: 100vh;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.sidebar {
  width: 220px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  position: fixed;
  height: 100vh;
  overflow-y: auto;
}

.main-content {
  flex: 1;
  margin-left: 220px;
  padding: 24px 32px;
}
```

### Reusable Component Classes

The CSS follows a consistent naming convention:

- `.card` — Base container with border, radius, and padding
- `.data-table` — Styled tables with hover effects and striped rows
- `.stats-row` / `.stat-card` — Stat card grid layouts
- `.badge` — Small count badges (used in sidebar and tables)
- `.btn-primary` / `.btn-secondary` / `.btn-danger` — Button variants
- `.btn-danger-outline` — Transparent button with red border (for destructive actions)
- `.empty-state` — Centered placeholder when no data exists
- `.settings-link-card` — Clickable navigation cards (used in Settings and Accounts)

### Chart Integration

Recharts components are styled with CSS overrides:

```css
.recharts-cartesian-axis-tick-value {
  fill: var(--text-secondary);
  font-size: 12px;
}

.recharts-tooltip-wrapper {
  outline: none;
}
```

---

## 5.14 Entry Point (`frontend/src/main.jsx`)

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

---

## What's Next

With the full frontend built, Part 6 adds advanced features: AI-powered financial insights, investment portfolio tracking, the background sync scheduler, and the sync daemon for scheduled background updates.

→ [Part 6: Advanced Features](06-advanced-features.md)
