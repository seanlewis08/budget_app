import React, { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

export default function Spending() {
  const [categoryData, setCategoryData] = useState([])
  const [trendData, setTrendData] = useState([])
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  })

  useEffect(() => {
    fetchCategorySpending()
    fetchTrend()
  }, [selectedMonth])

  const fetchCategorySpending = async () => {
    try {
      const res = await fetch(`/api/transactions/spending-by-category?month=${selectedMonth}`)
      if (res.ok) {
        const data = await res.json()
        setCategoryData(data.sort((a, b) => b.total - a.total))
      }
    } catch (err) {
      console.error('Failed to fetch spending:', err)
    }
  }

  const fetchTrend = async () => {
    try {
      const res = await fetch('/api/transactions/monthly-trend?months=12')
      if (res.ok) {
        const data = await res.json()
        setTrendData(data)
      }
    } catch (err) {
      console.error('Failed to fetch trend:', err)
    }
  }

  const totalSpending = categoryData.reduce((sum, c) => sum + c.total, 0)

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
          <div className="value">{categoryData.length}</div>
        </div>
        <div className="stat-card">
          <div className="label">Month</div>
          <div style={{ marginTop: 8 }}>
            <input
              type="month"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
              style={{
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                padding: '6px 10px',
                fontSize: '14px',
              }}
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

        {/* Category Breakdown (Pie) */}
        <div className="card">
          <div className="card-header">
            <h3>By Category</h3>
          </div>
          <div className="chart-container">
            {categoryData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={categoryData.slice(0, 10)}
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
                    {categoryData.slice(0, 10).map((entry, index) => (
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

      {/* Category Breakdown Table */}
      <div className="card">
        <div className="card-header">
          <h3>Category Breakdown</h3>
        </div>
        {categoryData.length > 0 ? (
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
              {categoryData.map(cat => (
                <tr key={cat.short_desc}>
                  <td>
                    <span style={{
                      display: 'inline-block',
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      backgroundColor: cat.color || 'var(--accent)',
                      marginRight: 8,
                    }} />
                    {cat.display_name}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 600 }}>${cat.total.toFixed(2)}</td>
                  <td style={{ textAlign: 'right' }}>{cat.count}</td>
                  <td style={{ textAlign: 'right' }}>
                    {totalSpending > 0 ? ((cat.total / totalSpending) * 100).toFixed(1) : 0}%
                  </td>
                </tr>
              ))}
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
