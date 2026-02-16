import React, { useState, useEffect, useRef } from 'react'
import { Calendar, ChevronLeft, ChevronRight, ChevronDown, Search, ArrowUpDown, Plus, X, Filter, CheckSquare, Square, MinusSquare, Trash2 } from 'lucide-react'
import CategoryPicker from '../components/CategoryPicker'

const PAGE_SIZES = [50, 100, 'All']

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatShortDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatCurrency(amount) {
  if (amount == null) return '—'
  const abs = Math.abs(amount)
  return `${amount < 0 ? '+' : ''}$${abs.toFixed(2)}`
}

function bankName(name) {
  if (!name) return ''
  return name
    .replace(/ Card$/i, '')
}

/* ─── Category Filter Dropdown for Data page ─── */
function DataCategoryFilter({ categoryTree, value, onChange }) {
  // value = { type: 'parent'|'child', id, name } or null
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(new Set())
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

  const toggleExpand = (id, e) => {
    e.stopPropagation()
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const q = search.toLowerCase()
  const isSearching = q.length > 0
  const filtered = isSearching
    ? categoryTree.map(pg => ({
        ...pg,
        children: (pg.children || []).filter(ch => ch.display_name.toLowerCase().includes(q)),
        parentMatch: pg.display_name.toLowerCase().includes(q),
      })).filter(pg => pg.parentMatch || pg.children.length > 0)
    : categoryTree

  const handleSelect = (val) => {
    onChange(val)
    setOpen(false)
    setSearch('')
  }

  const label = value ? value.name : 'All Categories'

  return (
    <div className="filter-dropdown" ref={ref}>
      <button
        className={`filter-dropdown-trigger ${value ? 'active' : ''}`}
        onClick={() => setOpen(!open)}
      >
        <Filter size={12} />
        <span>{label}</span>
        {value && (
          <span className="filter-clear" onClick={(e) => { e.stopPropagation(); onChange(null) }}>
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
              onClick={() => handleSelect(null)}
            >
              All Categories
            </div>
            {filtered.map(pg => {
              const children = pg.children || []
              const isExpanded = isSearching || expanded.has(pg.id)
              const hasChildren = children.length > 0
              return (
                <React.Fragment key={pg.id}>
                  <div
                    className={`filter-dropdown-item filter-parent ${value?.type === 'parent' && value?.id === pg.id ? 'selected' : ''}`}
                    onClick={() => handleSelect({ type: 'parent', id: pg.id, name: pg.display_name })}
                  >
                    {hasChildren && (
                      <span className="filter-expand-toggle" onClick={(e) => toggleExpand(pg.id, e)}>
                        {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      </span>
                    )}
                    <span className="filter-parent-name">{pg.display_name}</span>
                  </div>
                  {hasChildren && isExpanded && children.map(ch => (
                    <div
                      key={ch.id}
                      className={`filter-dropdown-item filter-child ${value?.type === 'child' && value?.id === ch.id ? 'selected' : ''}`}
                      onClick={() => handleSelect({ type: 'child', id: ch.id, name: ch.display_name })}
                    >
                      <span className="filter-child-name">{ch.display_name}</span>
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

export default function Data() {
  // Restore persisted filters from sessionStorage
  const saved = sessionStorage.getItem('dataFilters')
  const persisted = saved ? JSON.parse(saved) : {}

  const [accounts, setAccounts] = useState([])
  const [availableYears, setAvailableYears] = useState([])
  const [selectedYear, setSelectedYear] = useState(persisted.year ?? '')
  const [selectedAccountId, setSelectedAccountId] = useState(persisted.accountId ?? '')
  const [selectedSource, setSelectedSource] = useState(persisted.source ?? '')
  const [transactions, setTransactions] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [filteredMin, setFilteredMin] = useState(null)
  const [filteredMax, setFilteredMax] = useState(null)
  const [loading, setLoading] = useState(true)
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(persisted.pageSize ?? 'All')
  const [search, setSearch] = useState(persisted.search ?? '')
  const [searchInput, setSearchInput] = useState(persisted.search ?? '')
  const searchTimerRef = useRef(null)
  const [sortAsc, setSortAsc] = useState(persisted.sortAsc ?? false)

  // Category picker state
  const [categoryTree, setCategoryTree] = useState([])
  const [editingTxnId, setEditingTxnId] = useState(null)
  const [selectedCategory, setSelectedCategory] = useState(persisted.category ?? null) // { type: 'parent'|'child', id, name } or null

  // Persist filters whenever they change
  useEffect(() => {
    sessionStorage.setItem('dataFilters', JSON.stringify({
      year: selectedYear,
      accountId: selectedAccountId,
      source: selectedSource,
      pageSize,
      search,
      sortAsc,
      category: selectedCategory,
    }))
  }, [selectedYear, selectedAccountId, selectedSource, pageSize, search, sortAsc, selectedCategory])

  // Multi-select state
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [bulkPickerOpen, setBulkPickerOpen] = useState(false)
  const lastClickedIndexRef = useRef(null)

  useEffect(() => {
    fetchAccounts()
    fetchYears()
    fetchCategories()
  }, [])

  useEffect(() => {
    fetchTransactions()
  }, [selectedAccountId, selectedYear, offset, search, pageSize, selectedCategory, selectedSource])

  const fetchAccounts = async () => {
    try {
      const res = await fetch('/api/accounts/')
      if (res.ok) setAccounts(await res.json())
    } catch (err) {
      console.error('Failed to fetch accounts:', err)
    }
  }

  const fetchYears = async () => {
    try {
      const res = await fetch('/api/transactions/years')
      if (res.ok) {
        const data = await res.json()
        setAvailableYears(data)
        // Only set default year if no persisted value
        if (!selectedYear && data.length > 0) setSelectedYear(String(data[0].year))
      }
    } catch (err) {
      console.error('Failed to fetch years:', err)
    }
  }

  const fetchCategories = async () => {
    try {
      const res = await fetch('/api/categories/tree')
      if (res.ok) setCategoryTree(await res.json())
    } catch (err) {
      console.error('Failed to fetch categories:', err)
    }
  }

  const fetchTransactions = async () => {
    setLoading(true)
    try {
      const limit = pageSize === 'All' ? 10000 : pageSize
      const params = new URLSearchParams({ limit, offset })
      if (selectedAccountId) params.set('account_id', selectedAccountId)
      if (search) params.set('search', search)
      if (selectedYear) {
        params.set('start_date', `${selectedYear}-01-01`)
        params.set('end_date', `${selectedYear}-12-31`)
      }
      if (selectedCategory) {
        if (selectedCategory.type === 'parent') {
          params.set('parent_category_id', selectedCategory.id)
        } else {
          params.set('category_id', selectedCategory.id)
        }
      }
      if (selectedSource) params.set('source', selectedSource)

      const res = await fetch(`/api/transactions/?${params}`)
      if (res.ok) {
        const data = await res.json()
        setTransactions(data)
        setTotalCount(data.length)

        if (data.length > 0) {
          const dates = data.map(t => t.date).sort()
          setFilteredMin(dates[0])
          setFilteredMax(dates[dates.length - 1])
        } else {
          setFilteredMin(null)
          setFilteredMax(null)
        }
      } else {
        console.error('API error:', res.status)
        setTransactions([])
        setFilteredMin(null)
        setFilteredMax(null)
      }
    } catch (err) {
      console.error('Failed to fetch transactions:', err)
      setTransactions([])
      setFilteredMin(null)
      setFilteredMax(null)
    } finally {
      setLoading(false)
    }
  }

  const handleCategoryChange = async (txnId, shortDesc) => {
    setEditingTxnId(null)
    try {
      const res = await fetch(`/api/transactions/${txnId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category_short_desc: shortDesc }),
      })
      if (res.ok) {
        // Find the display name from the category tree
        let displayName = shortDesc
        for (const parent of categoryTree) {
          for (const child of parent.children || []) {
            if (child.short_desc === shortDesc) {
              displayName = child.display_name
              break
            }
          }
        }
        // Update the transaction in local state so badge refreshes instantly
        setTransactions(prev =>
          prev.map(txn =>
            txn.id === txnId
              ? { ...txn, category_name: displayName, category_short_desc: shortDesc, status: 'confirmed' }
              : txn
          )
        )
      } else {
        const err = await res.json()
        console.error('Failed to assign category:', err.detail)
      }
    } catch (err) {
      console.error('Failed to assign category:', err)
    }
  }

  const handleCategoryFilterChange = (val) => {
    setSelectedCategory(val)
    setOffset(0)
    setSelectedIds(new Set())
  }

  const handleYearChange = (e) => {
    setSelectedYear(e.target.value)
    setSelectedAccountId('')
    setOffset(0)
    setSelectedIds(new Set())
  }

  const handleAccountChange = (e) => {
    setSelectedAccountId(e.target.value)
    setOffset(0)
    setSelectedIds(new Set())
  }

  const handleSearchInput = (val) => {
    setSearchInput(val)
    clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => {
      setSearch(val)
      setOffset(0)
    }, 300)
  }

  const handleSearch = (e) => {
    e.preventDefault()
    clearTimeout(searchTimerRef.current)
    setSearch(searchInput)
    setOffset(0)
  }

  const handleClearSearch = () => {
    clearTimeout(searchTimerRef.current)
    setSearchInput('')
    setSearch('')
    setOffset(0)
  }

  // Multi-select helpers
  const toggleSelect = (id, e) => {
    const currentIndex = sortedTransactions.findIndex(t => t.id === id)
    if (e?.shiftKey && lastClickedIndexRef.current != null) {
      const start = Math.min(lastClickedIndexRef.current, currentIndex)
      const end = Math.max(lastClickedIndexRef.current, currentIndex)
      const rangeIds = sortedTransactions.slice(start, end + 1).map(t => t.id)
      setSelectedIds(prev => {
        const next = new Set(prev)
        rangeIds.forEach(rid => next.add(rid))
        return next
      })
    } else {
      setSelectedIds(prev => {
        const next = new Set(prev)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
    }
    lastClickedIndexRef.current = currentIndex
  }

  const bulkAssignCategory = async (shortDesc) => {
    setBulkPickerOpen(false)
    const ids = [...selectedIds]
    try {
      const res = await fetch('/api/transactions/bulk-review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transaction_ids: ids,
          action: 'change',
          category_short_desc: shortDesc,
        }),
      })
      if (res.ok) {
        let displayName = shortDesc
        for (const parent of categoryTree) {
          for (const child of parent.children || []) {
            if (child.short_desc === shortDesc) {
              displayName = child.display_name
              break
            }
          }
        }
        setTransactions(prev =>
          prev.map(txn =>
            selectedIds.has(txn.id)
              ? { ...txn, category_name: displayName, category_short_desc: shortDesc, status: 'confirmed' }
              : txn
          )
        )
        setSelectedIds(new Set())
      } else {
        const err = await res.json()
        console.error('Bulk assign failed:', err.detail)
      }
    } catch (err) {
      console.error('Bulk assign failed:', err)
    }
  }

  const handleDeleteTransaction = async (txnId) => {
    if (!confirm('Delete this transaction? This cannot be undone.')) return
    try {
      const res = await fetch(`/api/transactions/${txnId}`, { method: 'DELETE' })
      if (res.ok) {
        setTransactions(prev => prev.filter(t => t.id !== txnId))
        setSelectedIds(prev => { const next = new Set(prev); next.delete(txnId); return next })
      } else {
        const err = await res.json()
        console.error('Delete failed:', err.detail)
      }
    } catch (err) { console.error('Delete failed:', err) }
  }

  const handleBulkDelete = async () => {
    const count = selectedIds.size
    if (!confirm(`Delete ${count} transaction${count > 1 ? 's' : ''}? This cannot be undone.`)) return
    try {
      const res = await fetch('/api/transactions/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_ids: [...selectedIds] }),
      })
      if (res.ok) {
        const data = await res.json()
        const deletedSet = new Set(data.transaction_ids)
        setTransactions(prev => prev.filter(t => !deletedSet.has(t.id)))
        setSelectedIds(new Set())
      } else {
        const err = await res.json()
        console.error('Bulk delete failed:', err.detail)
      }
    } catch (err) { console.error('Bulk delete failed:', err) }
  }

  const handlePageSizeChange = (size) => {
    setPageSize(size)
    setOffset(0)
  }

  const toggleSort = () => setSortAsc(!sortAsc)

  const accountsForYear = accounts.filter(acct => {
    if (!selectedYear || !acct.earliest_transaction || !acct.latest_transaction) return false
    const yr = parseInt(selectedYear)
    const earliest = new Date(acct.earliest_transaction + 'T00:00:00').getFullYear()
    const latest = new Date(acct.latest_transaction + 'T00:00:00').getFullYear()
    return yr >= earliest && yr <= latest
  })

  const sortedTransactions = [...transactions].sort((a, b) => {
    return sortAsc
      ? new Date(a.date) - new Date(b.date)
      : new Date(b.date) - new Date(a.date)
  })

  const allVisibleIds = sortedTransactions.map(t => t.id)
  const allSelected = allVisibleIds.length > 0 && allVisibleIds.every(id => selectedIds.has(id))
  const someSelected = allVisibleIds.some(id => selectedIds.has(id))

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(allVisibleIds))
    }
  }

  const yearData = availableYears.find(y => String(y.year) === selectedYear)
  const effectiveLimit = pageSize === 'All' ? 10000 : pageSize

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Transaction Data</h2>
          <p>Browse all stored transactions by year and bank</p>
        </div>

        <select
          className="data-year-select"
          value={selectedYear}
          onChange={handleYearChange}
        >
          <option value="">All Years</option>
          {availableYears.map(y => (
            <option key={y.year} value={y.year}>{y.year}</option>
          ))}
        </select>
      </div>

      {/* Stats row */}
      <div className="stats-row">
        <div className="stat-card">
          <div className="label">Transactions</div>
          <div className="value">
            {totalCount.toLocaleString()}
          </div>
        </div>
        <div className="stat-card">
          <div className="label">Earliest</div>
          <div className="value" style={{ fontSize: 20 }}>{formatShortDate(filteredMin)}</div>
        </div>
        <div className="stat-card">
          <div className="label">Latest</div>
          <div className="value" style={{ fontSize: 20 }}>{formatShortDate(filteredMax)}</div>
        </div>
        <div className="stat-card">
          <div className="label">Accounts</div>
          <div className="value">{new Set(transactions.map(t => t.account_id)).size}</div>
        </div>
      </div>

      {/* Filters & table */}
      <div className="card">
        <div className="card-header" style={{ flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1 }}>
            <select
              className="data-account-select"
              value={selectedAccountId}
              onChange={handleAccountChange}
            >
              <option value="">All Accounts</option>
              {(selectedYear ? accountsForYear : accounts).map(acct => (
                <option key={acct.id} value={acct.id}>
                  {bankName(acct.name)}
                </option>
              ))}
            </select>

            <select
              className="data-account-select"
              value={selectedSource}
              onChange={(e) => { setSelectedSource(e.target.value); setOffset(0) }}
            >
              <option value="">All Sources</option>
              <option value="plaid_sync">Plaid</option>
              <option value="archive_import">Archive</option>
              <option value="csv_import">CSV</option>
            </select>

            <DataCategoryFilter
              categoryTree={categoryTree}
              value={selectedCategory}
              onChange={handleCategoryFilterChange}
            />

            <form onSubmit={handleSearch} style={{ display: 'flex', gap: 8 }}>
              <div className="data-search-box">
                <Search size={14} />
                <input
                  type="text"
                  placeholder="Search descriptions..."
                  value={searchInput}
                  onChange={(e) => handleSearchInput(e.target.value)}
                />
                {searchInput && (
                  <button
                    type="button"
                    className="btn-icon"
                    onClick={handleClearSearch}
                    style={{ padding: 0, marginLeft: 4 }}
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            </form>
          </div>

          {/* Page size selector */}
          <div className="data-page-size">
            Show:
            {PAGE_SIZES.map(size => (
              <button
                key={size}
                className={`btn btn-sm ${pageSize === size ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => handlePageSizeChange(size)}
              >
                {size}
              </button>
            ))}
          </div>
        </div>

        {/* Pagination above table */}
        {pageSize !== 'All' && (
          <div className="data-pagination" style={{ borderBottom: '1px solid var(--border)' }}>
            <button
              className="btn btn-secondary btn-sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - effectiveLimit))}
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <span className="data-page-info">
              Showing {offset + 1}–{offset + sortedTransactions.length}
              {yearData ? ` of ${yearData.total.toLocaleString()}` : ''}
            </span>
            <button
              className="btn btn-secondary btn-sm"
              disabled={transactions.length < effectiveLimit}
              onClick={() => setOffset(offset + effectiveLimit)}
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
        )}

        {/* Bulk action bar */}
        {selectedIds.size > 0 && (
          <div className="bulk-action-bar">
            <span className="bulk-count">{selectedIds.size} selected</span>
            <div className="bulk-actions">
              <button
                className="btn btn-primary btn-sm"
                onClick={() => setBulkPickerOpen(!bulkPickerOpen)}
              >
                Categorize ({selectedIds.size})
              </button>
              <button
                className="btn btn-danger btn-sm"
                onClick={handleBulkDelete}
              >
                <Trash2 size={12} /> Delete ({selectedIds.size})
              </button>
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
                    onTreeChanged={fetchCategories}
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Transaction table */}
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th className="data-th-check" onClick={toggleSelectAll} style={{ cursor: 'pointer', width: 36, textAlign: 'center' }}>
                  {allSelected
                    ? <CheckSquare size={15} />
                    : someSelected
                      ? <MinusSquare size={15} />
                      : <Square size={15} />
                  }
                </th>
                <th className="data-th-date" onClick={toggleSort} style={{ cursor: 'pointer' }}>
                  Date <ArrowUpDown size={12} style={{ opacity: 0.5 }} />
                </th>
                <th className="data-th-desc">Description</th>
                <th className="data-th-account">Account</th>
                <th className="data-th-amount">Amount</th>
                <th className="data-th-category">Category</th>
                <th className="data-th-status">Status</th>
                <th className="data-th-source">Source</th>
                <th className="data-th-actions" style={{ width: 36 }}></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    Loading...
                  </td>
                </tr>
              ) : sortedTransactions.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    {search ? `No transactions matching "${search}"` : 'No transactions found'}
                  </td>
                </tr>
              ) : (
                sortedTransactions.map(txn => (
                  <tr
                    key={txn.id}
                    className={`data-row ${selectedIds.has(txn.id) ? 'selected' : ''}`}
                    onClick={(e) => {
                      // Don't select when clicking category badge or picker
                      if (e.target.closest('.data-cell-category')) return
                      toggleSelect(txn.id, e)
                    }}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="data-cell-check" style={{ textAlign: 'center', width: 36 }} onClick={(e) => e.stopPropagation()}>
                      <span onClick={(e) => toggleSelect(txn.id, e)} style={{ cursor: 'pointer' }}>
                        {selectedIds.has(txn.id) ? <CheckSquare size={15} /> : <Square size={15} />}
                      </span>
                    </td>
                    <td className="data-cell-date">{formatDate(txn.date)}</td>
                    <td className="data-cell-desc" title={txn.merchant_name && txn.merchant_name !== txn.description ? `${txn.merchant_name}` : ''}>
                      {txn.description}
                    </td>
                    <td className="data-cell-account">{bankName(txn.account_name)}</td>
                    <td className={`data-cell-amount ${txn.amount > 0 ? 'expense' : 'income'}`}>
                      {formatCurrency(txn.amount)}
                    </td>
                    <td className="data-cell-category" style={{ position: 'relative' }}>
                      <span
                        className={`data-cat-badge clickable ${!txn.category_name && txn.predicted_category_name ? 'predicted' : ''}`}
                        onClick={() => setEditingTxnId(editingTxnId === txn.id ? null : txn.id)}
                        title="Click to change category"
                      >
                        {txn.category_name
                          ? txn.category_name
                          : txn.predicted_category_name
                            ? `${txn.predicted_category_name}?`
                            : '—'}
                      </span>
                      {editingTxnId === txn.id && (
                        <CategoryPicker
                          categoryTree={categoryTree}
                          onSelect={(shortDesc) => handleCategoryChange(txn.id, shortDesc)}
                          onCancel={() => setEditingTxnId(null)}
                          onTreeChanged={fetchCategories}
                        />
                      )}
                    </td>
                    <td className="data-cell-status">
                      <span className={`data-status-dot ${txn.status}`} />
                      {txn.status === 'auto_confirmed' ? 'Auto' : txn.status === 'confirmed' ? 'Confirmed' : 'Pending'}
                    </td>
                    <td className="data-cell-source">
                      {txn.source === 'plaid_sync' ? 'Plaid' : txn.source === 'archive_import' ? 'Archive' : 'CSV'}
                    </td>
                    <td className="data-cell-actions" onClick={(e) => e.stopPropagation()}>
                      <button
                        className="btn-icon danger"
                        title="Delete transaction"
                        onClick={() => handleDeleteTransaction(txn.id)}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination below table */}
        {pageSize !== 'All' && (
          <div className="data-pagination">
            <button
              className="btn btn-secondary btn-sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - effectiveLimit))}
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <span className="data-page-info">
              Showing {offset + 1}–{offset + sortedTransactions.length}
              {yearData ? ` of ${yearData.total.toLocaleString()}` : ''}
            </span>
            <button
              className="btn btn-secondary btn-sm"
              disabled={transactions.length < effectiveLimit}
              onClick={() => setOffset(offset + effectiveLimit)}
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
