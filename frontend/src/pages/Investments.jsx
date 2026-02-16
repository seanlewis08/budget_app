import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell, Legend } from 'recharts'
import { RefreshCw, TrendingUp, TrendingDown, DollarSign, PieChart as PieChartIcon, ArrowUpDown, Plus, Loader, AlertCircle, Link2 } from 'lucide-react'

const COLORS = ['#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#f472b6', '#fb923c', '#2dd4bf', '#818cf8', '#e879f9']

const fmt = (n) => {
  if (n == null) return '—'
  return '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const fmtSigned = (n) => {
  if (n == null) return '—'
  const prefix = n >= 0 ? '+' : '-'
  return prefix + '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const fmtPct = (n) => {
  if (n == null) return '—'
  const prefix = n >= 0 ? '+' : ''
  return prefix + n.toFixed(2) + '%'
}
const fmtShares = (n) => {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}


// ── Plaid Link for Investment Accounts ──

function PlaidLinkOpener({ token, onSuccess, onExit }) {
  const { open, ready } = usePlaidLink({ token, onSuccess, onExit })
  useEffect(() => { if (ready) open() }, [ready, open])
  return null
}

function AddInvestmentAccount({ onLinked, label }) {
  const [linkToken, setLinkToken] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [mode, setMode] = useState(null) // 'manual' | 'plaid'
  const [plaidError, setPlaidError] = useState(null)
  const [accountName, setAccountName] = useState('')
  const [accountType, setAccountType] = useState('taxable')
  const [institution, setInstitution] = useState('Fidelity')

  // Manual holding fields
  const [holdings, setHoldings] = useState([{ ticker: '', quantity: '', costBasis: '' }])
  const [saving, setSaving] = useState(false)

  const addHoldingRow = () => {
    setHoldings(prev => [...prev, { ticker: '', quantity: '', costBasis: '' }])
  }
  const updateHolding = (idx, field, value) => {
    setHoldings(prev => prev.map((h, i) => i === idx ? { ...h, [field]: value } : h))
  }
  const removeHolding = (idx) => {
    setHoldings(prev => prev.filter((_, i) => i !== idx))
  }

  const fetchLinkToken = async () => {
    setLoading(true)
    setPlaidError(null)
    try {
      const origin = window.location.origin
      const payload = {}
      if (origin.startsWith('https://')) {
        payload.redirect_uri = `${origin}/oauth-callback`
      }
      const res = await fetch('/api/investments/link-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (res.ok) {
        setLinkToken(data.link_token)
      } else {
        // If Plaid investments product not authorized, suggest manual entry
        const detail = data.detail || ''
        if (detail.includes('not authorized') || detail.includes('PRODUCTS_NOT_SUPPORTED')) {
          setPlaidError('Your Plaid account does not have the investments product enabled. You can add accounts manually instead.')
          setMode('manual')
        } else {
          setPlaidError(detail || 'Failed to create link token')
        }
      }
    } catch (err) {
      setPlaidError('Error connecting to Plaid: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  const onPlaidSuccess = useCallback(async (publicToken, metadata) => {
    try {
      const res = await fetch('/api/investments/link/exchange', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          public_token: publicToken,
          account_name: accountName || 'Investment Account',
          account_type: accountType,
          institution_name: institution || null,
        }),
      })
      const data = await res.json()
      if (res.ok) {
        onLinked(data)
      } else {
        alert(data.detail || 'Failed to link investment account')
      }
    } catch (err) {
      alert('Error linking account: ' + err.message)
    }
    setLinkToken(null)
    setShowForm(false)
    setMode(null)
  }, [accountName, accountType, institution, onLinked])

  const handleManualSave = async () => {
    if (!accountName.trim()) return
    setSaving(true)
    try {
      // Step 1: Create the manual account
      const acctRes = await fetch('/api/investments/accounts/manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_name: accountName,
          account_type: accountType,
          institution_name: institution || null,
        }),
      })
      const acctData = await acctRes.json()
      if (!acctRes.ok) {
        alert(acctData.detail || 'Failed to create account')
        setSaving(false)
        return
      }

      // Step 2: Add holdings one by one
      const accountId = acctData.account_id
      const validHoldings = holdings.filter(h => h.ticker.trim() && parseFloat(h.quantity) > 0)
      for (const h of validHoldings) {
        await fetch(`/api/investments/accounts/${accountId}/holdings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ticker: h.ticker.trim().toUpperCase(),
            quantity: parseFloat(h.quantity),
            cost_basis_per_share: h.costBasis ? parseFloat(h.costBasis) : null,
          }),
        })
      }

      onLinked(acctData)
      setShowForm(false)
      setMode(null)
      setAccountName('')
      setHoldings([{ ticker: '', quantity: '', costBasis: '' }])
    } catch (err) {
      alert('Error creating account: ' + err.message)
    }
    setSaving(false)
  }

  if (showForm) {
    return (
      <div className="inv-link-form">
        {/* Mode selection */}
        {!mode && (
          <>
            <h4>Add Investment Account</h4>
            <p style={{ color: 'var(--text-muted)', fontSize: 13, margin: '0 0 8px' }}>
              Choose how to add your account:
            </p>
            <div className="inv-link-actions">
              <button className="btn btn-primary" onClick={() => setMode('manual')}>
                <Plus size={14} />
                Enter Manually
              </button>
              <button className="btn btn-secondary" onClick={() => setMode('plaid')}>
                <Link2 size={14} />
                Connect via Plaid
              </button>
              <button className="btn btn-secondary" onClick={() => { setShowForm(false); setMode(null) }}>
                Cancel
              </button>
            </div>
          </>
        )}

        {/* Plaid flow */}
        {mode === 'plaid' && (
          <>
            <h4>Connect via Plaid</h4>
            <div className="inv-link-field">
              <label>Account Name</label>
              <input type="text" value={accountName} onChange={e => setAccountName(e.target.value)} placeholder="e.g. Fidelity Brokerage" />
            </div>
            <div className="inv-link-field">
              <label>Account Type</label>
              <select value={accountType} onChange={e => setAccountType(e.target.value)}>
                <option value="taxable">Taxable Brokerage</option>
                <option value="roth">Roth IRA</option>
                <option value="traditional_ira">Traditional IRA</option>
                <option value="401k">401(k)</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="inv-link-field">
              <label>Institution</label>
              <input type="text" value={institution} onChange={e => setInstitution(e.target.value)} placeholder="e.g. Fidelity" />
            </div>
            {plaidError && (
              <div className="inv-sync-error">
                <AlertCircle size={14} /> {plaidError}
              </div>
            )}
            <div className="inv-link-actions">
              <button className="btn btn-primary" onClick={fetchLinkToken} disabled={loading || !accountName.trim()}>
                <Link2 size={14} />
                {loading ? 'Connecting...' : 'Connect via Plaid'}
              </button>
              <button className="btn btn-secondary" onClick={() => { setMode(null); setPlaidError(null) }}>Back</button>
            </div>
            {linkToken && (
              <PlaidLinkOpener token={linkToken} onSuccess={onPlaidSuccess} onExit={() => setLinkToken(null)} />
            )}
          </>
        )}

        {/* Manual entry flow */}
        {mode === 'manual' && (
          <>
            <h4>Add Account Manually</h4>
            {plaidError && (
              <div className="inv-sync-error" style={{ marginBottom: 8 }}>
                <AlertCircle size={14} /> {plaidError}
              </div>
            )}
            <div className="inv-link-field">
              <label>Account Name</label>
              <input type="text" value={accountName} onChange={e => setAccountName(e.target.value)} placeholder="e.g. Fidelity Brokerage" />
            </div>
            <div className="inv-link-field">
              <label>Account Type</label>
              <select value={accountType} onChange={e => setAccountType(e.target.value)}>
                <option value="taxable">Taxable Brokerage</option>
                <option value="roth">Roth IRA</option>
                <option value="traditional_ira">Traditional IRA</option>
                <option value="401k">401(k)</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="inv-link-field">
              <label>Institution</label>
              <input type="text" value={institution} onChange={e => setInstitution(e.target.value)} placeholder="e.g. Fidelity" />
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, marginTop: 4 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                Holdings (optional — you can add these later)
              </label>
              {holdings.map((h, idx) => (
                <div key={idx} className="inv-holding-input-row">
                  <input
                    type="text"
                    placeholder="Ticker (e.g. AAPL)"
                    value={h.ticker}
                    onChange={e => updateHolding(idx, 'ticker', e.target.value)}
                    style={{ width: 110 }}
                  />
                  <input
                    type="number"
                    placeholder="Shares"
                    value={h.quantity}
                    onChange={e => updateHolding(idx, 'quantity', e.target.value)}
                    style={{ width: 90 }}
                  />
                  <input
                    type="number"
                    placeholder="Avg cost/share"
                    value={h.costBasis}
                    onChange={e => updateHolding(idx, 'costBasis', e.target.value)}
                    style={{ width: 130 }}
                  />
                  {holdings.length > 1 && (
                    <button className="btn btn-secondary btn-sm" onClick={() => removeHolding(idx)} title="Remove">×</button>
                  )}
                </div>
              ))}
              <button className="btn btn-secondary btn-sm" onClick={addHoldingRow} style={{ marginTop: 6 }}>
                <Plus size={12} /> Add Holding
              </button>
            </div>

            <div className="inv-link-actions">
              <button className="btn btn-primary" onClick={handleManualSave} disabled={saving || !accountName.trim()}>
                {saving ? 'Saving...' : 'Create Account'}
              </button>
              <button className="btn btn-secondary" onClick={() => { setMode(null); setPlaidError(null) }}>Back</button>
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <button className="btn btn-primary" onClick={() => setShowForm(true)}>
      <Plus size={14} />
      {label || 'Add Investment Account'}
    </button>
  )
}


// ── Main Component ──

export default function Investments() {
  const [summary, setSummary] = useState(null)
  const [holdings, setHoldings] = useState([])
  const [performance, setPerformance] = useState([])
  const [allocation, setAllocation] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [txnTotal, setTxnTotal] = useState(0)
  const [accounts, setAccounts] = useState([])

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [syncing, setSyncing] = useState(null) // account id being synced

  const [sortCol, setSortCol] = useState('current_value')
  const [sortDir, setSortDir] = useState('desc')
  const [txnTypeFilter, setTxnTypeFilter] = useState('all')
  const [txnPage, setTxnPage] = useState(0)
  const [perfMonths, setPerfMonths] = useState(12)
  const [selectedSecurity, setSelectedSecurity] = useState(null) // filter txns by security

  // ── Data Fetching ──

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [sumRes, holdRes, perfRes, allocRes, txnRes, acctRes] = await Promise.all([
        fetch('/api/investments/summary'),
        fetch('/api/investments/holdings'),
        fetch(`/api/investments/performance?months=${perfMonths}`),
        fetch('/api/investments/allocation'),
        fetch('/api/investments/transactions?limit=50'),
        fetch('/api/investments/accounts'),
      ])
      if (sumRes.ok) setSummary(await sumRes.json())
      if (holdRes.ok) setHoldings(await holdRes.json())
      if (perfRes.ok) setPerformance(await perfRes.json())
      if (allocRes.ok) setAllocation(await allocRes.json())
      if (acctRes.ok) setAccounts(await acctRes.json())
      if (txnRes.ok) {
        const txnData = await txnRes.json()
        setTransactions(txnData.transactions)
        setTxnTotal(txnData.total)
      }
    } catch (err) {
      console.error('Failed to load investment data:', err)
    }
    setLoading(false)
  }, [perfMonths])

  useEffect(() => { fetchAll() }, [fetchAll])

  // Fetch transactions when filter/page/security changes
  useEffect(() => {
    const fetchTxns = async () => {
      const params = new URLSearchParams({ limit: '50', offset: String(txnPage * 50) })
      if (txnTypeFilter !== 'all') params.set('type', txnTypeFilter)
      if (selectedSecurity) params.set('security_id', selectedSecurity)
      try {
        const res = await fetch(`/api/investments/transactions?${params}`)
        if (res.ok) {
          const data = await res.json()
          setTransactions(data.transactions)
          setTxnTotal(data.total)
        }
      } catch (err) { console.error(err) }
    }
    fetchTxns()
  }, [txnTypeFilter, txnPage, selectedSecurity])

  // ── Actions ──

  const handleRefreshPrices = async () => {
    setRefreshing(true)
    try {
      await fetch('/api/investments/refresh-prices', { method: 'POST' })
      await fetchAll()
    } catch (err) { console.error(err) }
    setRefreshing(false)
  }

  const handleSync = async (accountId) => {
    setSyncing(accountId)
    try {
      await fetch(`/api/investments/accounts/${accountId}/sync`, { method: 'POST' })
      await fetchAll()
    } catch (err) { console.error(err) }
    setSyncing(null)
  }

  const handleAccountLinked = async (result) => {
    await fetchAll()
  }

  // ── Sorted Holdings ──

  const sortedHoldings = useMemo(() => {
    const sorted = [...holdings]
    sorted.sort((a, b) => {
      let va = a[sortCol], vb = b[sortCol]
      if (va == null) va = -Infinity
      if (vb == null) vb = -Infinity
      return sortDir === 'asc' ? va - vb : vb - va
    })
    return sorted
  }, [holdings, sortCol, sortDir])

  const handleSort = (col) => {
    if (sortCol === col) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortCol(col)
      setSortDir('desc')
    }
  }

  // ── Render ──

  if (loading) {
    return (
      <div className="empty-state" style={{ padding: 60 }}>
        <Loader size={24} className="spin" />
        <p>Loading investment data...</p>
      </div>
    )
  }

  const hasData = summary && summary.total_value > 0

  return (
    <div className="page-content">
      <div className="page-header">
        <h2><TrendingUp size={22} /> Investments</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-secondary"
            onClick={handleRefreshPrices}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh Prices'}
          </button>
        </div>
      </div>

      {/* ── Portfolio Overview ── */}
      {hasData ? (
        <>
          <div className="stats-row">
            <div className="stat-card">
              <div className="label">Total Value</div>
              <div className="value">{fmt(summary.total_value)}</div>
            </div>
            <div className="stat-card">
              <div className="label">Cost Basis</div>
              <div className="value">{fmt(summary.total_cost_basis)}</div>
            </div>
            <div className="stat-card">
              <div className="label">Total Gain/Loss</div>
              <div className={`value ${summary.total_gain_loss >= 0 ? 'green' : 'red'}`}>
                {fmtSigned(summary.total_gain_loss)}
                <span className="inv-pct">{fmtPct(summary.total_gain_loss_pct)}</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="label">Day Change</div>
              <div className={`value ${summary.day_change >= 0 ? 'green' : 'red'}`}>
                {fmtSigned(summary.day_change)}
                <span className="inv-pct">{fmtPct(summary.day_change_pct)}</span>
              </div>
            </div>
          </div>

          {/* ── Holdings Table ── */}
          <div className="card">
            <div className="card-header">
              <h3>Holdings</h3>
              <span className="inv-subtitle">{holdings.length} position{holdings.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="data-table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th onClick={() => handleSort('ticker')} className="inv-sortable">Ticker <ArrowUpDown size={12} /></th>
                    <th>Name</th>
                    <th>Type</th>
                    <th onClick={() => handleSort('quantity')} className="inv-sortable">Shares <ArrowUpDown size={12} /></th>
                    <th onClick={() => handleSort('cost_basis_per_unit')} className="inv-sortable">Avg Cost <ArrowUpDown size={12} /></th>
                    <th onClick={() => handleSort('current_price')} className="inv-sortable">Price <ArrowUpDown size={12} /></th>
                    <th onClick={() => handleSort('current_value')} className="inv-sortable">Value <ArrowUpDown size={12} /></th>
                    <th onClick={() => handleSort('gain_loss')} className="inv-sortable">Gain/Loss <ArrowUpDown size={12} /></th>
                    <th onClick={() => handleSort('gain_loss_pct')} className="inv-sortable">G/L % <ArrowUpDown size={12} /></th>
                    <th onClick={() => handleSort('weight_pct')} className="inv-sortable">Weight <ArrowUpDown size={12} /></th>
                  </tr>
                </thead>
                <tbody>
                  {sortedHoldings.map(h => (
                    <tr
                      key={h.id}
                      className="inv-holding-row"
                      onClick={() => {
                        setSelectedSecurity(selectedSecurity === h.security_id ? null : h.security_id)
                        setTxnPage(0)
                      }}
                      style={{ cursor: 'pointer', background: selectedSecurity === h.security_id ? 'var(--bg-hover)' : undefined }}
                    >
                      <td className="inv-ticker">{h.ticker || '—'}</td>
                      <td className="inv-name">{h.name}</td>
                      <td className="inv-type-badge">{h.security_type.replace(/_/g, ' ')}</td>
                      <td style={{ textAlign: 'right' }}>{fmtShares(h.quantity)}</td>
                      <td style={{ textAlign: 'right' }}>{h.cost_basis_per_unit ? fmt(h.cost_basis_per_unit) : '—'}</td>
                      <td style={{ textAlign: 'right' }}>{h.current_price ? fmt(h.current_price) : '—'}</td>
                      <td style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(h.current_value)}</td>
                      <td style={{ textAlign: 'right' }} className={h.gain_loss != null ? (h.gain_loss >= 0 ? 'inv-gain' : 'inv-loss') : ''}>
                        {fmtSigned(h.gain_loss)}
                      </td>
                      <td style={{ textAlign: 'right' }} className={h.gain_loss_pct != null ? (h.gain_loss_pct >= 0 ? 'inv-gain' : 'inv-loss') : ''}>
                        {fmtPct(h.gain_loss_pct)}
                      </td>
                      <td style={{ textAlign: 'right' }}>{h.weight_pct != null ? h.weight_pct.toFixed(1) + '%' : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Charts Row ── */}
          <div className="inv-charts-row">
            {/* Performance Chart */}
            <div className="card inv-chart-card">
              <div className="card-header">
                <h3>Performance</h3>
                <div className="inv-perf-controls">
                  {[3, 6, 12, 24].map(m => (
                    <button
                      key={m}
                      className={`inv-perf-btn ${perfMonths === m ? 'active' : ''}`}
                      onClick={() => setPerfMonths(m)}
                    >
                      {m}M
                    </button>
                  ))}
                </div>
              </div>
              {performance.length > 1 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={performance} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                      tickFormatter={d => {
                        const dt = new Date(d)
                        return `${dt.getMonth() + 1}/${dt.getDate()}`
                      }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                      tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text-primary)' }}
                      formatter={(val) => [fmt(val), '']}
                      labelFormatter={d => new Date(d).toLocaleDateString()}
                    />
                    <Line type="monotone" dataKey="value" stroke="#60a5fa" strokeWidth={2} dot={false} name="Portfolio" />
                    <Line type="monotone" dataKey="cost_basis" stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="4 4" dot={false} name="Cost Basis" />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="empty-state" style={{ padding: 40 }}>
                  <p>Need at least 2 daily snapshots for charting. Data will accumulate over time.</p>
                </div>
              )}
            </div>

            {/* Allocation Chart */}
            <div className="card inv-chart-card">
              <div className="card-header">
                <h3>Allocation</h3>
              </div>
              {allocation && allocation.by_type.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie
                      data={allocation.by_type}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      innerRadius={50}
                      paddingAngle={2}
                      label={({ name, pct }) => `${name.replace(/_/g, ' ')} ${pct.toFixed(0)}%`}
                      labelLine={{ stroke: 'var(--text-muted)' }}
                    >
                      {allocation.by_type.map((entry, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text-primary)' }}
                      formatter={(val) => [fmt(val), '']}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="empty-state" style={{ padding: 40 }}>
                  <p>No allocation data yet.</p>
                </div>
              )}
            </div>
          </div>

          {/* ── Transaction History ── */}
          <div className="card">
            <div className="card-header">
              <h3>
                Investment Transactions
                {selectedSecurity && (
                  <span className="inv-filter-badge" onClick={() => { setSelectedSecurity(null); setTxnPage(0) }}>
                    filtered — click to clear
                  </span>
                )}
              </h3>
              <div className="inv-txn-filters">
                {['all', 'buy', 'sell', 'dividend', 'transfer'].map(t => (
                  <button
                    key={t}
                    className={`inv-txn-filter-btn ${txnTypeFilter === t ? 'active' : ''}`}
                    onClick={() => { setTxnTypeFilter(t); setTxnPage(0) }}
                  >
                    {t === 'all' ? 'All' : t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <div className="data-table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Ticker</th>
                    <th>Name</th>
                    <th style={{ textAlign: 'right' }}>Shares</th>
                    <th style={{ textAlign: 'right' }}>Price</th>
                    <th style={{ textAlign: 'right' }}>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.length === 0 ? (
                    <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 30 }}>No transactions found</td></tr>
                  ) : (
                    transactions.map(t => (
                      <tr key={t.id}>
                        <td>{t.date}</td>
                        <td>
                          <span className={`inv-txn-type ${t.type}`}>
                            {t.type.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="inv-ticker">{t.ticker || '—'}</td>
                        <td className="inv-name">{t.security_name || '—'}</td>
                        <td style={{ textAlign: 'right' }}>{t.quantity != null ? fmtShares(t.quantity) : '—'}</td>
                        <td style={{ textAlign: 'right' }}>{t.price != null ? fmt(t.price) : '—'}</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }} className={t.amount >= 0 ? 'inv-gain' : 'inv-loss'}>
                          {fmtSigned(t.amount)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {txnTotal > 50 && (
              <div className="inv-pagination">
                <button disabled={txnPage === 0} onClick={() => setTxnPage(p => p - 1)}>Previous</button>
                <span>Page {txnPage + 1} of {Math.ceil(txnTotal / 50)}</span>
                <button disabled={(txnPage + 1) * 50 >= txnTotal} onClick={() => setTxnPage(p => p + 1)}>Next</button>
              </div>
            )}
          </div>

          {/* ── Account Management ── */}
          <div className="card">
            <div className="card-header">
              <h3>Investment Accounts</h3>
              <AddInvestmentAccount onLinked={handleAccountLinked} label="Add Account" />
            </div>
            <div className="inv-accounts-grid">
              {accounts.map(acct => (
                <div key={acct.id} className="inv-account-card">
                  <div className="inv-account-header">
                    <div>
                      <div className="inv-account-name">{acct.account_name}</div>
                      <div className="inv-account-meta">
                        {acct.institution_name && <span>{acct.institution_name}</span>}
                        <span className="inv-account-type">{acct.account_type.replace(/_/g, ' ')}</span>
                      </div>
                    </div>
                    <div className="inv-account-value">{fmt(acct.total_value)}</div>
                  </div>
                  <div className="inv-account-footer">
                    <span className={`inv-status ${acct.connection_status}`}>
                      {acct.connection_status === 'connected' ? 'Connected' :
                       acct.connection_status === 'manual' ? 'Manual' :
                       acct.connection_status}
                    </span>
                    {acct.last_synced_at && (
                      <span className="inv-last-sync">
                        Last synced: {new Date(acct.last_synced_at).toLocaleString()}
                      </span>
                    )}
                    {acct.connection_status !== 'manual' && (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleSync(acct.id)}
                        disabled={syncing === acct.id}
                      >
                        <RefreshCw size={12} className={syncing === acct.id ? 'spin' : ''} />
                        {syncing === acct.id ? 'Syncing...' : 'Sync'}
                      </button>
                    )}
                  </div>
                  {acct.last_sync_error && (
                    <div className="inv-sync-error">
                      <AlertCircle size={12} /> {acct.last_sync_error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        /* ── Empty State ── */
        <div className="card" style={{ textAlign: 'center', padding: 60 }}>
          <TrendingUp size={48} style={{ color: 'var(--text-muted)', marginBottom: 16 }} />
          <h3 style={{ marginBottom: 8 }}>No Investment Data Yet</h3>
          <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>
            Connect your brokerage account to start tracking your portfolio.
          </p>
          <AddInvestmentAccount onLinked={handleAccountLinked} />
        </div>
      )}
    </div>
  )
}
