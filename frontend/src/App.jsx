import React, { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { usePlaidLink } from 'react-plaid-link'
import { LayoutDashboard, CheckSquare, TrendingUp, Wallet, Upload, Settings, FolderTree, Database, BarChart3, Repeat, LineChart, Sparkles } from 'lucide-react'
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
            {pendingCount > 0 && <span className="badge" title="Pending review + staged">{pendingCount}</span>}
          </NavLink>
        </li>
        <li>
          <NavLink to="/spending">
            <TrendingUp size={18} />
            Spending
          </NavLink>
        </li>
        <li>
          <NavLink to="/cash-flow">
            <BarChart3 size={18} />
            Cash Flow
          </NavLink>
        </li>
        <li>
          <NavLink to="/recurring">
            <Repeat size={18} />
            Recurring
          </NavLink>
        </li>
        <li>
          <NavLink to="/budget">
            <Wallet size={18} />
            Budget
          </NavLink>
        </li>
        <li>
          <NavLink to="/accounts">
            <LayoutDashboard size={18} />
            Accounts
          </NavLink>
        </li>
        <li>
          <NavLink to="/investments">
            <LineChart size={18} />
            Investments
          </NavLink>
        </li>
        <li>
          <NavLink to="/insights">
            <Sparkles size={18} />
            Insights
          </NavLink>
        </li>
        <li>
          <NavLink to="/data">
            <Database size={18} />
            Data
          </NavLink>
        </li>
        <li>
          <NavLink to="/categories">
            <FolderTree size={18} />
            Categories
          </NavLink>
        </li>
        <li>
          <NavLink to="/settings">
            <Settings size={18} />
            Settings
          </NavLink>
        </li>
      </ul>
    </nav>
  )
}

// OAuth callback handler — Plaid redirects here after OAuth bank login
function OAuthCallback() {
  const navigate = useNavigate()

  // Retrieve the link token that was stored before the OAuth redirect
  const linkToken = sessionStorage.getItem('plaid_link_token')
  const accountId = sessionStorage.getItem('plaid_account_id')

  const onSuccess = useCallback(async (publicToken) => {
    try {
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
    } catch (err) {
      console.error('OAuth exchange failed:', err)
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

  return (
    <div className="empty-state" style={{ padding: 60 }}>
      <p>Completing bank connection...</p>
    </div>
  )
}

function AppContent() {
  const [stats, setStats] = useState({ total_transactions: 0, pending_review: 0, pending_save: 0, confirmed: 0 })

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/stats')
      if (res.ok) {
        const data = await res.json()
        setStats(data)
      }
    } catch (err) {
      console.error('Failed to fetch stats:', err)
    }
  }

  useEffect(() => {
    fetchStats()
    // Refresh stats every 30 seconds
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

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  )
}
