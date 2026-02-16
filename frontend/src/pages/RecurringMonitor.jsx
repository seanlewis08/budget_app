import React, { useState, useEffect, useMemo, useRef } from 'react'
import { ChevronRight, ChevronDown, Filter, Loader } from 'lucide-react'
import CategoryPicker from '../components/CategoryPicker'

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const fmtFull = (n) =>
  `$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const fmtSigned = (n) => {
  const abs = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (n < -0.005) return `+$${abs}`
  return `$${abs}`
}

const formatDate = (dateStr) => {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/* ─── Category Filter Dropdown ─── */
function CategoryFilterDropdown({ recurringParents, enabledCategories, expandedParents, toggleParent, toggleParentCheckbox, toggleChild, selectAll, selectNone }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const totalRecurring = recurringParents.reduce((sum, p) => sum + p.children.length, 0)
  const enabledCount = enabledCategories.size

  return (
    <div className="recurring-filter-dropdown" ref={ref}>
      <button
        className={`recurring-filter-trigger ${open ? 'active' : ''}`}
        onClick={() => setOpen(!open)}
      >
        <Filter size={12} />
        <span>Categories ({enabledCount}/{totalRecurring})</span>
      </button>

      {open && (
        <div className="recurring-filter-panel">
          <div className="recurring-filter-panel-header">
            <button className="recurring-link-btn" onClick={selectAll}>All</button>
            <button className="recurring-link-btn" onClick={selectNone}>None</button>
          </div>

          <div className="recurring-filter-panel-list">
            {recurringParents.map(parent => {
              const childIds = parent.children.map(c => c.id)
              const allChecked = childIds.every(id => enabledCategories.has(id))
              const someChecked = childIds.some(id => enabledCategories.has(id))
              const isExpanded = expandedParents.has(parent.id)

              return (
                <div key={parent.id}>
                  <div className="recurring-filter-parent-row" onClick={() => toggleParent(parent.id)}>
                    {isExpanded
                      ? <ChevronDown size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                      : <ChevronRight size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
                    <input
                      type="checkbox"
                      className="recurring-checkbox"
                      checked={allChecked}
                      ref={el => { if (el) el.indeterminate = someChecked && !allChecked }}
                      onChange={(e) => { e.stopPropagation(); toggleParentCheckbox(parent) }}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <span>{parent.display_name}</span>
                  </div>
                  {isExpanded && parent.children.map(child => (
                    <label key={child.id} className="recurring-filter-child-row">
                      <input
                        type="checkbox"
                        className="recurring-checkbox"
                        checked={enabledCategories.has(child.id)}
                        onChange={() => toggleChild(child.id)}
                      />
                      <span>{child.display_name}</span>
                    </label>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

/* ─── Recurring Monitor Page ─── */
export default function RecurringMonitor() {
  const saved = sessionStorage.getItem('recurringMonitorFilters')
  const persisted = saved ? JSON.parse(saved) : {}

  const [selectedYear, setSelectedYear] = useState(persisted.year ?? new Date().getFullYear())
  const [availableYears, setAvailableYears] = useState([])
  const [categoryTree, setCategoryTree] = useState([])
  const [enabledCategories, setEnabledCategories] = useState(new Set(persisted.enabled ?? []))
  const [expandedParents, setExpandedParents] = useState(new Set())
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  // Drill-down state
  const [selectedCell, setSelectedCell] = useState(null) // { categoryId, monthIdx, displayName }
  const [drillTxns, setDrillTxns] = useState([])
  const [drillLoading, setDrillLoading] = useState(false)
  const [editingTxnId, setEditingTxnId] = useState(null)

  // Fetch available years on mount
  useEffect(() => {
    const fetchYears = async () => {
      try {
        const res = await fetch('/api/transactions/years')
        if (res.ok) setAvailableYears(await res.json())
      } catch (err) { console.error('Failed to fetch years:', err) }
    }
    fetchYears()
  }, [])

  // Fetch category tree on mount and initialize enabled categories
  useEffect(() => {
    const fetchTree = async () => {
      try {
        const res = await fetch('/api/categories/tree')
        if (res.ok) {
          const tree = await res.json()
          setCategoryTree(tree)

          if (!persisted.enabled || persisted.enabled.length === 0) {
            const allRecurring = new Set()
            tree.forEach(parent => {
              (parent.children || []).forEach(child => {
                if (child.is_recurring) allRecurring.add(child.id)
              })
            })
            setEnabledCategories(allRecurring)
          }
        }
      } catch (err) { console.error('Failed to fetch category tree:', err) }
    }
    fetchTree()
  }, [])

  // Fetch recurring data when year changes
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const res = await fetch(`/api/transactions/recurring-monitor?year=${selectedYear}`)
        if (res.ok) setData(await res.json())
      } catch (err) { console.error('Failed to fetch recurring data:', err) }
      finally { setLoading(false) }
    }
    fetchData()
    // Clear drill-down on year change
    setSelectedCell(null)
    setDrillTxns([])
  }, [selectedYear])

  // Persist filters
  useEffect(() => {
    sessionStorage.setItem('recurringMonitorFilters', JSON.stringify({
      year: selectedYear,
      enabled: Array.from(enabledCategories),
    }))
  }, [selectedYear, enabledCategories])

  // Filter recurring parents from category tree
  const recurringParents = useMemo(() => {
    return categoryTree
      .map(parent => {
        const recurringChildren = (parent.children || []).filter(c => c.is_recurring)
        return recurringChildren.length > 0 ? { ...parent, children: recurringChildren } : null
      })
      .filter(Boolean)
  }, [categoryTree])

  // Filter visible rows based on enabled categories
  const visibleRows = useMemo(() => {
    if (!data) return []
    return data.rows.filter(row => enabledCategories.has(row.category_id))
  }, [data, enabledCategories])

  // Group visible rows by parent
  const groupedRows = useMemo(() => {
    const groups = []
    const groupMap = {}
    visibleRows.forEach(row => {
      const key = row.parent_short_desc
      if (!groupMap[key]) {
        groupMap[key] = {
          parent_name: row.parent_name,
          parent_color: row.parent_color,
          parent_short_desc: key,
          rows: [],
        }
        groups.push(groupMap[key])
      }
      groupMap[key].rows.push(row)
    })
    return groups
  }, [visibleRows])

  // Compute visible totals per month — split into inflows/outflows
  const { outflowTotals, inflowTotals, netTotals } = useMemo(() => {
    const outflows = new Array(12).fill(0)
    const inflows = new Array(12).fill(0)
    visibleRows.forEach(row => {
      row.monthly.forEach((val, i) => {
        if (val !== null) {
          if (val > 0) outflows[i] += val
          else inflows[i] += Math.abs(val)
        }
      })
    })
    return {
      outflowTotals: outflows.map(t => Math.round(t * 100) / 100),
      inflowTotals: inflows.map(t => Math.round(t * 100) / 100),
      netTotals: outflows.map((o, i) => Math.round((o - inflows[i]) * 100) / 100),
    }
  }, [visibleRows])

  const activeMonths = data ? new Set(data.active_months) : new Set()

  // ── Filter handlers ──

  const toggleParent = (parentId) => {
    setExpandedParents(prev => {
      const next = new Set(prev)
      if (next.has(parentId)) next.delete(parentId)
      else next.add(parentId)
      return next
    })
  }

  const toggleParentCheckbox = (parent) => {
    const childIds = parent.children.map(c => c.id)
    const allChecked = childIds.every(id => enabledCategories.has(id))
    setEnabledCategories(prev => {
      const next = new Set(prev)
      childIds.forEach(id => allChecked ? next.delete(id) : next.add(id))
      return next
    })
  }

  const toggleChild = (childId) => {
    setEnabledCategories(prev => {
      const next = new Set(prev)
      if (next.has(childId)) next.delete(childId)
      else next.add(childId)
      return next
    })
  }

  const selectAll = () => {
    const all = new Set()
    recurringParents.forEach(p => p.children.forEach(c => all.add(c.id)))
    setEnabledCategories(all)
  }

  const selectNone = () => setEnabledCategories(new Set())

  // ── Recategorize a transaction ──
  const fetchCategoryTree = async () => {
    try {
      const res = await fetch('/api/categories/tree')
      if (res.ok) setCategoryTree(await res.json())
    } catch (err) { console.error('Failed to refresh category tree:', err) }
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
        const updated = await res.json()
        // Update transaction in-place in drill-down
        setDrillTxns(prev => prev.map(t =>
          t.id === txnId ? { ...t, category_name: updated.category_name, category_id: updated.category_id } : t
        ))
        // Refresh the recurring monitor data silently
        try {
          const dataRes = await fetch(`/api/transactions/recurring-monitor?year=${selectedYear}`)
          if (dataRes.ok) setData(await dataRes.json())
        } catch (_) {}
      }
    } catch (err) {
      console.error('Failed to recategorize:', err)
    }
  }

  // ── Cell click / drill-down ──
  const handleCellClick = async (categoryId, monthIdx, displayName) => {
    const isActive = activeMonths.has(monthIdx + 1)
    if (!isActive) return // can't drill into inactive months

    // Toggle off if clicking same cell
    if (selectedCell && selectedCell.categoryId === categoryId && selectedCell.monthIdx === monthIdx) {
      setSelectedCell(null)
      setDrillTxns([])
      return
    }

    setSelectedCell({ categoryId, monthIdx, displayName })
    setDrillTxns([])
    setDrillLoading(true)

    const month = monthIdx + 1
    const startDate = `${selectedYear}-${String(month).padStart(2, '0')}-01`
    // End of month: use first day of next month minus 1, or just set to last possible day
    const lastDay = new Date(selectedYear, month, 0).getDate()
    const endDate = `${selectedYear}-${String(month).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`

    try {
      const res = await fetch(
        `/api/transactions/?category_id=${categoryId}&start_date=${startDate}&end_date=${endDate}&limit=500`
      )
      if (res.ok) {
        let txns = await res.json()
        txns.sort((a, b) => a.date.localeCompare(b.date))
        setDrillTxns(txns)
      }
    } catch (err) {
      console.error('Failed to fetch drill-down transactions:', err)
    } finally {
      setDrillLoading(false)
    }
  }

  // ── Change indicator ──
  const getIndicator = (monthly, monthIdx) => {
    for (let prev = monthIdx - 1; prev >= 0; prev--) {
      if (!activeMonths.has(prev + 1)) continue
      const prevVal = monthly[prev]
      const curVal = monthly[monthIdx]
      if (prevVal === null || curVal === null) return null
      const diff = curVal - prevVal
      if (Math.abs(diff) < 0.01) return null
      return diff > 0
        ? <span className="recurring-indicator up" title={`+${fmtFull(diff)}`}>↑</span>
        : <span className="recurring-indicator down" title={`−${fmtFull(Math.abs(diff))}`}>↓</span>
    }
    return null
  }

  // ── Render cell ──
  const renderCell = (row, monthIdx) => {
    const isActive = activeMonths.has(monthIdx + 1)
    const val = row.monthly[monthIdx]
    const isSelected = selectedCell && selectedCell.categoryId === row.category_id && selectedCell.monthIdx === monthIdx

    if (!isActive) return <td key={monthIdx} className="recurring-cell"><span className="recurring-missing">–</span></td>

    const clickable = val !== null
    return (
      <td
        key={monthIdx}
        className={`recurring-cell ${clickable ? 'recurring-cell-clickable' : ''} ${isSelected ? 'recurring-cell-selected' : ''}`}
        onClick={clickable ? () => handleCellClick(row.category_id, monthIdx, row.display_name) : undefined}
      >
        {val === null
          ? <span className="recurring-zero">$0.00</span>
          : <>{fmtFull(val)}{getIndicator(row.monthly, monthIdx)}</>
        }
      </td>
    )
  }

  const rowTotal = (monthly) => {
    let sum = 0
    monthly.forEach((val) => { if (val !== null) sum += val })
    return sum
  }

  return (
    <div className="page-content">
      {/* ── Top Bar: title left, filters + year right ── */}
      <div className="recurring-top-bar">
        <h2>Recurring Monitor</h2>
        <div className="recurring-top-controls">
          <CategoryFilterDropdown
            recurringParents={recurringParents}
            enabledCategories={enabledCategories}
            expandedParents={expandedParents}
            toggleParent={toggleParent}
            toggleParentCheckbox={toggleParentCheckbox}
            toggleChild={toggleChild}
            selectAll={selectAll}
            selectNone={selectNone}
          />
          <select
            className="category-select"
            value={selectedYear}
            onChange={(e) => setSelectedYear(parseInt(e.target.value))}
            style={{ minWidth: 100 }}
          >
            {availableYears.length > 0 ? (
              availableYears.map(y => (
                <option key={y.year} value={y.year}>{y.year}</option>
              ))
            ) : (
              <option value={selectedYear}>{selectedYear}</option>
            )}
          </select>
        </div>
      </div>

      {/* ── Grid Table ── */}
      <div className="recurring-grid-container">
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading…
          </div>
        ) : visibleRows.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            No recurring categories selected
          </div>
        ) : (
          <table className="recurring-table">
            <thead>
              <tr>
                <th className="recurring-name-col">Category</th>
                {MONTH_LABELS.map((m, i) => (
                  <th key={m} className={`recurring-cell ${!activeMonths.has(i + 1) ? 'recurring-inactive-header' : ''}`}>
                    {m}
                  </th>
                ))}
                <th className="recurring-cell">Total</th>
              </tr>
            </thead>
            <tbody>
              {groupedRows.map(group => (
                <React.Fragment key={group.parent_short_desc}>
                  <tr className="recurring-group-header">
                    <td colSpan={14}>
                      {group.parent_color && (
                        <span className="recurring-color-dot" style={{ background: group.parent_color }} />
                      )}
                      {group.parent_name}
                    </td>
                  </tr>

                  {group.rows.map(row => (
                    <tr key={row.category_id}>
                      <td className="recurring-name-col recurring-child-name">{row.display_name}</td>
                      {row.monthly.map((_, i) => renderCell(row, i))}
                      <td className="recurring-cell recurring-row-total">{fmtFull(rowTotal(row.monthly))}</td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}
            </tbody>
            <tfoot>
              <tr className="recurring-total-row recurring-outflow-row">
                <td className="recurring-name-col" style={{ fontWeight: 600 }}>Outflows</td>
                {outflowTotals.map((t, i) => (
                  <td key={i} className="recurring-cell expense">
                    {activeMonths.has(i + 1) ? fmtFull(t) : <span className="recurring-missing">–</span>}
                  </td>
                ))}
                <td className="recurring-cell expense" style={{ fontWeight: 600 }}>
                  {fmtFull(outflowTotals.reduce((a, b) => a + b, 0))}
                </td>
              </tr>
              <tr className="recurring-total-row recurring-inflow-row">
                <td className="recurring-name-col" style={{ fontWeight: 600 }}>Inflows</td>
                {inflowTotals.map((t, i) => (
                  <td key={i} className="recurring-cell income">
                    {activeMonths.has(i + 1) ? fmtFull(t) : <span className="recurring-missing">–</span>}
                  </td>
                ))}
                <td className="recurring-cell income" style={{ fontWeight: 600 }}>
                  {fmtFull(inflowTotals.reduce((a, b) => a + b, 0))}
                </td>
              </tr>
              <tr className="recurring-total-row recurring-net-row">
                <td className="recurring-name-col" style={{ fontWeight: 600 }}>Net</td>
                {netTotals.map((t, i) => (
                  <td key={i} className={`recurring-cell ${t < -0.005 ? 'income' : t > 0.005 ? 'expense' : ''}`}>
                    {activeMonths.has(i + 1) ? fmtSigned(t) : <span className="recurring-missing">–</span>}
                  </td>
                ))}
                {(() => {
                  const grandNet = netTotals.reduce((a, b) => a + b, 0)
                  return (
                    <td className={`recurring-cell ${grandNet < -0.005 ? 'income' : grandNet > 0.005 ? 'expense' : ''}`} style={{ fontWeight: 600 }}>
                      {fmtSigned(grandNet)}
                    </td>
                  )
                })()}
              </tr>
            </tfoot>
          </table>
        )}
      </div>

      {/* ── Drill-Down Transaction Table ── */}
      {selectedCell && (
        <div className="recurring-drill-down">
          <div className="recurring-drill-header">
            <span>
              <strong>{selectedCell.displayName}</strong>
              {' '}&mdash;{' '}
              {MONTH_LABELS[selectedCell.monthIdx]} {selectedYear}
            </span>
            <button
              className="recurring-link-btn"
              onClick={() => { setSelectedCell(null); setDrillTxns([]) }}
              style={{ fontSize: 12 }}
            >
              Close
            </button>
          </div>

          {drillLoading ? (
            <div className="recurring-drill-loading">
              <Loader size={14} className="spin" /> Loading transactions…
            </div>
          ) : drillTxns.length === 0 ? (
            <div className="recurring-drill-empty">No transactions found</div>
          ) : (
            <table className="recurring-drill-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Description</th>
                  <th>Account</th>
                  <th>Category</th>
                  <th style={{ textAlign: 'right' }}>Amount</th>
                </tr>
              </thead>
              <tbody>
                {drillTxns.map(txn => (
                  <tr key={txn.id}>
                    <td className="recurring-drill-date">{formatDate(txn.date)}</td>
                    <td className="recurring-drill-desc">{txn.description}</td>
                    <td className="recurring-drill-acct">{txn.account_name || '—'}</td>
                    <td className="recurring-drill-cat" onClick={(e) => e.stopPropagation()}>
                      <span
                        className="cf-cat-badge"
                        onClick={() => setEditingTxnId(editingTxnId === txn.id ? null : txn.id)}
                        title="Click to change category"
                      >
                        {txn.category_name || '—'}
                      </span>
                      {editingTxnId === txn.id && (
                        <CategoryPicker
                          categoryTree={categoryTree}
                          onSelect={(shortDesc) => handleRecategorize(txn.id, shortDesc)}
                          onCancel={() => setEditingTxnId(null)}
                          onTreeChanged={fetchCategoryTree}
                        />
                      )}
                    </td>
                    <td className={`recurring-drill-amt ${txn.amount < 0 ? 'income' : 'expense'}`}>
                      {txn.amount < 0 ? '−' : ''}{fmtFull(txn.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
