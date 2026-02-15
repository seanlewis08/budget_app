import React, { useState, useEffect, useMemo } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { ChevronRight, ChevronDown, Loader } from 'lucide-react'
import CategoryPicker from '../components/CategoryPicker'

/* ─── Tiny SVG Sparkline ─── */
function Sparkline({ data, width = 80, height = 20, color = 'var(--text-muted)' }) {
  if (!data || data.length < 2) return null
  const absData = data.map(v => Math.abs(v))
  const max = Math.max(...absData, 0.01)
  const points = absData.map((v, i) => {
    const x = (i / (absData.length - 1)) * width
    const y = height - (v / max) * (height - 2) - 1
    return `${x},${y}`
  }).join(' ')

  return (
    <svg className="cf-sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/* ─── Cash Flow Page ─── */
export default function CashFlow() {
  const savedCF = sessionStorage.getItem('cashFlowFilters')
  const persistedCF = savedCF ? JSON.parse(savedCF) : {}

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedYear, setSelectedYear] = useState(persistedCF.year ?? new Date().getFullYear())
  const [expandedCats, setExpandedCats] = useState(new Set())
  const [availableYears, setAvailableYears] = useState([])
  const [showExcluded, setShowExcluded] = useState(false)

  // Transaction drill-down state (for category sections)
  const [expandedSubCat, setExpandedSubCat] = useState(null)
  const [expandedTxns, setExpandedTxns] = useState([])
  const [subCatDirection, setSubCatDirection] = useState(null) // 'income' or 'expense'
  const [loadingTxns, setLoadingTxns] = useState(false)
  const [editingTxnId, setEditingTxnId] = useState(null)
  const [categoryTree, setCategoryTree] = useState([])

  // Transaction drill-down state (for biweekly period rows)
  const [expandedPeriod, setExpandedPeriod] = useState(null)
  const [periodTxns, setPeriodTxns] = useState([])
  const [loadingPeriod, setLoadingPeriod] = useState(false)
  const [editingPeriodTxnId, setEditingPeriodTxnId] = useState(null)

  useEffect(() => {
    fetchYears()
    fetchCategoryTree()
  }, [])

  useEffect(() => {
    fetchCashFlow()
    sessionStorage.setItem('cashFlowFilters', JSON.stringify({ year: selectedYear }))
    // Reset drill-down state on year change
    setExpandedCats(new Set())
    setExpandedSubCat(null)
    setExpandedTxns([])
    setEditingTxnId(null)
    setExpandedPeriod(null)
    setPeriodTxns([])
    setEditingPeriodTxnId(null)
  }, [selectedYear])

  const fetchYears = async () => {
    try {
      const res = await fetch('/api/transactions/years')
      if (res.ok) setAvailableYears(await res.json())
    } catch (err) {
      console.error('Failed to fetch years:', err)
    }
  }

  const fetchCashFlow = async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/transactions/cash-flow?year=${selectedYear}`)
      if (res.ok) setData(await res.json())
    } catch (err) {
      console.error('Failed to fetch cash flow:', err)
    } finally {
      setLoading(false)
    }
  }

  // Silently refresh cash flow data without setting loading=true (avoids blink)
  const refreshCashFlow = async () => {
    try {
      const res = await fetch(`/api/transactions/cash-flow?year=${selectedYear}`)
      if (res.ok) setData(await res.json())
    } catch (err) {
      console.error('Failed to refresh cash flow:', err)
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

  const toggleCat = (id) => {
    setExpandedCats(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
        setExpandedSubCat(null)
        setExpandedTxns([])
        setEditingTxnId(null)
      } else {
        next.add(id)
      }
      return next
    })
  }

  // Toggle subcategory expand → fetch transactions for that category for the whole year
  // direction: 'income' | 'expense' — filters to only show relevant transactions
  const toggleSubCat = async (childId, direction) => {
    if (expandedSubCat === childId) {
      setExpandedSubCat(null)
      setExpandedTxns([])
      setEditingTxnId(null)
      setSubCatDirection(null)
      return
    }

    setExpandedSubCat(childId)
    setExpandedTxns([])
    setEditingTxnId(null)
    setSubCatDirection(direction)
    setLoadingTxns(true)

    try {
      const res = await fetch(
        `/api/transactions/?category_id=${childId}&start_date=${selectedYear}-01-01&end_date=${selectedYear}-12-31&limit=500`
      )
      if (res.ok) {
        let txns = await res.json()
        if (direction === 'income') {
          txns = txns.filter(t => t.amount < 0)
        } else if (direction === 'expense') {
          txns = txns.filter(t => t.amount > 0)
        }
        txns.sort((a, b) => b.date.localeCompare(a.date))
        setExpandedTxns(txns)
      }
    } catch (err) {
      console.error('Failed to fetch category transactions:', err)
    } finally {
      setLoadingTxns(false)
    }
  }

  // Toggle biweekly period expand → fetch transactions in that date range
  const togglePeriod = async (weekStart, weekEnd) => {
    if (expandedPeriod === weekStart) {
      setExpandedPeriod(null)
      setPeriodTxns([])
      setEditingPeriodTxnId(null)
      return
    }

    setExpandedPeriod(weekStart)
    setPeriodTxns([])
    setEditingPeriodTxnId(null)
    setLoadingPeriod(true)

    const yearStart = `${selectedYear}-01-01`
    const yearEnd = `${selectedYear}-12-31`
    const clampedStart = weekStart < yearStart ? yearStart : weekStart
    const clampedEnd = weekEnd > yearEnd ? yearEnd : weekEnd

    try {
      const res = await fetch(
        `/api/transactions/?start_date=${clampedStart}&end_date=${clampedEnd}&exclude_transfers=true&limit=500`
      )
      if (res.ok) {
        let txns = await res.json()
        txns = txns.filter(t => t.status === 'confirmed' || t.status === 'auto_confirmed')
        txns.sort((a, b) => b.date.localeCompare(a.date))
        setPeriodTxns(txns)
      }
    } catch (err) {
      console.error('Failed to fetch period transactions:', err)
    } finally {
      setLoadingPeriod(false)
    }
  }

  const handleRecategorize = async (txnId, shortDesc, source) => {
    if (source === 'cat') setEditingTxnId(null)
    else setEditingPeriodTxnId(null)

    try {
      const res = await fetch(`/api/transactions/${txnId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category_short_desc: shortDesc }),
      })
      if (res.ok) {
        if (source === 'cat') {
          setExpandedTxns(prev => prev.filter(t => t.id !== txnId))
        } else {
          // Update the transaction's category in-place instead of removing it
          const updated = await res.json()
          setPeriodTxns(prev => prev.map(t =>
            t.id === txnId ? { ...t, category_name: updated.category_name, category_id: updated.category_id } : t
          ))
        }
        // Silently refresh totals without full reload blink
        refreshCashFlow()
      }
    } catch (err) {
      console.error('Failed to recategorize:', err)
    }
  }

  const fmt = (n) => {
    const abs = Math.abs(n)
    if (abs >= 1000) return `$${(abs / 1000).toFixed(1)}k`
    return `$${abs.toFixed(0)}`
  }

  const fmtFull = (n) => `$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  const fmtSigned = (n) => {
    const prefix = n >= 0 ? '+' : '−'
    return `${prefix}${fmtFull(n)}`
  }

  const formatPeriodLabel = (dateStr) => {
    const d = new Date(dateStr + 'T00:00:00')
    const end = new Date(d.getTime() + 13 * 24 * 60 * 60 * 1000)
    const startStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    const endStr = end.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    return `${startStr} – ${endStr}`
  }

  const formatDate = (dateStr) => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  const monthTick = (dateStr) => {
    const d = new Date(dateStr + 'T00:00:00')
    const day = d.getDate()
    if (day <= 14) return d.toLocaleDateString('en-US', { month: 'short' })
    return ''
  }

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h2>Cash Flow</h2>
          <p>Loading...</p>
        </div>
      </div>
    )
  }

  if (!data || data.weeks.length === 0) {
    return (
      <div>
        <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2>Cash Flow</h2>
            <p>Weekly cash flow analysis</p>
          </div>
          <YearPicker years={availableYears} value={selectedYear} onChange={setSelectedYear} />
        </div>
        <div className="card">
          <div className="empty-state">
            <h3>No confirmed transactions</h3>
            <p>Confirm transactions in the Review Queue to see cash flow data.</p>
          </div>
        </div>
      </div>
    )
  }

  const { summary, weeks, categories, excluded_categories = [] } = data
  const expenseCategories = categories.filter(c => c.expense_total > 0)
    .sort((a, b) => b.expense_total - a.expense_total)
  const incomeCategories = categories.filter(c => c.income_total > 0)
    .sort((a, b) => b.income_total - a.income_total)
  const excludedTotal = excluded_categories.reduce((s, c) => s + c.total, 0)

  return (
    <div>
      {/* ─── Header ─── */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Cash Flow</h2>
          <div className="cf-summary">
            <span className="cf-positive">{fmtFull(summary.total_income)} in</span>
            <span className="cf-sep">·</span>
            <span className="cf-negative">{fmtFull(summary.total_expenses)} out</span>
            <span className="cf-sep">·</span>
            <span className={summary.net >= 0 ? 'cf-positive' : 'cf-negative'}>
              {fmtSigned(summary.net)} net
            </span>
          </div>
        </div>
        <YearPicker years={availableYears} value={selectedYear} onChange={setSelectedYear} />
      </div>

      {/* ─── Weekly Net Cash Flow Chart ─── */}
      <div className="card cf-chart-card">
        <div className="cf-chart-label">Biweekly Net Cash Flow</div>
        <div className="cf-chart">
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={weeks} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <defs>
                <linearGradient id="cfGreen" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--green)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="var(--green)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="week_start"
                tickFormatter={monthTick}
                stroke="var(--text-muted)"
                fontSize={11}
                axisLine={false}
                tickLine={false}
                interval={0}
                tick={({ x, y, payload }) => {
                  const label = monthTick(payload.value)
                  if (!label) return null
                  return <text x={x} y={y + 12} textAnchor="middle" fill="var(--text-muted)" fontSize={11}>{label}</text>
                }}
              />
              <YAxis
                stroke="var(--text-muted)"
                fontSize={10}
                axisLine={false}
                tickLine={false}
                tickFormatter={fmt}
                width={45}
              />
              <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1} />
              <Tooltip
                contentStyle={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelFormatter={formatPeriodLabel}
                formatter={(value, name) => {
                  const label = name === 'net' ? 'Net' : name === 'cumulative' ? 'Cumulative' : name
                  return [fmtSigned(value), label]
                }}
              />
              <Area
                type="monotone"
                dataKey="net"
                stroke="var(--green)"
                strokeWidth={1.5}
                fill="url(#cfGreen)"
                dot={false}
                activeDot={{ r: 3, stroke: 'var(--green)', fill: 'var(--bg-card)' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ─── Category Drivers ─── */}
      <div className="card" style={{ padding: 0 }}>
        <div className="cf-section-header">
          Expense Drivers
          <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 11, marginLeft: 8 }}>
            Click subcategories for transaction details
          </span>
        </div>
        <table className="cf-table">
          <thead>
            <tr>
              <th className="cf-th-name">Category</th>
              <th className="cf-th-num">Total</th>
              <th className="cf-th-num">Avg / 2 Wk</th>
              <th className="cf-th-trend">Trend</th>
            </tr>
          </thead>
          <tbody>
            {expenseCategories.map(cat => (
              <React.Fragment key={cat.id}>
                <tr className="cf-expandable" onClick={() => cat.children.length > 0 && toggleCat(cat.id)}>
                  <td className="cf-td-name">
                    {cat.children.length > 0 ? (
                      expandedCats.has(cat.id)
                        ? <ChevronDown size={14} className="cf-chevron" />
                        : <ChevronRight size={14} className="cf-chevron" />
                    ) : <span className="cf-chevron-spacer" />}
                    {cat.color && <span className="cf-dot" style={{ background: cat.color }} />}
                    {cat.name}
                  </td>
                  <td className="cf-td-num cf-negative">{fmtFull(cat.expense_total)}</td>
                  <td className="cf-td-num">{fmt(cat.expense_total / (weeks.length || 1))}</td>
                  <td className="cf-td-trend">
                    <Sparkline data={cat.weekly_totals.map(v => Math.max(v, 0))} color="var(--red)" />
                  </td>
                </tr>
                {expandedCats.has(cat.id) && cat.children.filter(ch => ch.expense_total > 0).map(child => (
                  <React.Fragment key={child.id}>
                    <tr
                      className="cf-child-row cf-expandable"
                      onClick={() => toggleSubCat(child.id, 'expense')}
                    >
                      <td className="cf-td-name cf-indent">
                        {expandedSubCat === child.id
                          ? <ChevronDown size={12} className="cf-chevron" />
                          : <ChevronRight size={12} className="cf-chevron" />
                        }
                        {child.name}
                      </td>
                      <td className="cf-td-num">{fmtFull(child.expense_total)}</td>
                      <td className="cf-td-num">{fmt(child.expense_total / (weeks.length || 1))}</td>
                      <td className="cf-td-trend">
                        <Sparkline data={child.weekly_totals.map(v => Math.max(v, 0))} color="var(--text-muted)" />
                      </td>
                    </tr>
                    {expandedSubCat === child.id && (
                      <CfTransactionRows
                        loading={loadingTxns}
                        transactions={expandedTxns}
                        editingTxnId={editingTxnId}
                        setEditingTxnId={setEditingTxnId}
                        categoryTree={categoryTree}
                        onRecategorize={(txnId, shortDesc) => handleRecategorize(txnId, shortDesc, 'cat')}
                        fetchCategoryTree={fetchCategoryTree}
                        formatDate={formatDate}
                      />
                    )}
                  </React.Fragment>
                ))}
              </React.Fragment>
            ))}
          </tbody>
          <tfoot>
            <tr className="cf-total-row">
              <td className="cf-td-name" style={{ fontWeight: 600 }}>Total Expenses</td>
              <td className="cf-td-num cf-negative" style={{ fontWeight: 600 }}>
                {fmtFull(expenseCategories.reduce((s, c) => s + c.expense_total, 0))}
              </td>
              <td className="cf-td-num" style={{ fontWeight: 600 }}>
                {fmt(expenseCategories.reduce((s, c) => s + c.expense_total, 0) / (weeks.length || 1))}
              </td>
              <td className="cf-td-trend" />
            </tr>
          </tfoot>
        </table>

        {incomeCategories.length > 0 && (
          <>
            <div className="cf-section-header" style={{ borderTop: '1px solid var(--border)' }}>Income Sources</div>
            <table className="cf-table">
              <thead>
                <tr>
                  <th className="cf-th-name">Category</th>
                  <th className="cf-th-num">Total</th>
                  <th className="cf-th-num">Avg / 2 Wk</th>
                  <th className="cf-th-trend">Trend</th>
                </tr>
              </thead>
              <tbody>
                {incomeCategories.map(cat => (
                  <React.Fragment key={cat.id}>
                    <tr className="cf-expandable" onClick={() => cat.children.length > 0 && toggleCat(cat.id)}>
                      <td className="cf-td-name">
                        {cat.children.length > 0 ? (
                          expandedCats.has(cat.id)
                            ? <ChevronDown size={14} className="cf-chevron" />
                            : <ChevronRight size={14} className="cf-chevron" />
                        ) : <span className="cf-chevron-spacer" />}
                        {cat.color && <span className="cf-dot" style={{ background: cat.color }} />}
                        {cat.name}
                      </td>
                      <td className="cf-td-num cf-positive">{fmtFull(cat.income_total)}</td>
                      <td className="cf-td-num">{fmt(cat.income_total / (weeks.length || 1))}</td>
                      <td className="cf-td-trend">
                        <Sparkline data={cat.weekly_totals.map(v => Math.abs(Math.min(v, 0)))} color="var(--green)" />
                      </td>
                    </tr>
                    {expandedCats.has(cat.id) && cat.children.filter(ch => ch.income_total > 0).map(child => (
                      <React.Fragment key={child.id}>
                        <tr
                          className="cf-child-row cf-expandable"
                          onClick={() => toggleSubCat(child.id, 'income')}
                        >
                          <td className="cf-td-name cf-indent">
                            {expandedSubCat === child.id
                              ? <ChevronDown size={12} className="cf-chevron" />
                              : <ChevronRight size={12} className="cf-chevron" />
                            }
                            {child.name}
                          </td>
                          <td className="cf-td-num">{fmtFull(child.income_total)}</td>
                          <td className="cf-td-num">{fmt(child.income_total / (weeks.length || 1))}</td>
                          <td className="cf-td-trend">
                            <Sparkline data={child.weekly_totals.map(v => Math.abs(Math.min(v, 0)))} color="var(--text-muted)" />
                          </td>
                        </tr>
                        {expandedSubCat === child.id && (
                          <CfTransactionRows
                            loading={loadingTxns}
                            transactions={expandedTxns}
                            editingTxnId={editingTxnId}
                            setEditingTxnId={setEditingTxnId}
                            categoryTree={categoryTree}
                            onRecategorize={(txnId, shortDesc) => handleRecategorize(txnId, shortDesc, 'cat')}
                            fetchCategoryTree={fetchCategoryTree}
                            formatDate={formatDate}
                          />
                        )}
                      </React.Fragment>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
              <tfoot>
                <tr className="cf-total-row">
                  <td className="cf-td-name" style={{ fontWeight: 600 }}>Total Income</td>
                  <td className="cf-td-num cf-positive" style={{ fontWeight: 600 }}>
                    {fmtFull(incomeCategories.reduce((s, c) => s + c.income_total, 0))}
                  </td>
                  <td className="cf-td-num" style={{ fontWeight: 600 }}>
                    {fmt(incomeCategories.reduce((s, c) => s + c.income_total, 0) / (weeks.length || 1))}
                  </td>
                  <td className="cf-td-trend" />
                </tr>
              </tfoot>
            </table>
          </>
        )}
      </div>

      {/* ─── Biweekly Detail Table ─── */}
      <div className="card" style={{ padding: 0, marginTop: 16 }}>
        <div className="cf-section-header">
          Biweekly Detail
          <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 11, marginLeft: 8 }}>
            Click a period to see transactions
          </span>
        </div>
        <table className="cf-table">
          <thead>
            <tr>
              <th className="cf-th-name">Period</th>
              <th className="cf-th-num">Income</th>
              <th className="cf-th-num">Expenses</th>
              <th className="cf-th-num">Net</th>
              <th className="cf-th-num">Cumulative</th>
            </tr>
          </thead>
          <tbody>
            {weeks.map(w => (
              <React.Fragment key={w.week_start}>
                <tr
                  className={`cf-week-row cf-expandable ${w.net >= 0 ? 'cf-week-pos' : 'cf-week-neg'}`}
                  onClick={() => togglePeriod(w.week_start, w.week_end)}
                >
                  <td className="cf-td-name cf-td-week">
                    {expandedPeriod === w.week_start
                      ? <ChevronDown size={12} className="cf-chevron" />
                      : <ChevronRight size={12} className="cf-chevron" />
                    }
                    {formatPeriodLabel(w.week_start)}
                  </td>
                  <td className="cf-td-num cf-positive">{w.income > 0 ? fmtFull(w.income) : '—'}</td>
                  <td className="cf-td-num cf-negative">{w.expenses > 0 ? fmtFull(w.expenses) : '—'}</td>
                  <td className={`cf-td-num ${w.net >= 0 ? 'cf-positive' : 'cf-negative'}`} style={{ fontWeight: 600 }}>
                    {fmtSigned(w.net)}
                  </td>
                  <td className={`cf-td-num ${w.cumulative >= 0 ? 'cf-positive' : 'cf-negative'}`}>
                    {fmtSigned(w.cumulative)}
                  </td>
                </tr>
                {expandedPeriod === w.week_start && (
                  <tr className="cf-txn-row">
                    <td colSpan={5} style={{ padding: 0 }}>
                      <PeriodDrillDown
                        loading={loadingPeriod}
                        transactions={periodTxns}
                        editingTxnId={editingPeriodTxnId}
                        setEditingTxnId={setEditingPeriodTxnId}
                        categoryTree={categoryTree}
                        onRecategorize={(txnId, shortDesc) => handleRecategorize(txnId, shortDesc, 'period')}
                        fetchCategoryTree={fetchCategoryTree}
                        formatDate={formatDate}
                        fmtFull={fmtFull}
                      />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* ─── Excluded Categories ─── */}
      {excluded_categories.length > 0 && (
        <div className="card" style={{ padding: 0, marginTop: 16 }}>
          <div
            className="cf-section-header cf-expandable"
            onClick={() => setShowExcluded(!showExcluded)}
            style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
          >
            {showExcluded
              ? <ChevronDown size={14} className="cf-chevron" />
              : <ChevronRight size={14} className="cf-chevron" />}
            <span>Excluded Categories</span>
            <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 12, marginLeft: 'auto', paddingRight: 16 }}>
              {excluded_categories.length} categories · net {fmtSigned(excludedTotal)}
            </span>
          </div>
          {showExcluded && (
            <table className="cf-table">
              <thead>
                <tr>
                  <th className="cf-th-name">Category</th>
                  <th className="cf-th-num">Transactions</th>
                  <th className="cf-th-num">Total</th>
                </tr>
              </thead>
              <tbody>
                {excluded_categories.map(cat => (
                  <tr key={cat.name}>
                    <td className="cf-td-name">{cat.name}</td>
                    <td className="cf-td-num">{cat.count}</td>
                    <td className={`cf-td-num ${cat.total >= 0 ? 'cf-negative' : 'cf-positive'}`}>{fmtSigned(cat.total)}</td>
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

/* ─── Side-by-Side Period Drill-Down ─── */
function PeriodDrillDown({
  loading, transactions, editingTxnId, setEditingTxnId,
  categoryTree, onRecategorize, fetchCategoryTree, formatDate, fmtFull,
}) {
  // Split transactions: negative amount = income, positive = expense
  const incomeTxns = useMemo(() =>
    transactions.filter(t => t.amount < 0).sort((a, b) => b.date.localeCompare(a.date)),
    [transactions]
  )
  const expenseTxns = useMemo(() =>
    transactions.filter(t => t.amount > 0).sort((a, b) => b.date.localeCompare(a.date)),
    [transactions]
  )

  const incomeTotal = incomeTxns.reduce((s, t) => s + Math.abs(t.amount), 0)
  const expenseTotal = expenseTxns.reduce((s, t) => s + t.amount, 0)

  if (loading) {
    return (
      <div className="cf-period-loading">
        <Loader size={14} className="spin" />
        <span>Loading transactions...</span>
      </div>
    )
  }

  if (transactions.length === 0) {
    return (
      <div style={{ padding: '16px 20px', color: 'var(--text-muted)', fontSize: 13 }}>
        No transactions found for this period.
      </div>
    )
  }

  return (
    <div className="cf-period-split">
      {/* Income column */}
      <div className="cf-period-col">
        <div className="cf-period-col-header cf-positive">
          Income · {fmtFull(incomeTotal)}
          <span className="cf-period-col-count">{incomeTxns.length} txns</span>
        </div>
        <div className="cf-period-col-scroll">
          {incomeTxns.length === 0 ? (
            <div className="cf-period-empty">No income this period</div>
          ) : (
            incomeTxns.map(txn => (
              <div key={txn.id} className="cf-period-txn">
                <span className="cf-txn-date">{formatDate(txn.date)}</span>
                <span className="cf-txn-desc" title={txn.description}>
                  {txn.merchant_name || txn.description}
                </span>
                <span className="cf-txn-amount income">
                  +${Math.abs(txn.amount).toFixed(2)}
                </span>
                <span className="cf-txn-cat-area" onClick={(e) => e.stopPropagation()}>
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
                      onSelect={(shortDesc) => onRecategorize(txn.id, shortDesc)}
                      onCancel={() => setEditingTxnId(null)}
                      onTreeChanged={fetchCategoryTree}
                    />
                  )}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Expenses column */}
      <div className="cf-period-col">
        <div className="cf-period-col-header cf-negative">
          Expenses · {fmtFull(expenseTotal)}
          <span className="cf-period-col-count">{expenseTxns.length} txns</span>
        </div>
        <div className="cf-period-col-scroll">
          {expenseTxns.length === 0 ? (
            <div className="cf-period-empty">No expenses this period</div>
          ) : (
            expenseTxns.map(txn => (
              <div key={txn.id} className="cf-period-txn">
                <span className="cf-txn-date">{formatDate(txn.date)}</span>
                <span className="cf-txn-desc" title={txn.description}>
                  {txn.merchant_name || txn.description}
                </span>
                <span className="cf-txn-amount expense">
                  -${Math.abs(txn.amount).toFixed(2)}
                </span>
                <span className="cf-txn-cat-area" onClick={(e) => e.stopPropagation()}>
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
                      onSelect={(shortDesc) => onRecategorize(txn.id, shortDesc)}
                      onCancel={() => setEditingTxnId(null)}
                      onTreeChanged={fetchCategoryTree}
                    />
                  )}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

/* ─── Transaction Rows for Cash Flow category drill-down ─── */
function CfTransactionRows({
  loading, transactions, editingTxnId, setEditingTxnId,
  categoryTree, onRecategorize, fetchCategoryTree, formatDate,
  colSpan = 4,
}) {
  if (loading) {
    return (
      <tr className="cf-txn-row">
        <td colSpan={colSpan}>
          <div className="cf-txn-loading">
            <Loader size={14} className="spin" />
            <span>Loading transactions...</span>
          </div>
        </td>
      </tr>
    )
  }

  if (transactions.length === 0) {
    return (
      <tr className="cf-txn-row">
        <td colSpan={colSpan}>
          <div style={{ padding: '12px 52px', color: 'var(--text-muted)', fontSize: 13 }}>
            No transactions found.
          </div>
        </td>
      </tr>
    )
  }

  return transactions.map(txn => (
    <tr key={txn.id} className="cf-txn-row">
      <td colSpan={colSpan}>
        <div className="cf-txn-cell">
          <span className="cf-txn-date">{formatDate(txn.date)}</span>
          <span className="cf-txn-desc" title={txn.description}>
            {txn.merchant_name || txn.description}
          </span>
          <span className={`cf-txn-amount ${txn.amount > 0 ? 'expense' : 'income'}`}>
            {txn.amount > 0 ? '-' : '+'}${Math.abs(txn.amount).toFixed(2)}
          </span>
          <span className="cf-txn-cat-area" onClick={(e) => e.stopPropagation()}>
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

/* ─── Year Picker ─── */
function YearPicker({ years, value, onChange }) {
  return (
    <select
      className="category-select"
      value={value}
      onChange={(e) => onChange(parseInt(e.target.value))}
      style={{ minWidth: 120 }}
    >
      {years.length > 0 ? (
        years.map(y => (
          <option key={y.year} value={y.year}>{y.year}</option>
        ))
      ) : (
        <option value={value}>{value}</option>
      )}
    </select>
  )
}
