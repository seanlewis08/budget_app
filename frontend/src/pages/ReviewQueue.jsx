import React, { useState, useEffect } from 'react'
import { CheckCircle, ArrowRight, Upload } from 'lucide-react'

export default function ReviewQueue({ stats, onUpdate }) {
  const [transactions, setTransactions] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState(null)

  useEffect(() => {
    fetchPending()
    fetchCategories()
  }, [])

  const fetchPending = async () => {
    try {
      const res = await fetch('/api/transactions/pending')
      if (res.ok) {
        const data = await res.json()
        setTransactions(data)
      }
    } catch (err) {
      console.error('Failed to fetch pending:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchCategories = async () => {
    try {
      const res = await fetch('/api/categories/?parent_only=false')
      if (res.ok) {
        const data = await res.json()
        // Only subcategories (those with a parent)
        setCategories(data.filter(c => c.parent_id))
      }
    } catch (err) {
      console.error('Failed to fetch categories:', err)
    }
  }

  const confirmTransaction = async (txnId, shortDesc) => {
    try {
      const res = await fetch(`/api/transactions/${txnId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category_short_desc: shortDesc }),
      })
      if (res.ok) {
        setTransactions(prev => prev.filter(t => t.id !== txnId))
        setEditingId(null)
        onUpdate()
      }
    } catch (err) {
      console.error('Failed to confirm:', err)
    }
  }

  const confirmAll = async () => {
    const confirmable = transactions.filter(t => t.predicted_category_id)
    if (confirmable.length === 0) return

    try {
      const res = await fetch('/api/transactions/bulk-review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transaction_ids: confirmable.map(t => t.id),
          action: 'confirm',
        }),
      })
      if (res.ok) {
        fetchPending()
        onUpdate()
      }
    } catch (err) {
      console.error('Failed to bulk confirm:', err)
    }
  }

  const formatDate = (dateStr) => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  const formatAmount = (amount) => {
    const abs = Math.abs(amount)
    return `$${abs.toFixed(2)}`
  }

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h2>Review Queue</h2>
          <p>Loading transactions...</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h2>Review Queue</h2>
        <p>{transactions.length} transaction{transactions.length !== 1 ? 's' : ''} awaiting review</p>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="label">Pending Review</div>
          <div className={`value ${stats.pending_review > 0 ? 'yellow' : 'green'}`}>
            {stats.pending_review}
          </div>
        </div>
        <div className="stat-card">
          <div className="label">Confirmed</div>
          <div className="value green">{stats.confirmed}</div>
        </div>
        <div className="stat-card">
          <div className="label">Total Transactions</div>
          <div className="value">{stats.total_transactions}</div>
        </div>
      </div>

      {transactions.length > 0 ? (
        <>
          <div className="card">
            <div className="card-header">
              <h3>Transactions to Review</h3>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button className="btn btn-confirm" onClick={confirmAll}>
                  <CheckCircle size={14} style={{ marginRight: 4 }} />
                  Confirm All ({transactions.filter(t => t.predicted_category_id).length})
                </button>
              </div>
            </div>
            <div className="review-list">
              {transactions.map(txn => (
                <div key={txn.id} className="review-item">
                  <span className="date">{formatDate(txn.date)}</span>
                  <span className="description" title={txn.description}>
                    {txn.merchant_name || txn.description}
                  </span>
                  <span className="account-tag">{txn.account_name}</span>
                  <span className={`amount ${txn.amount > 0 ? 'expense' : 'income'}`}>
                    {txn.amount > 0 ? '-' : '+'}{formatAmount(txn.amount)}
                  </span>

                  {editingId === txn.id ? (
                    <select
                      className="category-select"
                      defaultValue={txn.category_short_desc || ''}
                      onChange={(e) => {
                        if (e.target.value) {
                          confirmTransaction(txn.id, e.target.value)
                        }
                      }}
                      autoFocus
                      onBlur={() => setEditingId(null)}
                    >
                      <option value="">Select category...</option>
                      {categories.map(cat => (
                        <option key={cat.id} value={cat.short_desc}>
                          {cat.parent_name ? `${cat.parent_name} > ` : ''}{cat.display_name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span
                      className="predicted"
                      onClick={() => setEditingId(txn.id)}
                      style={{ cursor: 'pointer' }}
                      title="Click to change"
                    >
                      <ArrowRight size={12} />
                      {txn.predicted_category_name || 'Uncategorized'}
                    </span>
                  )}

                  <div className="actions">
                    {txn.predicted_category_id && (
                      <button
                        className="btn btn-confirm"
                        onClick={() => confirmTransaction(txn.id, txn.category_short_desc)}
                        title="Confirm this category"
                      >
                        <CheckCircle size={14} />
                      </button>
                    )}
                    <button
                      className="btn btn-secondary"
                      onClick={() => setEditingId(editingId === txn.id ? null : txn.id)}
                    >
                      Change
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="card">
          <div className="empty-state">
            <div className="icon"><CheckCircle size={48} /></div>
            <h3>All caught up!</h3>
            <p>No transactions to review. Import a CSV or connect your bank to get started.</p>
          </div>
        </div>
      )}
    </div>
  )
}
