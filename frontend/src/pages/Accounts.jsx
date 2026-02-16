import React, { useState, useEffect, useRef, useCallback } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import { useNavigate } from 'react-router-dom'
import {
  Upload, FileText, CheckCircle, AlertCircle,
  RefreshCw, Link2, Unlink, Wifi, WifiOff, DollarSign, Clock,
  CreditCard, Building2, PiggyBank, Landmark, Calendar, Database,
  History, ChevronRight,
} from 'lucide-react'

// Icon map for account types
const accountIcons = {
  credit: CreditCard,
  checking: Building2,
  savings: PiggyBank,
}

// Status badge colors
const statusColors = {
  connected: { bg: 'var(--green-bg)', color: 'var(--green)', border: 'rgba(52,211,153,0.3)' },
  disconnected: { bg: 'var(--bg-primary)', color: 'var(--text-muted)', border: 'var(--border)' },
  item_login_required: { bg: 'var(--yellow-bg)', color: 'var(--yellow)', border: 'rgba(251,191,36,0.3)' },
}

function formatCurrency(amount) {
  if (amount == null) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

function timeAgo(dateStr) {
  if (!dateStr) return 'Never'
  // Backend stores UTC times without a Z suffix — append it so the browser
  // interprets the timestamp correctly instead of treating it as local time.
  const normalized = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z'
  const date = new Date(normalized)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  let relative
  if (diffMins < 1) relative = 'Just now'
  else if (diffMins < 60) relative = `${diffMins}m ago`
  else {
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) relative = `${diffHours}h ago`
    else {
      const diffDays = Math.floor(diffHours / 24)
      relative = `${diffDays}d ago`
    }
  }
  // Show actual time alongside relative
  const timeStr = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  const dateFormatted = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  if (diffMins < 1440) return `${relative} (${timeStr})`
  return `${relative} (${dateFormatted} ${timeStr})`
}

function formatShortDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

function formatDateRange(earliest, latest) {
  if (!earliest || !latest) return null
  return `${formatShortDate(earliest)} – ${formatShortDate(latest)}`
}


// Plaid Link wrapper component
function PlaidLinkButton({ accountId, onSuccess }) {
  const [linkToken, setLinkToken] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchLinkToken = async () => {
    setLoading(true)
    try {
      // Only send redirect_uri if we're on HTTPS (required by Plaid production).
      // OAuth banks (e.g. Wells Fargo) need this; non-OAuth banks work without it.
      const origin = window.location.origin
      const payload = { account_id: accountId }
      if (origin.startsWith('https://')) {
        payload.redirect_uri = `${origin}/oauth-callback`
      }

      const res = await fetch('/api/accounts/link/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (res.ok) {
        // Store for OAuth callback recovery
        sessionStorage.setItem('plaid_link_token', data.link_token)
        sessionStorage.setItem('plaid_account_id', String(accountId))
        setLinkToken(data.link_token)
      } else {
        alert(data.detail || 'Failed to create link token')
      }
    } catch (err) {
      alert('Error connecting to Plaid: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  const onPlaidSuccess = useCallback(async (publicToken, metadata) => {
    try {
      const res = await fetch('/api/accounts/link/exchange', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: accountId,
          public_token: publicToken,
        }),
      })
      const data = await res.json()
      if (res.ok) {
        onSuccess(data)
      } else {
        alert(data.detail || 'Failed to link account')
      }
    } catch (err) {
      alert('Error linking account: ' + err.message)
    }
    setLinkToken(null)
  }, [accountId, onSuccess])

  return (
    <>
      <button
        className="btn btn-primary acct-btn"
        onClick={fetchLinkToken}
        disabled={loading}
      >
        <Link2 size={14} />
        {loading ? 'Connecting...' : 'Link Bank'}
      </button>
      {linkToken && (
        <PlaidLinkOpener
          token={linkToken}
          onSuccess={onPlaidSuccess}
          onExit={() => setLinkToken(null)}
        />
      )}
    </>
  )
}

