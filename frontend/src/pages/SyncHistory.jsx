import React, { useState, useEffect } from 'react'
import { History, CheckCircle, AlertCircle, Clock, RefreshCw, ArrowLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

function formatTimestamp(isoStr) {
  if (!isoStr) return '—'
  const normalized = isoStr.endsWith('Z') || isoStr.includes('+') ? isoStr : isoStr + 'Z'
  return new Date(normalized).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
  })
}

const statusIcon = (status) => {
  if (status === 'success') return <CheckCircle size={13} style={{ color: 'var(--green)' }} />
  if (status === 'error') return <AlertCircle size={13} style={{ color: 'var(--red)' }} />
  return <Clock size={13} style={{ color: 'var(--yellow)' }} />
}

const triggerLabel = (t) => {
  const labels = { scheduled: 'Auto', manual: 'Manual', initial: 'Initial', retry: 'Retry' }
  return labels[t] || t
}

export default function SyncHistory() {
  const navigate = useNavigate()
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/accounts/sync-history?limit=50')
      if (res.ok) setLogs(await res.json())
    } catch (err) {
      console.error('Failed to fetch sync history:', err)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchLogs()
  }, [])

  // Group logs by date
  const groupedByDate = logs.reduce((acc, log) => {
    const normalized = log.started_at?.endsWith?.('Z') || log.started_at?.includes?.('+')
      ? log.started_at : (log.started_at + 'Z')
    const d = new Date(normalized)
    const dateKey = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
    if (!acc[dateKey]) acc[dateKey] = []
    acc[dateKey].push(log)
    return acc
  }, {})

  const successCount = logs.filter(l => l.status === 'success').length
  const errorCount = logs.filter(l => l.status === 'error').length

  return (
    <div className="page-content">
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/accounts')} title="Back to Accounts">
            <ArrowLeft size={14} />
          </button>
          <h2>
            <History size={20} />
            Sync History
          </h2>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          {logs.length > 0 && (
            <div style={{ display: 'flex', gap: 12, fontSize: 13, color: 'var(--text-muted)' }}>
              <span style={{ color: 'var(--green)' }}>{successCount} successful</span>
              {errorCount > 0 && <span style={{ color: 'var(--red)' }}>{errorCount} failed</span>}
            </div>
          )}
          <button className="btn btn-secondary btn-sm" onClick={fetchLogs} disabled={loading}>
            <RefreshCw size={12} className={loading ? 'spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading sync history...
        </div>
      ) : logs.length === 0 ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          No sync history yet. Syncs will appear here after the first sync completes.
        </div>
      ) : (
        <div className="card">
          <div className="data-table-wrapper">
            <table className="data-table sync-history-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Account</th>
                  <th>Trigger</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Added</th>
                  <th style={{ textAlign: 'right' }}>Modified</th>
                  <th style={{ textAlign: 'right' }}>Removed</th>
                  <th style={{ textAlign: 'right' }}>Duration</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(groupedByDate).map(([dateLabel, dateLogs]) => (
                  <React.Fragment key={dateLabel}>
                    <tr className="sync-date-separator">
                      <td colSpan={9}>{dateLabel}</td>
                    </tr>
                    {dateLogs.map(log => (
                      <tr key={log.id}>
                        <td style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                          {formatTimestamp(log.started_at)}
                        </td>
                        <td style={{ fontWeight: 500 }}>{log.account_name}</td>
                        <td>
                          <span className={`sync-trigger-badge ${log.trigger}`}>
                            {triggerLabel(log.trigger)}
                          </span>
                        </td>
                        <td>{statusIcon(log.status)}</td>
                        <td style={{ textAlign: 'right', color: log.added > 0 ? 'var(--green)' : 'var(--text-muted)' }}>
                          {log.added > 0 ? `+${log.added}` : '—'}
                        </td>
                        <td style={{ textAlign: 'right', color: log.modified > 0 ? 'var(--accent)' : 'var(--text-muted)' }}>
                          {log.modified > 0 ? `~${log.modified}` : '—'}
                        </td>
                        <td style={{ textAlign: 'right', color: log.removed > 0 ? 'var(--red)' : 'var(--text-muted)' }}>
                          {log.removed > 0 ? `-${log.removed}` : '—'}
                        </td>
                        <td style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-muted)' }}>
                          {log.duration_seconds != null ? `${log.duration_seconds}s` : '—'}
                        </td>
                        <td style={{ fontSize: 11, color: 'var(--red)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                            title={log.error_message || ''}>
                          {log.error_message ? log.error_message.slice(0, 60) + (log.error_message.length > 60 ? '...' : '') : ''}
                        </td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
