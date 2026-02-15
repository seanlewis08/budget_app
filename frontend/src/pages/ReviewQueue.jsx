import React, { useState, useEffect, useRef } from 'react'
import { CheckCircle, ArrowRight, ChevronRight, ChevronDown, Plus, X, Undo2, Save, Zap, Loader, Trash2, ArrowUpDown, Filter, Square, CheckSquare, MinusSquare, Search } from 'lucide-react'
import CategoryPicker from '../components/CategoryPicker'

/* ─── Custom Category Filter Dropdown (expandable) ─── */
function CategoryFilterDropdown({ predictedCategories, value, onChange }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(new Set()) // parent names that are expanded
  const ref = useRef(null)
  const searchRef = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    if (open) setTimeout(() => searchRef.current?.focus(), 0)
  }, [open])

  const getLabel = () => {
    if (!value) return 'All Categories'
    if (value.startsWith('parent:')) return value.slice(7)
    return value
  }

  const toggleExpand = (name, e) => {
    e.stopPropagation()
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const q = search.toLowerCase()
  const isSearching = q.length > 0
  const filtered = isSearching
    ? predictedCategories.map(pg => ({
        ...pg,
        children: pg.children.filter(ch => ch.name.toLowerCase().includes(q)),
        parentMatch: pg.name.toLowerCase().includes(q),
      })).filter(pg => pg.parentMatch || pg.children.length > 0)
    : predictedCategories

  const handleSelect = (val) => {
    onChange(val)
    setOpen(false)
    setSearch('')
  }

  if (predictedCategories.length === 0) return null

  return (
    <div className="filter-dropdown" ref={ref}>
      <button
        className={`filter-dropdown-trigger ${value ? 'active' : ''}`}
        onClick={() => setOpen(!open)}
      >
        <Filter size={12} />
        <span>{getLabel()}</span>
        {value && (
          <span
            className="filter-clear"
            onClick={(e) => { e.stopPropagation(); onChange(''); }}
          >
            <X size={10} />
          </span>
        )}
        <ChevronDown size={12} style={{ opacity: 0.5, marginLeft: 2 }} />
      </button>
      {open && (
        <div className="filter-dropdown-panel">
          <input
            ref={searchRef}
            type="text"
            className="filter-dropdown-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search..."
          />
          <div className="filter-dropdown-list">
            <div
              className={`filter-dropdown-item ${!value ? 'selected' : ''}`}
              onClick={() => handleSelect('')}
            >
              All Categories
            </div>
            {filtered.map(pg => {
              const isExpanded = isSearching || expanded.has(pg.name)
              const hasChildren = pg.children.length > 0
              return (
                <React.Fragment key={pg.name}>
                  <div
                    className={`filter-dropdown-item filter-parent ${value === `parent:${pg.name}` ? 'selected' : ''}`}
                    onClick={() => handleSelect(`parent:${pg.name}`)}
                  >
                    {hasChildren && (
                      <span className="filter-expand-toggle" onClick={(e) => toggleExpand(pg.name, e)}>
                        {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      </span>
                    )}
                    <span className="filter-parent-name">{pg.name}</span>
                    <span className="filter-count">{pg.count}</span>
                  </div>
                  {hasChildren && isExpanded && pg.children.map(ch => (
                    <div
                      key={ch.name}
                      className={`filter-dropdown-item filter-child ${value === ch.name ? 'selected' : ''}`}
                      onClick={() => handleSelect(ch.name)}
                    >
                      <span className="filter-child-name">{ch.name}</span>
                      <span className="filter-count">{ch.count}</span>
                    </div>
                  ))}
                </React.Fragment>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

/* ─── Review Queue Page ─── */
export default function ReviewQueue({ stats, onUpdate }) {
  const savedRQ = sessionStorage.getItem('reviewQueueFilters')
  const persistedRQ = savedRQ ? JSON.parse(savedRQ) : {}

  const [pendingTxns, setPendingTxns] = useState([])
  const [stagedTxns, setStagedTxns] = useState([])
  const [categoryTree, setCategoryTree] = useState([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState(null)
  const [selectedYear, setSelectedYear] = useState(persistedRQ.year ?? '')
  const [availableYears, setAvailableYears] = useState([])
  const [activeTab, setActiveTab] = useState(persistedRQ.tab ?? 'review') // 'review' or 'staged'
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchResult, setBatchResult] = useState(null)
  const [batchProgress, setBatchProgress] = useState({ current: 0, total: 0 })
  const [committing, setCommitting] = useState(false)
  const [sortOrder, setSortOrder] = useState(persistedRQ.sortOrder ?? 'desc')
  const [filterCategory, setFilterCategory] = useState(persistedRQ.filterCategory ?? '')
  const [selectedIds, setSelectedIds] = useState(new Set()) // multi-select
  const [bulkPickerOpen, setBulkPickerOpen] = useState(false) // category picker for bulk assign
  const [descSearch, setDescSearch] = useState(persistedRQ.descSearch ?? '')
  const batchAbortRef = useRef(false)
  const lastClickedIndexRef = useRef(null) // for shift-click range selection

  useEffect(() => {
    fetchPending()
    fetchStaged()
    fetchCategoryTree()
    fetchYears()
  }, [])

  useEffect(() => {
    fetchPending()
    fetchStaged()
  }, [selectedYear])

  // Persist filters
  useEffect(() => {
    sessionStorage.setItem('reviewQueueFilters', JSON.stringify({
      year: selectedYear,
      tab: activeTab,
      sortOrder,
      filterCategory,
      descSearch,
    }))
  }, [selectedYear, activeTab, sortOrder, filterCategory, descSearch])

  // Clear selection when tab/filter changes
  useEffect(() => {
    setSelectedIds(new Set())
    setBulkPickerOpen(false)
  }, [activeTab, filterCategory, descSearch])

  const fetchYears = async () => {
    try {
      const res = await fetch('/api/transactions/years')
      if (res.ok) setAvailableYears(await res.json())
    } catch (err) {
      console.error('Failed to fetch years:', err)
    }
  }

  const fetchPending = async () => {
    try {
      const url = selectedYear
        ? `/api/transactions/pending?year=${selectedYear}`
        : '/api/transactions/pending'
      const res = await fetch(url)
      if (res.ok) setPendingTxns(await res.json())
    } catch (err) {
      console.error('Failed to fetch pending:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchStaged = async () => {
    try {
      const url = selectedYear
        ? `/api/transactions/staged?year=${selectedYear}`
        : '/api/transactions/staged'
      const res = await fetch(url)
      if (res.ok) setStagedTxns(await res.json())
    } catch (err) {
      console.error('Failed to fetch staged:', err)
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

  // Stage a transaction (pending_review → pending_save)
  const stageTransaction = async (txnId, shortDesc) => {
    try {
      const res = await fetch(`/api/transactions/${txnId}/stage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category_short_desc: shortDesc }),
      })
      if (res.ok) {
        setPendingTxns(prev => prev.filter(t => t.id !== txnId))
        setEditingId(null)
        setSelectedIds(prev => { const next = new Set(prev); next.delete(txnId); return next })
        fetchStaged()
        onUpdate()
      }
    } catch (err) {
      console.error('Failed to stage:', err)
    }
  }

  // Bulk stage all predicted (respects active filter + search)
  const stageAllPredicted = async () => {
    const source = (filterCategory || descSearch)
      ? filteredTransactions
      : pendingTxns
    const confirmable = source.filter(t => t.predicted_category_id)
    if (confirmable.length === 0) return
    const stagedIdSet = new Set(confirmable.map(t => t.id))

    try {
      const res = await fetch('/api/transactions/bulk-stage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transaction_ids: confirmable.map(t => t.id),
          action: 'confirm',
        }),
      })
      if (res.ok) {
        setPendingTxns(prev => prev.filter(t => !stagedIdSet.has(t.id)))
        setSelectedIds(new Set())
        fetchStaged()
        onUpdate()
      }
    } catch (err) {
      console.error('Failed to bulk stage:', err)
    }
  }

  // Bulk assign category to selected transactions
  const bulkAssignCategory = async (shortDesc) => {
    const ids = [...selectedIds]
    if (ids.length === 0) return
    setBulkPickerOpen(false)
    const idSet = new Set(ids)

    try {
      const res = await fetch('/api/transactions/bulk-stage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transaction_ids: ids,
          action: 'change',
          category_short_desc: shortDesc,
        }),
      })
      if (res.ok) {
        // Optimistically remove staged items from pending list
        setPendingTxns(prev => prev.filter(t => !idSet.has(t.id)))
        setSelectedIds(new Set())
        fetchStaged()
        onUpdate()
      }
    } catch (err) {
      console.error('Failed to bulk assign:', err)
    }
  }

  // Bulk stage selected that have predictions
  const bulkStageSelected = async () => {
    const ids = [...selectedIds]
    const withPredictions = transactions.filter(t => ids.includes(t.id) && t.predicted_category_id)
    if (withPredictions.length === 0) return
    const stagedIdSet = new Set(withPredictions.map(t => t.id))

    try {
      const res = await fetch('/api/transactions/bulk-stage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transaction_ids: withPredictions.map(t => t.id),
          action: 'confirm',
        }),
      })
      if (res.ok) {
        setPendingTxns(prev => prev.filter(t => !stagedIdSet.has(t.id)))
        setSelectedIds(new Set())
        fetchStaged()
        onUpdate()
      }
    } catch (err) {
      console.error('Failed to bulk stage selected:', err)
    }
  }

  // Kick back a staged transaction (pending_save → pending_review)
  const kickBack = async (txnId) => {
    try {
      const res = await fetch(`/api/transactions/${txnId}/kick-back`, {
        method: 'POST',
      })
      if (res.ok) {
        setStagedTxns(prev => prev.filter(t => t.id !== txnId))
        fetchPending()
        onUpdate()
      }
    } catch (err) {
      console.error('Failed to kick back:', err)
    }
  }

  // Commit all staged → confirmed
  const commitAll = async () => {
    if (!window.confirm(`Save ${stagedTxns.length} staged transactions? This will update merchant mappings and finalize categories.`)) return
    setCommitting(true)
    try {
      const res = await fetch('/api/transactions/staged/commit', { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setStagedTxns([])
        fetchPending()
        fetchStaged()
        onUpdate()
        alert(`Saved ${data.committed} transactions, updated ${data.mappings_updated} merchant mappings.`)
      } else {
        const err = await res.json().catch(() => ({}))
        alert(`Failed to save: ${err.detail || res.statusText || 'Unknown error'} (${res.status})`)
      }
    } catch (err) {
      console.error('Failed to commit:', err)
      alert(`Network error saving transactions: ${err.message}`)
    } finally {
      setCommitting(false)
    }
  }

  // Revert all staged → pending_review
  const revertAll = async () => {
    if (!window.confirm(`Revert all ${stagedTxns.length} staged transactions back to review?`)) return
    try {
      const res = await fetch('/api/transactions/staged/revert-all', { method: 'POST' })
      if (res.ok) {
        setStagedTxns([])
        fetchPending()
        onUpdate()
      }
    } catch (err) {
      console.error('Failed to revert all:', err)
    }
  }

  // Batch categorize — calls in chunks of 50 with progress tracking
  const CHUNK_SIZE = 50

  const runBatchCategorize = async () => {
    setBatchRunning(true)
    setBatchResult(null)
    setBatchProgress({ current: 0, total: 0 })
    batchAbortRef.current = false

    const accumulated = {
      processed: 0, auto_staged: 0, predicted: 0, unmatched: 0,
      by_tier: { amount_rule: 0, merchant_map: 0, ai: 0, none: 0 },
    }
    let totalEligible = 0

    try {
      while (!batchAbortRef.current) {
        const res = await fetch(`/api/transactions/batch-categorize?limit=${CHUNK_SIZE}`, { method: 'POST' })
        if (!res.ok) {
          const err = await res.json()
          alert(`Batch categorize failed: ${err.detail || 'Unknown error'}`)
          break
        }
        const data = await res.json()

        // First call sets total from backend's count
        if (totalEligible === 0 && data.total_eligible > 0) {
          totalEligible = data.total_eligible
        }

        // Nothing left to process
        if (data.processed === 0) break

        // Accumulate stats
        accumulated.processed += data.processed
        accumulated.auto_staged += data.auto_staged
        accumulated.predicted += data.predicted
        accumulated.unmatched += data.unmatched
        Object.keys(data.by_tier).forEach(k => {
          accumulated.by_tier[k] = (accumulated.by_tier[k] || 0) + (data.by_tier[k] || 0)
        })

        setBatchProgress({ current: accumulated.processed, total: totalEligible })

        // If we got fewer than the chunk size, we're done
        if (data.processed < CHUNK_SIZE) break

        // Safety: if an entire chunk was all unmatched, no further progress is possible
        if (data.auto_staged === 0 && data.predicted === 0) break
      }

      accumulated.total_eligible = totalEligible
      setBatchResult(accumulated)
      fetchPending()
      fetchStaged()
      onUpdate()
    } catch (err) {
      console.error('Batch categorize error:', err)
      alert('Batch categorize failed — check console')
    } finally {
      setBatchRunning(false)
    }
  }

  const cancelBatch = () => {
    batchAbortRef.current = true
  }

  const clearPredictions = async () => {
    if (!window.confirm('Clear all AI predictions from pending transactions? You can re-run batch categorize after.')) return
    try {
      const res = await fetch('/api/transactions/clear-predictions', { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setBatchResult(null)
        fetchPending()
        fetchStaged()
        onUpdate()
      }
    } catch (err) {
      console.error('Failed to clear predictions:', err)
    }
  }

  const formatDate = (dateStr) => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
  }

  const formatAmount = (amount) => {
    const abs = Math.abs(amount)
    return `$${abs.toFixed(2)}`
  }

  const confidenceBadge = (conf, tier) => {
    if (conf == null && !tier) return null
    const pct = conf != null ? Math.round(conf * 100) : null
    const tierLabel = tier === 'amount_rule' ? 'Rule' : tier === 'merchant_map' ? 'Merchant' : tier === 'ai' ? 'AI' : ''
    const level = conf >= 0.9 ? 'high' : conf >= 0.6 ? 'med' : 'low'
    return (
      <span className={`confidence-badge ${level}`} title={`${tierLabel} — ${pct != null ? pct + '% confidence' : 'no score'}`}>
        {tierLabel}{pct != null ? ` ${pct}%` : ''}
      </span>
    )
  }

  // Filter helper
  const matchesFilter = (t, filter) => {
    if (!filter) return true
    if (filter.startsWith('parent:')) {
      const parentName = filter.slice(7)
      return t.predicted_parent_category_name === parentName || t.predicted_category_name === parentName
    }
    return t.predicted_category_name === filter
  }

  // Build hierarchical predicted categories for filter dropdown (parent → subcategories)
  const predictedCategories = React.useMemo(() => {
    const parentMap = new Map()
    for (const t of pendingTxns) {
      if (t.predicted_category_id && t.predicted_category_name) {
        const parentName = t.predicted_parent_category_name || t.predicted_category_name
        if (!parentMap.has(parentName)) {
          parentMap.set(parentName, { name: parentName, count: 0, children: new Map() })
        }
        const parent = parentMap.get(parentName)
        parent.count++
        if (t.predicted_category_name !== parentName) {
          const childCount = parent.children.get(t.predicted_category_name) || 0
          parent.children.set(t.predicted_category_name, childCount + 1)
        }
      }
    }
    return [...parentMap.values()]
      .sort((a, b) => b.count - a.count)
      .map(p => ({
        ...p,
        children: [...p.children.entries()]
          .map(([name, count]) => ({ name, count }))
          .sort((a, b) => b.count - a.count)
      }))
  }, [pendingTxns])

  const rawTransactions = activeTab === 'review' ? pendingTxns : stagedTxns
  const categoryFiltered = (activeTab === 'review' && filterCategory)
    ? rawTransactions.filter(t => matchesFilter(t, filterCategory))
    : rawTransactions
  const filteredTransactions = descSearch.trim()
    ? categoryFiltered.filter(t => {
        const q = descSearch.toLowerCase()
        return (t.merchant_name && t.merchant_name.toLowerCase().includes(q))
          || (t.description && t.description.toLowerCase().includes(q))
      })
    : categoryFiltered
  const transactions = [...filteredTransactions].sort((a, b) => {
    const cmp = a.date.localeCompare(b.date)
    return sortOrder === 'desc' ? -cmp : cmp
  })
  const confirmableCount = transactions.filter(t => t.predicted_category_id).length

  // Multi-select helpers (with shift-click range support)
  const toggleSelect = (id, e) => {
    const currentIndex = transactions.findIndex(t => t.id === id)

    if (e?.shiftKey && lastClickedIndexRef.current != null) {
      // Shift-click: select range between last click and this click
      const start = Math.min(lastClickedIndexRef.current, currentIndex)
      const end = Math.max(lastClickedIndexRef.current, currentIndex)
      const rangeIds = transactions.slice(start, end + 1).map(t => t.id)
      setSelectedIds(prev => {
        const next = new Set(prev)
        rangeIds.forEach(rid => next.add(rid))
        return next
      })
    } else {
      // Normal click: toggle single item
      setSelectedIds(prev => {
        const next = new Set(prev)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
    }

    lastClickedIndexRef.current = currentIndex
  }
  const allVisibleIds = transactions.map(t => t.id)
  const allSelected = allVisibleIds.length > 0 && allVisibleIds.every(id => selectedIds.has(id))
  const someSelected = allVisibleIds.some(id => selectedIds.has(id))
  const selectedWithPredictions = transactions.filter(t => selectedIds.has(t.id) && t.predicted_category_id).length

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(allVisibleIds))
    }
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
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <h2>Review Queue</h2>
          <p>
            {stats.pending_review} to review, {stats.pending_save || 0} staged
            {selectedYear ? ` (${selectedYear})` : ''}
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {batchRunning ? (
            <div className="batch-progress-wrapper">
              <div className="batch-progress-info">
                <Loader size={14} className="spin" />
                <span>Categorizing {batchProgress.current} / {batchProgress.total || '...'}</span>
                <button className="btn btn-secondary btn-sm" onClick={cancelBatch} style={{ padding: '2px 8px' }}>
                  <X size={12} /> Stop
                </button>
              </div>
              <div className="batch-progress-bar">
                <div
                  className="batch-progress-fill"
                  style={{ width: batchProgress.total > 0 ? `${Math.round((batchProgress.current / batchProgress.total) * 100)}%` : '5%' }}
                />
              </div>
              {batchProgress.total > 0 && (
                <span className="batch-progress-pct">
                  {Math.round((batchProgress.current / batchProgress.total) * 100)}%
                </span>
              )}
            </div>
          ) : (
            <>
              <button
                className="btn btn-secondary btn-sm"
                onClick={runBatchCategorize}
                title="Run AI categorization on uncategorized transactions"
              >
                <Zap size={14} /> Run AI Categorize
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={clearPredictions}
                title="Clear all predictions so you can re-run categorization"
                style={{ color: 'var(--red)' }}
              >
                <Trash2 size={14} /> Clear Predictions
              </button>
            </>
          )}
          <select
            className="category-select"
            value={selectedYear}
            onChange={(e) => { setSelectedYear(e.target.value); setLoading(true) }}
            style={{ minWidth: 140 }}
          >
            <option value="">All Years</option>
            {availableYears.map(y => (
              <option key={y.year} value={y.year}>
                {y.year} ({y.pending} pending)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Batch result banner */}
      {batchResult && (
        <div className="batch-result-banner">
          Categorized {batchResult.processed} transactions:
          {batchResult.auto_staged > 0 && ` ${batchResult.auto_staged} auto-staged,`}
          {batchResult.predicted > 0 && ` ${batchResult.predicted} predicted,`}
          {batchResult.unmatched > 0 && ` ${batchResult.unmatched} unmatched`}
          {' '}(Tier 1: {batchResult.by_tier.amount_rule}, Tier 2: {batchResult.by_tier.merchant_map}, AI: {batchResult.by_tier.ai})
          <button className="btn-icon" onClick={() => setBatchResult(null)}><X size={14} /></button>
        </div>
      )}

      {/* Stats row */}
      <div className="stats-row">
        <div className="stat-card">
          <div className="label">Pending Review</div>
          <div className={`value ${stats.pending_review > 0 ? 'yellow' : 'green'}`}>
            {stats.pending_review}
          </div>
        </div>
        <div className="stat-card">
          <div className="label">Staged</div>
          <div className={`value ${(stats.pending_save || 0) > 0 ? 'blue' : ''}`}>
            {stats.pending_save || 0}
          </div>
        </div>
        <div className="stat-card">
          <div className="label">Confirmed</div>
          <div className="value green">{stats.confirmed}</div>
        </div>
        <div className="stat-card">
          <div className="label">Total</div>
          <div className="value">{stats.total_transactions}</div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="review-tabs">
        <button
          className={`review-tab ${activeTab === 'review' ? 'active' : ''}`}
          onClick={() => setActiveTab('review')}
        >
          To Review ({pendingTxns.length})
        </button>
        <button
          className={`review-tab ${activeTab === 'staged' ? 'active' : ''}`}
          onClick={() => setActiveTab('staged')}
        >
          Staged ({stagedTxns.length})
        </button>
        <button
          className="review-tab-sort"
          onClick={() => setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc')}
          title={sortOrder === 'desc' ? 'Showing newest first — click for oldest first' : 'Showing oldest first — click for newest first'}
        >
          <ArrowUpDown size={13} />
          {sortOrder === 'desc' ? 'Newest' : 'Oldest'}
        </button>
      </div>

      {/* Card content based on active tab */}
      {(transactions.length > 0 || descSearch || filterCategory) ? (
        <div className="card" style={{ borderTopLeftRadius: 0, borderTopRightRadius: 0 }}>
          <div className="card-header">
            {activeTab === 'review' ? (
              <>
                <h3>Transactions to Review</h3>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div className="data-search-box" style={{ minWidth: 160 }}>
                    <Search size={14} />
                    <input
                      type="text"
                      placeholder="Search descriptions..."
                      value={descSearch}
                      onChange={(e) => setDescSearch(e.target.value)}
                    />
                    {descSearch && (
                      <button
                        className="btn-icon"
                        onClick={() => setDescSearch('')}
                        style={{ padding: 0, marginLeft: 4 }}
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                  <CategoryFilterDropdown
                    predictedCategories={predictedCategories}
                    value={filterCategory}
                    onChange={setFilterCategory}
                  />
                  {confirmableCount > 0 && (
                    <button className="btn btn-confirm btn-sm" onClick={stageAllPredicted}>
                      <CheckCircle size={12} style={{ marginRight: 4 }} />
                      Stage {filterCategory || descSearch ? 'Filtered' : 'All'} ({confirmableCount})
                    </button>
                  )}
                </div>
              </>
            ) : (
              <>
                <h3>Staged for Save</h3>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-secondary btn-sm" onClick={revertAll}>
                    <Undo2 size={14} style={{ marginRight: 4 }} />
                    Revert All
                  </button>
                  <button className="btn btn-confirm" onClick={commitAll} disabled={committing}>
                    <Save size={14} style={{ marginRight: 4 }} />
                    {committing ? 'Saving...' : `Save All (${stagedTxns.length})`}
                  </button>
                </div>
              </>
            )}
          </div>

          {/* Bulk action bar — appears when rows are selected */}
          {activeTab === 'review' && selectedIds.size > 0 && (
            <div className="bulk-action-bar">
              <span className="bulk-count">{selectedIds.size} selected</span>
              <div className="bulk-actions">
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setBulkPickerOpen(!bulkPickerOpen)}
                >
                  Categorize ({selectedIds.size})
                </button>
                {selectedWithPredictions > 0 && (
                  <button className="btn btn-confirm btn-sm" onClick={bulkStageSelected}>
                    <CheckCircle size={12} style={{ marginRight: 4 }} />
                    Stage Predicted ({selectedWithPredictions})
                  </button>
                )}
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setSelectedIds(new Set())}
                >
                  Deselect
                </button>
                {bulkPickerOpen && (
                  <div className="bulk-picker-anchor">
                    <CategoryPicker
                      categoryTree={categoryTree}
                      onSelect={bulkAssignCategory}
                      onCancel={() => setBulkPickerOpen(false)}
                      onTreeChanged={fetchCategoryTree}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="review-list">
            {/* Select-all row for review tab */}
            {activeTab === 'review' && transactions.length > 0 && (
              <div className="review-select-all" onClick={toggleSelectAll}>
                <span className="review-checkbox">
                  {allSelected
                    ? <CheckSquare size={15} />
                    : someSelected
                      ? <MinusSquare size={15} />
                      : <Square size={15} />
                  }
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {allSelected ? 'Deselect all' : `Select all ${transactions.length}`}
                </span>
              </div>
            )}
            {transactions.length === 0 && (descSearch || filterCategory) && (
              <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
                No transactions matching {descSearch ? `"${descSearch}"` : 'this filter'}
              </div>
            )}
            {transactions.map(txn => (
              <div
                key={txn.id}
                className={`review-item ${selectedIds.has(txn.id) ? 'selected' : ''}`}
                onClick={activeTab === 'review' ? (e) => toggleSelect(txn.id, e) : undefined}
                style={activeTab === 'review' ? { cursor: 'pointer' } : undefined}
              >
                {activeTab === 'review' && (
                  <span className="review-checkbox">
                    {selectedIds.has(txn.id)
                      ? <CheckSquare size={15} />
                      : <Square size={15} />
                    }
                  </span>
                )}
                <span className="date">{formatDate(txn.date)}</span>
                <span className="description" title={txn.description}>
                  {txn.merchant_name || txn.description}
                </span>
                <span className="account-tag" title={txn.account_name}>{txn.account_name}</span>
                <span className={`amount ${txn.amount > 0 ? 'expense' : 'income'}`}>
                  {txn.amount > 0 ? '-' : '+'}{formatAmount(txn.amount)}
                </span>

                <div className="review-category-area" onClick={e => e.stopPropagation()}>
                  {activeTab === 'review' ? (
                    /* ─── To Review tab ─── */
                    editingId === txn.id ? (
                      <CategoryPicker
                        categoryTree={categoryTree}
                        onSelect={(shortDesc) => stageTransaction(txn.id, shortDesc)}
                        onCancel={() => setEditingId(null)}
                        onTreeChanged={fetchCategoryTree}
                      />
                    ) : txn.predicted_category_id ? (
                      <div className="predicted-group">
                        <span className="predicted-label" title={txn.predicted_category_name}>
                          <ArrowRight size={12} />
                          {txn.predicted_category_name}
                        </span>
                        {confidenceBadge(txn.prediction_confidence, txn.categorization_tier)}
                        <button
                          className="btn btn-confirm btn-sm"
                          onClick={() => stageTransaction(txn.id, txn.predicted_category_short_desc)}
                          title="Stage this category"
                        >
                          <CheckCircle size={12} />
                        </button>
                        <button
                          className="btn btn-secondary btn-sm btn-icon-only"
                          onClick={() => setEditingId(txn.id)}
                          title="Pick a different category"
                        >
                          ✎
                        </button>
                      </div>
                    ) : (
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => setEditingId(txn.id)}
                      >
                        Categorize
                      </button>
                    )
                  ) : (
                    /* ─── Staged tab ─── */
                    <div className="staged-group">
                      <span className="staged-label" title={txn.category_name || txn.predicted_category_name}>
                        {txn.category_name || txn.predicted_category_name}
                      </span>
                      {confidenceBadge(txn.prediction_confidence, txn.categorization_tier)}
                      <button
                        className="btn btn-secondary btn-sm btn-icon-only"
                        onClick={() => kickBack(txn.id)}
                        title="Send back to review"
                      >
                        <Undo2 size={13} />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="card" style={{ borderTopLeftRadius: 0, borderTopRightRadius: 0 }}>
          <div className="empty-state">
            <div className="icon"><CheckCircle size={48} /></div>
            {activeTab === 'review' ? (
              <>
                <h3>All caught up!</h3>
                <p>No transactions to review. {stagedTxns.length > 0 ? `Switch to the Staged tab to review ${stagedTxns.length} staged transactions.` : 'Import a CSV or connect your bank to get started.'}</p>
              </>
            ) : (
              <>
                <h3>Nothing staged yet</h3>
                <p>Review and confirm transactions to stage them here before saving.</p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