// Only mount usePlaidLink when we actually have a token
function PlaidLinkOpener({ token, onSuccess, onExit }) {
  const { open, ready } = usePlaidLink({
    token,
    onSuccess,
    onExit,
  })

  useEffect(() => {
    if (ready) open()
  }, [ready, open])

  return null
}


// Individual account card
function AccountCard({ account, onRefresh }) {
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)

  const Icon = accountIcons[account.account_type] || Landmark
  const status = statusColors[account.plaid_connection_status] || statusColors.disconnected
  const isConnected = account.plaid_connection_status === 'connected'
  const needsRelink = account.plaid_connection_status === 'item_login_required'

  const handleSync = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await fetch(`/api/accounts/${account.id}/sync`, { method: 'POST' })
      const data = await res.json()
      if (res.ok) {
        setSyncResult({ type: 'success', data })
        onRefresh()
      } else {
        setSyncResult({ type: 'error', message: data.detail || 'Sync failed' })
      }
    } catch (err) {
      setSyncResult({ type: 'error', message: err.message })
    } finally {
      setSyncing(false)
    }
  }

  const handleRefreshBalances = async () => {
    try {
      await fetch(`/api/accounts/${account.id}/balances`, { method: 'POST' })
      onRefresh()
    } catch (err) {
      console.error('Balance refresh failed:', err)
    }
  }

  const handleDisconnect = async () => {
    if (!confirm(`Disconnect ${account.name}? This will remove all synced transactions from Plaid.`)) return
    try {
      const res = await fetch(`/api/accounts/${account.id}/disconnect`, { method: 'POST' })
      if (res.ok) onRefresh()
    } catch (err) {
      console.error('Disconnect failed:', err)
    }
  }

  return (
    <div className="acct-card">
      <div className="acct-card-header">
        <div className="acct-card-icon">
          <Icon size={20} />
        </div>
        <div className="acct-card-info">
          <div className="acct-card-name">{account.name}</div>
          <div className="acct-card-type">{account.account_type}</div>
        </div>
        <div
          className="acct-status-badge"
          style={{ background: status.bg, color: status.color, borderColor: status.border }}
        >
          {isConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
          {account.plaid_connection_status === 'item_login_required'
            ? 'Relink needed'
            : account.plaid_connection_status}
        </div>
      </div>

      {isConnected && (
        <div className="acct-card-balances">
          <div className="acct-balance-row">
            <span className="acct-balance-label">
              <DollarSign size={13} />
              {account.account_type === 'credit' ? 'Balance' : 'Available'}
            </span>
            <span className="acct-balance-value">
              {formatCurrency(
                account.account_type === 'credit'
                  ? account.balance_current
                  : (account.balance_available ?? account.balance_current)
              )}
            </span>
          </div>
          {account.account_type === 'credit' && account.balance_limit && (
            <div className="acct-balance-row">
              <span className="acct-balance-label">Credit Limit</span>
              <span className="acct-balance-value">{formatCurrency(account.balance_limit)}</span>
            </div>
          )}
          <div className="acct-balance-row last-sync">
            <span className="acct-balance-label">
              <Clock size={13} />
              Last synced
            </span>
            <span className="acct-balance-value muted">
              {timeAgo(account.last_synced_at)}
            </span>
          </div>
          {account.transaction_count > 0 && (
            <>
              <div className="acct-balance-row">
                <span className="acct-balance-label">
                  <Database size={13} />
                  Transactions
                </span>
                <span className="acct-balance-value muted">
                  {account.transaction_count.toLocaleString()}
                </span>
              </div>
              <div className="acct-balance-row">
                <span className="acct-balance-label">
                  <Calendar size={13} />
                  Coverage
                </span>
                <span className="acct-balance-value muted" style={{ fontSize: 12 }}>
                  {formatDateRange(account.earliest_transaction, account.latest_transaction)}
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {account.last_sync_error && (
        <div className="acct-error">
          <AlertCircle size={13} />
          {account.last_sync_error}
        </div>
      )}

      <div className="acct-card-actions">
        {isConnected ? (
          <>
            <button
              className="btn btn-secondary acct-btn"
              onClick={handleSync}
              disabled={syncing}
            >
              <RefreshCw size={14} className={syncing ? 'spin' : ''} />
              {syncing ? 'Syncing...' : 'Sync Now'}
            </button>
            <button
              className="btn btn-secondary acct-btn"
              onClick={handleRefreshBalances}
              title="Refresh balances"
            >
              <DollarSign size={14} />
            </button>
            <button
              className="btn btn-secondary acct-btn acct-btn-unlink"
              onClick={handleDisconnect}
              title="Disconnect account"
            >
              <Unlink size={14} />
            </button>
          </>
        ) : (
          <PlaidLinkButton
            accountId={account.id}
            onSuccess={() => onRefresh()}
          />
        )}
        {needsRelink && (
          <PlaidLinkButton
            accountId={account.id}
            onSuccess={() => onRefresh()}
          />
        )}
      </div>

      {syncResult && (
        <div className={`acct-sync-result ${syncResult.type}`}>
          {syncResult.type === 'success' ? (
            <span>
              <CheckCircle size={13} />
              +{syncResult.data.added} new, {syncResult.data.modified} updated, {syncResult.data.removed} removed
            </span>
          ) : (
            <span>
              <AlertCircle size={13} />
              {syncResult.message}
            </span>
          )}
        </div>
      )}
    </div>
  )
}


export default function Accounts({ onUpdate }) {
  const navigate = useNavigate()
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)

  // CSV upload state
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [selectedBank, setSelectedBank] = useState('')
  const [autoDetect, setAutoDetect] = useState(true)
  const fileRef = useRef(null)

  const banks = [
    { value: 'discover', label: 'Discover Credit Card' },
    { value: 'sofi_checking', label: 'SoFi Checking' },
    { value: 'sofi_savings', label: 'SoFi Savings' },
    { value: 'wellsfargo', label: 'Wells Fargo Checking' },
  ]

  const fetchAccounts = async () => {
    try {
      const res = await fetch('/api/accounts')
      if (res.ok) {
        const data = await res.json()
        setAccounts(data)
      }
    } catch (err) {
      console.error('Failed to fetch accounts:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAccounts() }, [])

  const handleRefresh = () => {
    fetchAccounts()
    if (onUpdate) onUpdate()
  }

  const handleSyncAll = async () => {
    setSyncing(true)
    try {
      const res = await fetch('/api/accounts/sync-all', { method: 'POST' })
      if (res.ok) {
        handleRefresh()
      }
    } catch (err) {
      console.error('Sync all failed:', err)
    } finally {
      setSyncing(false)
    }
  }

  // CSV upload handlers
  const handleUpload = async (file) => {
    setUploading(true)
    setUploadResult(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      let url = '/api/import/csv/auto-detect'
      if (!autoDetect && selectedBank) {
        url = `/api/import/csv?bank=${selectedBank}`
      }

      const res = await fetch(url, { method: 'POST', body: formData })
      const data = await res.json()
      if (res.ok) {
        setUploadResult({ type: 'success', data })
        handleRefresh()
      } else {
        setUploadResult({ type: 'error', message: data.detail || 'Upload failed' })
      }
    } catch (err) {
      setUploadResult({ type: 'error', message: err.message })
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }

  const connectedCount = accounts.filter(a => a.plaid_connection_status === 'connected').length

  return (
    <div>
      <div className="page-header">
        <h2>Accounts & Import</h2>
        <p>Link your bank accounts for automatic syncing or import CSVs manually</p>
      </div>

      {/* Bank Accounts Section */}
      <div className="card">
        <div className="card-header">
          <h3>Bank Accounts</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {connectedCount > 0 && (
              <span style={{ fontSize: 13, color: 'var(--text-muted)', marginRight: 8 }}>
                {connectedCount} of {accounts.length} connected
              </span>
            )}
            {connectedCount > 0 && (
              <button
                className="btn btn-secondary"
                onClick={handleSyncAll}
                disabled={syncing}
              >
                <RefreshCw size={14} className={syncing ? 'spin' : ''} style={{ marginRight: 6 }} />
                {syncing ? 'Syncing...' : 'Sync All'}
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="empty-state" style={{ padding: 30 }}>
            <p>Loading accounts...</p>
          </div>
        ) : accounts.length === 0 ? (
          <div className="empty-state" style={{ padding: 30 }}>
            <p>No accounts found. Restart the backend to seed your 4 accounts.</p>
          </div>
        ) : (
          <div className="acct-grid">
            {accounts.map(account => (
              <AccountCard
                key={account.id}
                account={account}
                onRefresh={handleRefresh}
              />
            ))}
          </div>
        )}
      </div>

      {/* Sync History Link */}
      <div
        className="card settings-link-card"
        style={{ cursor: 'pointer' }}
        onClick={() => navigate('/sync-history')}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <History size={16} />
            <span style={{ fontWeight: 500 }}>Sync History</span>
          </div>
          <ChevronRight size={16} style={{ color: 'var(--text-muted)' }} />
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '4px 0 0 26px' }}>
          View a log of all sync operations across your accounts
        </p>
      </div>

      {/* CSV Import */}
      <div className="card">
        <div className="card-header">
          <h3>Import CSV</h3>
        </div>

        <div style={{ marginBottom: 16, display: 'flex', gap: 16, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 14, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={autoDetect}
              onChange={(e) => setAutoDetect(e.target.checked)}
            />
            Auto-detect bank format
          </label>

          {!autoDetect && (
            <select
              className="category-select"
              value={selectedBank}
              onChange={(e) => setSelectedBank(e.target.value)}
            >
              <option value="">Select bank...</option>
              {banks.map(bank => (
                <option key={bank.value} value={bank.value}>{bank.label}</option>
              ))}
            </select>
          )}
        </div>

        <div
          className="upload-zone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <input
            type="file"
            ref={fileRef}
            onChange={(e) => { const f = e.target.files[0]; if (f) handleUpload(f) }}
            accept=".csv"
            style={{ display: 'none' }}
          />
          {uploading ? (
            <>
              <div className="icon" style={{ color: 'var(--accent)' }}>
                <FileText size={40} />
              </div>
              <p>Processing...</p>
            </>
          ) : (
            <>
              <div className="icon" style={{ color: 'var(--text-muted)' }}>
                <Upload size={40} />
              </div>
              <p>Drop a CSV file here or click to browse</p>
              <p style={{ fontSize: 12, marginTop: 4, color: 'var(--text-muted)' }}>
                Supports Discover, SoFi, and Wells Fargo formats
              </p>
            </>
          )}
        </div>

        {uploadResult && (
          <div style={{
            marginTop: 16,
            padding: 16,
            borderRadius: 'var(--radius)',
            background: uploadResult.type === 'success' ? 'var(--green-bg)' : 'var(--red-bg)',
            border: `1px solid ${uploadResult.type === 'success' ? 'rgba(52,211,153,0.3)' : 'rgba(248,113,113,0.3)'}`,
          }}>
            {uploadResult.type === 'success' ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle size={18} style={{ color: 'var(--green)' }} />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--green)' }}>Import successful!</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                    {uploadResult.data.imported} new transactions imported,
                    {' '}{uploadResult.data.skipped_duplicates} duplicates skipped
                    {' '}({uploadResult.data.bank} format)
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertCircle size={18} style={{ color: 'var(--red)' }} />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--red)' }}>Import failed</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                    {uploadResult.message}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
