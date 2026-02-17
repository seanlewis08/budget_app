import React, { useState, useRef, useEffect } from 'react'

const CATEGORIES_DEFAULT = [
  { id: 'housing', label: 'Housing', on: true },
  { id: 'food', label: 'Food & Dining', on: true },
  { id: 'transport', label: 'Transportation', on: true },
  { id: 'utilities', label: 'Utilities', on: true },
  { id: 'entertainment', label: 'Entertainment', on: false },
  { id: 'healthcare', label: 'Healthcare', on: false },
  { id: 'shopping', label: 'Shopping', on: false },
  { id: 'savings', label: 'Savings', on: false },
]

const TOTAL_STEPS = 5

export default function SetupWizard({ onComplete }) {
  const [step, setStep] = useState(0)
  const [userName, setUserName] = useState('')
  const [bankChoice, setBankChoice] = useState(null)
  const [categories, setCategories] = useState(CATEGORIES_DEFAULT)
  const [insights, setInsights] = useState({
    spending: true,
    alerts: true,
    savings: false,
    investments: false,
  })
  const confettiRef = useRef(null)

  const toggleCategory = (id) => {
    setCategories(prev => prev.map(c => c.id === id ? { ...c, on: !c.on } : c))
  }

  const toggleInsight = (key) => {
    setInsights(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const navigate = (dir) => {
    const next = step + dir
    if (next < 0) return
    if (next >= TOTAL_STEPS) {
      // Save wizard preferences
      const prefs = { userName, bankChoice, categories: categories.filter(c => c.on).map(c => c.id), insights }
      localStorage.setItem('budget_app_prefs', JSON.stringify(prefs))
      onComplete()
      return
    }
    setStep(next)
  }

  // Confetti on final step
  useEffect(() => {
    if (step === TOTAL_STEPS - 1 && confettiRef.current) {
      const container = confettiRef.current
      container.innerHTML = ''
      const colors = ['#5ce0b8', '#60a5fa', '#a78bfa', '#fbbf24', '#f87171', '#4ade80']
      for (let i = 0; i < 40; i++) {
        const c = document.createElement('div')
        c.className = 'wiz-confetti'
        c.style.left = Math.random() * 100 + '%'
        c.style.top = '-10px'
        c.style.background = colors[Math.floor(Math.random() * colors.length)]
        c.style.animationDelay = (Math.random() * 0.8) + 's'
        c.style.width = (6 + Math.random() * 6) + 'px'
        c.style.height = (6 + Math.random() * 6) + 'px'
        c.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px'
        container.appendChild(c)
      }
    }
  }, [step])

  const buttonLabel = step === 0 ? 'Get Started' : step === TOTAL_STEPS - 1 ? 'Launch App' : 'Continue'

  return (
    <div className="wiz-container">
      {/* Progress bar */}
      <div className="wiz-progress">
        {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
          <div
            key={i}
            className={`wiz-progress-step ${i === step ? 'active' : ''} ${i < step ? 'completed' : ''}`}
          />
        ))}
        <span className="wiz-step-count">{step + 1} / {TOTAL_STEPS}</span>
      </div>

      {/* Steps */}
      <div className="wiz-body">

        {/* Step 0: Welcome */}
        <div className={`wiz-step ${step === 0 ? 'active' : step > 0 ? 'exit-left' : ''}`}>
          <div className="wiz-icon teal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
              <polyline points="9 22 9 12 15 12 15 22" />
            </svg>
          </div>
          <h2 className="wiz-title">Welcome to Budget App</h2>
          <p className="wiz-subtitle">Your finances stay on your machine — no cloud, no third parties. Let's get you set up in a few quick steps.</p>
          <div className="wiz-input-group">
            <label>What should we call you?</label>
            <input
              type="text"
              className="wiz-text-input"
              placeholder="Enter your name"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              autoFocus
            />
          </div>
        </div>

        {/* Step 1: Bank Connection */}
        <div className={`wiz-step ${step === 1 ? 'active' : step > 1 ? 'exit-left' : ''}`}>
          <div className="wiz-icon blue">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
              <line x1="1" y1="10" x2="23" y2="10" />
            </svg>
          </div>
          <h2 className="wiz-title">Connect Your Bank</h2>
          <p className="wiz-subtitle">Link your accounts through Plaid to automatically import transactions. Everything is processed locally.</p>
          <div className="wiz-card-grid single-col">
            {[
              { value: 'plaid', label: 'Connect with Plaid', desc: 'Securely link checking, savings, and credit cards' },
              { value: 'csv', label: 'Import CSV files', desc: 'Upload transaction exports from your bank' },
              { value: 'skip', label: 'Skip for now', desc: 'You can connect accounts later in Settings' },
            ].map(opt => (
              <div
                key={opt.value}
                className={`wiz-select-card ${bankChoice === opt.value ? 'selected' : ''}`}
                onClick={() => setBankChoice(opt.value)}
              >
                <div className="wiz-card-radio" />
                <div className="wiz-card-label">
                  {opt.label}
                  <small>{opt.desc}</small>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Step 2: Budget Categories */}
        <div className={`wiz-step ${step === 2 ? 'active' : step > 2 ? 'exit-left' : ''}`}>
          <div className="wiz-icon purple">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
              <line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
            </svg>
          </div>
          <h2 className="wiz-title">Budget Categories</h2>
          <p className="wiz-subtitle">Select the categories you'd like to track. You can customize these anytime.</p>
          <div className="wiz-card-grid">
            {categories.map(cat => (
              <div
                key={cat.id}
                className={`wiz-select-card ${cat.on ? 'selected' : ''}`}
                onClick={() => toggleCategory(cat.id)}
              >
                <div className="wiz-card-check" />
                <div className="wiz-card-label">{cat.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Step 3: AI Insights */}
        <div className={`wiz-step ${step === 3 ? 'active' : step > 3 ? 'exit-left' : ''}`}>
          <div className="wiz-icon amber">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
          </div>
          <h2 className="wiz-title">AI-Powered Insights</h2>
          <p className="wiz-subtitle">Enable intelligent analysis of your spending patterns. Your data never leaves your machine.</p>
          {[
            { key: 'spending', label: 'Spending analysis', desc: 'Weekly summaries of spending patterns' },
            { key: 'alerts', label: 'Budget alerts', desc: 'Get notified when nearing budget limits' },
            { key: 'savings', label: 'Savings suggestions', desc: 'AI tips to help you save more' },
            { key: 'investments', label: 'Investment tracking', desc: 'Monitor portfolio performance' },
          ].map(item => (
            <div key={item.key} className="wiz-toggle-row">
              <div className="wiz-toggle-label">
                {item.label}
                <small>{item.desc}</small>
              </div>
              <div
                className={`wiz-toggle ${insights[item.key] ? 'on' : ''}`}
                onClick={() => toggleInsight(item.key)}
              />
            </div>
          ))}
        </div>

        {/* Step 4: All Done */}
        <div className={`wiz-step ${step === 4 ? 'active' : step > 4 ? 'exit-left' : ''}`}>
          <div className="wiz-confetti-container" ref={confettiRef} />
          <div className="wiz-completion-check">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="4 12 9 17 20 6" />
            </svg>
          </div>
          <h2 className="wiz-title">You're All Set!</h2>
          <p className="wiz-subtitle">
            {userName.trim()
              ? `Great job, ${userName.trim()}! Your budget app is ready. Everything runs locally on your machine — your data, your rules.`
              : 'Your budget app is ready to go. Everything runs locally on your machine — your data, your rules.'}
          </p>
        </div>
      </div>

      {/* Footer */}
      <div className="wiz-footer">
        <button
          className="wiz-btn wiz-btn-ghost"
          onClick={() => navigate(-1)}
          style={{ visibility: step === 0 ? 'hidden' : 'visible' }}
        >
          Back
        </button>
        <button className="wiz-btn wiz-btn-primary" onClick={() => navigate(1)}>
          {buttonLabel}
        </button>
      </div>
    </div>
  )
}
