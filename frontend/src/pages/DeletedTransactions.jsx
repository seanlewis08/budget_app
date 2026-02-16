import React, { useState, useEffect } from 'react'
import { Trash2, RotateCcw, CheckSquare, Square, MinusSquare, AlertTriangle, ArrowLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDeletedAt(isoStr) {
  if (!isoStr) return '—'
  const normalized = isoStr.endsWith('Z') || isoStr.includes('+') ? isoStr : isoStr + 'Z'
  const d = new Date(normalized)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) +
    ' ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

function formatCurrency(amount) {
  if (amount == null) return '—'
  const abs = Math.abs(amount)
  return `${amount < 0 ? '+' : ''}$${abs.toFixed(2)}`
}

export default function DeletedTransactions() {
  const navigate = useNavigate()
  const [deletedTxns, setDeletedTxns] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [restoring, setRestoring] = useState(false)
  const [purging, setPurging] = useState(false)
  const [confirmClearAll, setConfirmClearAll] = useState(false)

  useEffect(() => {
    fetchDeletedTransactions()
  }, [])

  const fetchDeletedTransactions = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/transactions/deleted')
      if (res.ok) setDeletedTxns(await res.json())
    } catch (err) {
      console.error('Failed to fetch deleted transactions:', err)
    } finally {
      setLoading(false)
    }
  }

  // ── Restore ──

  const handleRestore = async (deletedId) => {
    setRestoring(true)
    try {
      const res = await fetch(`/api/transactions/restore/${deletedId}`, { method: 'POST' })
      if (res.ok) {
        setDeletedTxns(prev => prev.filter(t => t.id !== deletedId))
        setSelectedIds(prev => { const next = new Set(prev); next.delete(deletedId); return next })
      }
    } catch (err) {
      console.error('Restore failed:', err)
    } finally {
      setRestoring(false)
    }
  }

  const handleBulkRestore = async () => {
    if (selectedIds.size === 0) return
    setRestoring(true)
    try {
      const res = await fetch('/api/transactions/bulk-restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deleted_ids: [...selectedIds] }),
      })
      if (res.ok) {
        const data = await res.json()
        const restoredSet = new Set(data.deleted_ids)
        setDeletedTxns(prev => prev.filter(t => !restoredSet.has(t.id)))
        setSelectedIds(new Set())
      }
    } catch (err) {
      console.error('Bulk restore failed:', err)
    } finally {
      setRestoring(false)
    }
  }

  // ── Purge (permanent delete) ──

  const handlePurgeOne = async (deletedId) => {
    setPurging(true)
    try {
      const res = await fetch(`/api/transactions/deleted/${deletedId}`, { method: 'DELETE' })
      if (res.ok) {
        setDeletedTxns(prev => prev.filter(t => t.id !== deletedId))
        setSelectedIds(prev => { const next = new Set(prev); next.delete(deletedId); return next })
      }
    } catch (err) {
      console.error('Purge failed:', err)
    } finally {
      setPurging(false)
    }
  }

  const handleClearAll = async () => {
    setPurging(true)
    try {
      const res = await fetch('/api/transactions/deleted', { method: 'DELETE' })
      if (res.ok) {
        setDeletedTxns([])
        setSelectedIds(new Set())
        setConfirmClearAll(false)
      }
    } catch (err) {
      console.error('Clear all failed:', err)
    } finally {
      setPurging(false)
    }
  }

  // ── Selection ──

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allSelected = deletedTxns.length > 0 && deletedTxns.every(t => selectedIds.has(t.id))
  const someSelected = deletedTxns.some(t => selectedIds.has(t.id))

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(deletedTxns.map(t => t.id)))
    }
  }

  return (
    <div className="page-content deleted-txns-page">
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/settings')} title="Back to Settings">
            <ArrowLeft size={14} />
          </button>
          <h2>
            <Trash2 size={20} />
            Deleted Transactions
            {deletedTxns.length > 0 && (
              <span className="deleted-count-badge">{deletedTxns.length}</span>
            )}
          </h2>
        </div>

        {deletedTxns.length > 0 && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {confirmClearAll ? (
              <>
                <span style={{ fontSize: 13, color: 'var(--danger)' }}>
                  <AlertTriangle size={14} style={{ verticalAlign: -2 }} /> Permanently delete all {deletedTxns.length} records?
                </span>
                <button className="btn btn-danger btn-sm" onClick={handleClearAll} disabled={purging}>
                  Yes, Clear All
                </button>
                <button className="btn btn-secondary btn-sm" onClick={() => setConfirmClearAll(false)}>
                  Cancel
                </button>
              </>
            ) : (
              <button className="btn btn-danger btn-sm" onClick={() => setConfirmClearAll(true)}>
                <Trash2 size={12} /> Clear All
              </button>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading deleted transactions...
        </div>
      ) : deletedTxns.length === 0 ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          No deleted transactions. Transactions you delete will appear here for review.
        </div>
      ) : (
        <div className="card">
          {/* Bulk action bar */}
          {selectedIds.size > 0 && (
            <div className="bulk-action-bar">
              <span className="bulk-count">{selectedIds.size} selected</span>
              <div className="bulk-actions">
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleBulkRestore}
                  disabled={restoring}
                >
                  <RotateCcw size={12} /> Restore ({selectedIds.size})
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setSelectedIds(new Set())}
                >
                  Deselect
                </button>
              </div>
            </div>
          )}

          <div className="data-table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 36, textAlign: 'center', cursor: 'pointer' }} onClick={toggleSelectAll}>
                    {allSelected
                      ? <CheckSquare size={15} />
                      : someSelected
                        ? <MinusSquare size={15} />
                        : <Square size={15} />
                    }
                  </th>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Account</th>
                  <th style={{ textAlign: 'right' }}>Amount</th>
                  <th>Category</th>
                  <th>Deleted</th>
                  <th style={{ width: 160 }}></th>
                </tr>
              </thead>
              <tbody>
                {deletedTxns.map(txn => (
                  <tr
                    key={txn.id}
                    className={`data-row ${selectedIds.has(txn.id) ? 'selected' : ''}`}
                    onClick={() => toggleSelect(txn.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ textAlign: 'center', width: 36 }} onClick={(e) => e.stopPropagation()}>
                      <span onClick={() => toggleSelect(txn.id)} style={{ cursor: 'pointer' }}>
                        {selectedIds.has(txn.id) ? <CheckSquare size={15} /> : <Square size={15} />}
                      </span>
                    </td>
                    <td className="data-cell-date">{formatDate(txn.date)}</td>
                    <td className="data-cell-desc" title={txn.description}>
                      {txn.description}
                    </td>
                    <td className="data-cell-account">{txn.account_name || '—'}</td>
                    <td className={`data-cell-amount ${txn.amount > 0 ? 'expense' : 'income'}`}>
                      {formatCurrency(txn.amount)}
                    </td>
                    <td>
                      <span className="data-cat-badge">{txn.category_name || '—'}</span>
                    </td>
                    <td className="deleted-at-cell">{formatDeletedAt(txn.deleted_at)}</td>
                    <td style={{ textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                      <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                        <button
                          className="btn btn-sm deleted-restore-btn"
                          onClick={() => handleRestore(txn.id)}
                          disabled={restoring}
                          title="Restore transaction"
                        >
                          <RotateCcw size={12} /> Restore
                        </button>
                        <button
                          className="btn btn-sm btn-danger-outline"
                          onClick={() => handlePurgeOne(txn.id)}
                          disabled={purging}
                          title="Permanently delete"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
