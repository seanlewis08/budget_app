import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, CheckSquare, TrendingUp, Wallet, Upload, Settings } from 'lucide-react'
import ReviewQueue from './pages/ReviewQueue'
import Spending from './pages/Spending'
import Budget from './pages/Budget'
import Accounts from './pages/Accounts'
import SettingsPage from './pages/Settings'

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
            {pendingCount > 0 && <span className="badge">{pendingCount}</span>}
          </NavLink>
        </li>
        <li>
          <NavLink to="/spending">
            <TrendingUp size={18} />
            Spending
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
          <NavLink to="/settings">
            <Settings size={18} />
            Settings
          </NavLink>
        </li>
      </ul>
    </nav>
  )
}

function AppContent() {
  const [stats, setStats] = useState({ total_transactions: 0, pending_review: 0, confirmed: 0 })

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
      <Sidebar pendingCount={stats.pending_review} />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<ReviewQueue stats={stats} onUpdate={fetchStats} />} />
          <Route path="/spending" element={<Spending />} />
          <Route path="/budget" element={<Budget />} />
          <Route path="/accounts" element={<Accounts onUpdate={fetchStats} />} />
          <Route path="/settings" element={<SettingsPage />} />
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
