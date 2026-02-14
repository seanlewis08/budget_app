import React, { useState, useEffect } from 'react'
import { Plus } from 'lucide-react'

export default function Budget() {
  const [budgets, setBudgets] = useState([])
  const [categories, setCategories] = useState([])
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  })
  const [showAdd, setShowAdd] = useState(false)
  const [newBudget, setNewBudget] = useState({ category_short_desc: '', amount: '' })

  useEffect(() => {
    fetchBudgets()
    fetchCategories()
  }, [selectedMonth])

  const fetchBudgets = async () => {
    try {
      const res = await fetch(`/api/budgets/?month=${selectedMonth}`)
      if (res.ok) {
        const data = await res.json()
        setBudgets(data)
      }
    } catch (err) {
      console.error('Failed to fetch budgets:', err)
    }
  }

  const fetchCategories = async () => {
    try {
      const res = await fetch('/api/categories/?parent_only=true')
      if (res.ok) {
        setCategories(await res.json())
      }
    } catch (err) {
      console.error('Failed to fetch categories:', err)
    }
  }

  const addBudget = async () => {
    if (!newBudget.category_short_desc || !newBudget.amount) return

    try {
      const res = await fetch('/api/budgets/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category_short_desc: newBudget.category_short_desc,
          month: selectedMonth,
          amount: parseFloat(newBudget.amount),
        }),
      })
      if (res.ok) {
        fetchBudgets()
        setShowAdd(false)
        setNewBudget({ category_short_desc: '', amount: '' })
      }
    } catch (err) {
      console.error('Failed to add budget:', err)
    }
  }

  const totalBudgeted = budgets.reduce((sum, b) => sum + b.budgeted, 0)
  const totalSpent = budgets.reduce((sum, b) => sum + b.spent, 0)

  const getBarColor = (percent) => {
    if (percent >= 100) return 'red'
    if (percent >= 75) return 'yellow'
    return 'green'
  }

  return (
    <div>
      <div className="page-header">
        <h2>Budget Manager</h2>
        <p>Set and track monthly spending targets</p>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="label">Total Budgeted</div>
          <div className="value">${totalBudgeted.toFixed(2)}</div>
        </div>
        <div className="stat-card">
          <div className="label">Total Spent</div>
          <div className={`value ${totalSpent > totalBudgeted ? 'red' : 'green'}`}>
            ${totalSpent.toFixed(2)}
          </div>
        </div>
        <div className="stat-card">
          <div className="label">Remaining</div>
          <div className={`value ${(totalBudgeted - totalSpent) < 0 ? 'red' : 'green'}`}>
            ${(totalBudgeted - totalSpent).toFixed(2)}
          </div>
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

      <div className="card">
        <div className="card-header">
          <h3>Budget Progress</h3>
          <button className="btn btn-primary" onClick={() => setShowAdd(!showAdd)}>
            <Plus size={14} style={{ marginRight: 4 }} />
            Add Budget
          </button>
        </div>

        {showAdd && (
          <div style={{
            display: 'flex',
            gap: '12px',
            alignItems: 'end',
            padding: '12px',
            marginBottom: '16px',
            background: 'var(--bg-secondary)',
            borderRadius: 'var(--radius)',
          }}>
            <div className="settings-group" style={{ margin: 0, flex: 1 }}>
              <label>Category</label>
              <select
                className="category-select"
                value={newBudget.category_short_desc}
                onChange={(e) => setNewBudget({ ...newBudget, category_short_desc: e.target.value })}
                style={{ width: '100%' }}
              >
                <option value="">Select category...</option>
                {categories.map(cat => (
                  <option key={cat.id} value={cat.short_desc}>{cat.display_name}</option>
                ))}
              </select>
            </div>
            <div className="settings-group" style={{ margin: 0, width: 150 }}>
              <label>Amount</label>
              <input
                type="number"
                placeholder="500.00"
                value={newBudget.amount}
                onChange={(e) => setNewBudget({ ...newBudget, amount: e.target.value })}
              />
            </div>
            <button className="btn btn-primary" onClick={addBudget}>Save</button>
            <button className="btn btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        )}

        {budgets.length > 0 ? (
          <div>
            {budgets.map(budget => (
              <div key={budget.id} className="budget-item">
                <div style={{ width: 150 }}>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{budget.category_name}</div>
                </div>
                <div className="budget-bar-container">
                  <div className="budget-bar-label">
                    <span>${budget.spent.toFixed(2)} spent</span>
                    <span>${budget.budgeted.toFixed(2)} budget</span>
                  </div>
                  <div className="budget-bar">
                    <div
                      className={`budget-bar-fill ${getBarColor(budget.percent_used)}`}
                      style={{ width: `${Math.min(budget.percent_used, 100)}%` }}
                    />
                  </div>
                </div>
                <div style={{
                  width: 80,
                  textAlign: 'right',
                  fontWeight: 600,
                  fontSize: 14,
                  color: budget.remaining >= 0 ? 'var(--green)' : 'var(--red)',
                }}>
                  ${budget.remaining.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <h3>No budgets set</h3>
            <p>Click "Add Budget" to set spending targets for this month.</p>
          </div>
        )}
      </div>
    </div>
  )
}
