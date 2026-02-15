import React, { useState, useEffect, useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { ChevronRight, ChevronDown, Loader } from 'lucide-react'
import CategoryPicker from '../components/CategoryPicker'

export default function Spending() {
  const savedSp = sessionStorage.getItem('spendingFilters')
  const persistedSp = savedSp ? JSON.parse(savedSp) : {}

  const [categoryData, setCategoryData] = useState([])
  const [trendData, setTrendData] = useState([])
  const [selectedMonth, setSelectedMonth] = useState(() => {
    if (persistedSp.month) return persistedSp.month
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  })

  // Two-level expand state
  const [expandedParents, setExpandedParents] = useState(new Set()) // expanded parent group keys
  const [expandedCat, setExpandedCat] = useState(null)              // subcategory id showing transactions
  const [expandedTxns, setExpandedTxns] = useState([])
  const [loadingTxns, setLoadingTxns] = useState(false)
  const [editingTxnId, setEditingTxnId] = useState(null)
  const [categoryTree, setCategoryTree] = useState([])

  useEffect(() => {
    fetchCategorySpending()
    fetchTrend()
    sessionStorage.setItem('spendingFilters', JSON.stringify({ month: selectedMonth }))
  }, [selectedMonth])

  useEffect(() => { fetchCategoryTree() }, [])

  // Reset expand state when month changes
  useEffect(() => {
    setExpandedParents(new Set())
    setExpandedCat(null)
    setExpandedTxns([])
    setEditingTxnId(null)
  }, [selectedMonth])

  const fetchCategorySpending = async () => {
    try {
      const res = await fetch(`/api/transactions/spending-by-category?month=${selectedMonth}`)
      if (res.ok) {
        const data = await res.json()
        setCategoryData(data)
      }
    } catch (err) {
      console.error('Failed to fetch spending:', err)
    }
  }

  const fetchTrend = async () => {
    try {
      const res = await fetch('/api/transactions/monthly-trend?months=12')
      if (res.ok) setTrendData(await res.json())
    } catch (err) {
      console.error('Failed to fetch trend:', err)
    }
  }

  const fetchCategoryTree = async () => {
    try {
      const res = await fetch('/api/categories/tree')
      if (res.ok) setCategoryTree(await res.json())
    } catch (err) {
      console.error('Failed to fetch category tree:', err)
    }
  }

  // Group flat subcategory data into parent → children hierarchy
  const groupedCategories = useMemo(() => {
    const groups = new Map()

    for (const cat of categoryData) {
      // Key: parent_id if it has one, otherwise its own id (standalone parent)
      const groupKey = cat.parent_id || cat.id
      const groupName = cat.parent_display_name || cat.display_name
      const groupColor = cat.parent_color || cat.color

      if (!groups.has(groupKey)) {
        groups.set(groupKey, {
          key: groupKey,
          display_name: groupName,
          color: groupColor,
          total: 0,
          count: 0,
          children: [],
        })
      }

      const group = groups.get(groupKey)
      group.total += cat.total
      group.count += cat.count
      group.children.push(cat)
    }

    // Sort children within each group by total desc
    for (const group of groups.values()) {
      group.children.sort((a, b) => b.total - a.total)
    }

    return [...groups.values()].sort((a, b) => b.total - a.total)
  }, [categoryData])

  const totalSpending = categoryData.reduce((sum, c) => sum + c.total, 0)

  // Toggle parent group expand
  const toggleParent = (groupKey) => {
    setExpandedParents(prev => {
      const next = new Set(prev)
      if (next.has(groupKey)) {
        next.delete(groupKey)
        // Also collapse any open transaction rows within this parent
        setExpandedCat(null)
        setExpandedTxns([])
        setEditingTxnId(null)
      } else {
        next.add(groupKey)
      }
      return next
    })
  }

  // Toggle subcategory expand (fetch transactions)
  const toggleSubcategory = async (cat) => {
    if (expandedCat === cat.id) {
      setExpandedCat(null)
      setExpandedTxns([])
      setEditingTxnId(null)
      return
    }

    setExpandedCat(cat.id)
    setExpandedTxns([])
    setEditingTxnId(null)
    setLoadingTxns(true)

    const [year, month] = selectedMonth.split('-')
    const startDate = `${year}-${month}-01`
    const lastDay = new Date(parseInt(year), parseInt(month), 0).getDate()
    const endDate = `${year}-${month}-${String(lastDay).padStart(2, '0')}`

    try {
      const res = await fetch(
        `/api/transactions/?category_id=${cat.id}&start_date=${startDate}&end_date=${endDate}&limit=500`
      )
      if (res.ok) {
        const txns = await res.json()
        txns.sort((a, b) => b.date.localeCompare(a.date))
        setExpandedTxns(txns)
      }
    } catch (err) {
      console.error('Failed to fetch category transactions:', err)
    } finally {
      setLoadingTxns(false)
    }
  }

  const handleRecategorize = async (txnId, shortDesc) => {
    setEditingTxnId(null)
    try {
      const res = await fetch(`/api/transactions/${txnId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category_short_desc: shortDesc }),
      })
      if (res.ok) {
        setExpandedTxns(prev => prev.filter(t => t.id !== txnId))
        fetchCategorySpending()
      }
    } catch (err) {
      console.error('Failed to recategorize:', err)
    }
  }

  const COLORS = [
    '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
    '#DDA0DD', '#BB8FCE', '#F7DC6F', '#F1948A', '#85C1E9',
    '#73C6B6', '#F0B27A', '#AEB6BF', '#58D68D', '#FAD7A0',
  ]

  const formatMonth = (monthStr) => {
    const [year, month] = monthStr.split('-')
    const date = new Date(year, month - 1)
    return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
  }

  const formatDate = (dateStr) => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  // For pie chart: use parent-level grouping
  const pieData = useMemo(() =>
    groupedCategories.slice(0, 10).map(g => ({
      display_name: g.display_name,
      total: g.total,
      color: g.color,
      short_desc: g.key,
    })),
    [groupedCategories]
  )

  return (
    <div>
      <div className="page-header">
        <h2>Spending Overview</h2>
        <p>Track where your money goes</p>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="label">Total Spending ({formatMonth(selectedMonth)})</div>
          <div className="value red">${totalSpending.toFixed(2)}</div>
        </div>
        <div className="stat-card">
          <div className="label">Categories</div>
          <div className="value">{groupedCategories.length}</div>
        </div>
        <div className="stat-card">
          <div className="label">Month</div>
          <div style={{ marginTop: 8 }}>
            <input
              type="month"
              className="month-input"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
            />
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
        {/* Monthly Trend */}
        <div className="card">
          <div className="card-header">
            <h3>Monthly Trend</h3>
          </div>
          <div className="chart-container">
            {trendData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="month" tickFormatter={formatMonth} stroke="var(--text-muted)" fontSize={12} />
                  <YAxis stroke="var(--text-muted)" fontSize={12} tickFormatter={(v) => `$${v}`} />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                    labelFormatter={formatMonth}
                    formatter={(value) => [`$${value.toFixed(2)}`, 'Spending']}
                  />
                  <Bar dataKey="total" fill="var(--accent)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                <p>No spending data yet. Import transactions to see trends.</p>
              </div>
            )}
          </div>
        </div>

        {/* Category Breakdown (Pie) — now uses parent grouping */}
        <div className="card">
          <div className="card-header">
            <h3>By Category</h3>
          </div>
          <div className="chart-container">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="total"
                    nameKey="display_name"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={({ display_name, percent }) =>
                      `${display_name} (${(percent * 100).toFixed(0)}%)`
                    }
                    labelLine={false}
                    fontSize={11}
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={entry.short_desc} fill={entry.color || COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => `$${value.toFixed(2)}`} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                <p>No category data for this month.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Category Breakdown Table — grouped by parent */}
      <div className="card">
        <div className="card-header">
          <h3>Category Breakdown</h3>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Click to expand categories and transactions
          </span>
        </div>
        {groupedCategories.length > 0 ? (
          <table className="txn-table">
            <thead>
              <tr>
                <th>Category</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
                <th style={{ textAlign: 'right' }}>Transactions</th>
                <th style={{ textAlign: 'right' }}>% of Total</th>
              </tr>
            </thead>
            <tbody>
              {groupedCategories.map(group => {
                const isParentExpanded = expandedParents.has(group.key)
                const hasMultipleChildren = group.children.length > 1

                return (
                  <React.Fragment key={group.key}>
                    {/* Parent group row */}
                    <tr
                      className="sp-expandable sp-parent-row"
                      onClick={() => hasMultipleChildren
                        ? toggleParent(group.key)
                        : toggleSubcategory(group.children[0])
                      }
                    >
                      <td>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {hasMultipleChildren ? (
                            isParentExpanded
                              ? <ChevronDown size={14} className="sp-chevron" />
                              : <ChevronRight size={14} className="sp-chevron" />
                          ) : (
                            expandedCat === group.children[0]?.id
                              ? <ChevronDown size={14} className="sp-chevron" />
                              : <ChevronRight size={14} className="sp-chevron" />
                          )}
                          <span style={{
                            display: 'inline-block',
                            width: 10,
                            height: 10,
                            borderRadius: '50%',
                            backgroundColor: group.color || 'var(--accent)',
                            flexShrink: 0,
                          }} />
                          <span style={{ fontWeight: 600 }}>{group.display_name}</span>
                          {hasMultipleChildren && (
                            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 4 }}>
                              ({group.children.length})
                            </span>
                          )}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right', fontWeight: 600 }}>${group.total.toFixed(2)}</td>
                      <td style={{ textAlign: 'right' }}>{group.count}</td>
                      <td style={{ textAlign: 'right' }}>
                        {totalSpending > 0 ? ((group.total / totalSpending) * 100).toFixed(1) : 0}%
                      </td>
                    </tr>

                    {/* Single-child parent: show transactions directly */}
                    {!hasMultipleChildren && expandedCat === group.children[0]?.id && (
                      <TransactionRows
                        loading={loadingTxns}
                        transactions={expandedTxns}
                        editingTxnId={editingTxnId}
                        setEditingTxnId={setEditingTxnId}
                        categoryTree={categoryTree}
                        onRecategorize={handleRecategorize}
                        fetchCategoryTree={fetchCategoryTree}
                        formatDate={formatDate}
                        indent={1}
                      />
                    )}

                    {/* Multi-child parent: show subcategory rows */}
                    {hasMultipleChildren && isParentExpanded && group.children.map(cat => (
                      <React.Fragment key={cat.id}>
                        <tr
                          className="sp-expandable sp-child-row"
                          onClick={() => toggleSubcategory(cat)}
                        >
                          <td>
                            <span className="sp-subcat-name">
                              {expandedCat === cat.id
                                ? <ChevronDown size={12} className="sp-chevron" />
                                : <ChevronRight size={12} className="sp-chevron" />
                              }
                              {cat.display_name}
                            </span>
                          </td>
                          <td style={{ textAlign: 'right' }}>${cat.total.toFixed(2)}</td>
                          <td style={{ textAlign: 'right' }}>{cat.count}</td>
                          <td style={{ textAlign: 'right' }}>
                            {totalSpending > 0 ? ((cat.total / totalSpending) * 100).toFixed(1) : 0}%
                          </td>
                        </tr>

                        {expandedCat === cat.id && (
                          <TransactionRows
                            loading={loadingTxns}
                            transactions={expandedTxns}
                            editingTxnId={editingTxnId}
                            setEditingTxnId={setEditingTxnId}
                            categoryTree={categoryTree}
                            onRecategorize={handleRecategorize}
                            fetchCategoryTree={fetchCategoryTree}
                            formatDate={formatDate}
                            indent={2}
                          />
                        )}
                      </React.Fragment>
                    ))}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <p>No spending data for this month.</p>
          </div>
        )}
      </div>
    </div>
  )
}

/* ─── Transaction Rows (extracted for reuse at both indent levels) ─── */
function TransactionRows({
  loading, transactions, editingTxnId, setEditingTxnId,
  categoryTree, onRecategorize, fetchCategoryTree, formatDate, indent,
}) {
  const paddingLeft = indent === 2 ? 56 : 42

  if (loading) {
    return (
      <tr className="sp-txn-row">
        <td colSpan={4}>
          <div className="sp-loading" style={{ paddingLeft }}>
            <Loader size={14} className="spin" />
            <span>Loading transactions...</span>
          </div>
        </td>
      </tr>
    )
  }

  if (transactions.length === 0) {
    return (
      <tr className="sp-txn-row">
        <td colSpan={4}>
          <div style={{ padding: `12px ${paddingLeft}px`, color: 'var(--text-muted)', fontSize: 13 }}>
            No transactions found for this category.
          </div>
        </td>
      </tr>
    )
  }

  return transactions.map(txn => (
    <tr key={txn.id} className="sp-txn-row">
      <td colSpan={4}>
        <div className="sp-txn-cell" style={{ paddingLeft }}>
          <span className="sp-txn-date">{formatDate(txn.date)}</span>
          <span className="sp-txn-desc" title={txn.description}>
            {txn.merchant_name || txn.description}
          </span>
          <span className={`sp-txn-amount ${txn.amount > 0 ? 'expense' : 'income'}`}>
            {txn.amount > 0 ? '-' : '+'}${Math.abs(txn.amount).toFixed(2)}
          </span>
          <span className="sp-txn-cat-area" onClick={(e) => e.stopPropagation()}>
            <span
              className="sp-cat-badge"
              onClick={() => setEditingTxnId(editingTxnId === txn.id ? null : txn.id)}
              title="Click to change category"
            >
              {txn.category_name || '—'}
            </span>
            {editingTxnId === txn.id && (
              <CategoryPicker
                categoryTree={categoryTree}
                onSelect={(shortDesc) => onRecategorize(txn.id, shortDesc)}
                onCancel={() => setEditingTxnId(null)}
                onTreeChanged={fetchCategoryTree}
              />
            )}
          </span>
        </div>
      </td>
    </tr>
  ))
}
