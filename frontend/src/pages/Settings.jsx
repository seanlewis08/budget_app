import React, { useState, useEffect } from 'react'
import { Save, Mail, Key, Database, Trash2, ChevronRight, Shield, CheckCircle, AlertCircle, Loader } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export default function SettingsPage() {
  const navigate = useNavigate()
  const [settings, setSettings] = useState({
    // Plaid
    plaid_client_id: '',
    plaid_secret: '',
    plaid_production_secret: '',
    plaid_env: 'sandbox',
    plaid_recovery_code: '',
    plaid_token_encryption_key: '',
    // Anthropic
    anthropic_api_key: '',
    // App preferences
    auto_confirm_threshold: '3',
    // Email (not in DB settings yet, keeping as local state)
    email_enabled: false,
    email_address: '',
    email_app_password: '',
    batch_interval: 30,
  })
  const [settingsMeta, setSettingsMeta] = useState({})  // source info per key
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const [deletedCount, setDeletedCount] = useState(0)
  const [loaded, setLoaded] = useState(false)

  // Load settings from backend
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const res = await fetch('/api/settings/')
        if (res.ok) {
          const data = await res.json()
          const newSettings = { ...settings }
          const meta = {}
          for (const [key, info] of Object.entries(data)) {
            newSettings[key] = info.value || ''
            meta[key] = { is_set: info.is_set, source: info.source }
          }
          setSettings(newSettings)
          setSettingsMeta(meta)
        } else {
          setLoadError('Failed to load settings')
        }
      } catch (err) {
        setLoadError('Could not connect to backend')
      } finally {
        setLoaded(true)
      }
    }
    loadSettings()

    // Fetch count of deleted transactions for the badge
    fetch('/api/transactions/deleted')
      .then(res => res.ok ? res.json() : [])
      .then(data => setDeletedCount(data.length))
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setSaveError(null)
    setSaved(false)

    // Collect only the DB-backed settings (not email, which is local-only for now)
    const dbKeys = [
      'plaid_client_id', 'plaid_secret', 'plaid_production_secret',
      'plaid_env', 'plaid_recovery_code', 'plaid_token_encryption_key',
      'anthropic_api_key', 'auto_confirm_threshold',
    ]
    const payload = {}
    for (const key of dbKeys) {
      payload[key] = settings[key]
    }

    try {
      const res = await fetch('/api/settings/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: payload }),
      })
      const data = await res.json()
      if (res.ok) {
        setSaved(true)
        setTimeout(() => setSaved(false), 3000)
        // Reload to get fresh masked values
        const reloadRes = await fetch('/api/settings/')
        if (reloadRes.ok) {
          const reloadData = await reloadRes.json()
          const newSettings = { ...settings }
          const meta = {}
          for (const [key, info] of Object.entries(reloadData)) {
            newSettings[key] = info.value || ''
            meta[key] = { is_set: info.is_set, source: info.source }
          }
          setSettings(newSettings)
          setSettingsMeta(meta)
        }
      } else {
        setSaveError(data.detail || 'Failed to save settings')
      }
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const sourceLabel = (key) => {
    const meta = settingsMeta[key]
    if (!meta) return null
    if (meta.source === 'database') return <span className="settings-source-badge db">Saved in app</span>
    if (meta.source === 'env') return <span className="settings-source-badge env">From .env file</span>
    return <span className="settings-source-badge none">Not set</span>
  }

  return (
    <div>
      <div className="page-header">
        <h2>Settings</h2>
        <p>Configure API keys, preferences, and integrations</p>
      </div>

      {loadError && (
        <div className="card" style={{ borderColor: 'rgba(248,113,113,0.3)', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--red)' }}>
            <AlertCircle size={16} />
            {loadError}
          </div>
        </div>
      )}

      {/* Plaid Configuration */}
      <div className="card">
        <div className="card-header">
          <h3><Shield size={16} style={{ marginRight: 8 }} />Plaid (Bank Connections)</h3>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
          Required for linking bank accounts. Get credentials at{' '}
          <a href="https://dashboard.plaid.com" target="_blank" rel="noreferrer"
            style={{ color: 'var(--accent)' }}>dashboard.plaid.com</a>
        </p>

        <div className="settings-group">
          <label>Client ID {sourceLabel('plaid_client_id')}</label>
          <input
            type="text"
            placeholder="e.g. 649048..."
            value={settings.plaid_client_id}
            onChange={(e) => setSettings({ ...settings, plaid_client_id: e.target.value })}
          />
        </div>

        <div className="settings-row">
          <div className="settings-group" style={{ flex: 1 }}>
            <label>Sandbox/Development Secret {sourceLabel('plaid_secret')}</label>
            <input
              type="password"
              placeholder="Sandbox or development secret"
              value={settings.plaid_secret}
              onChange={(e) => setSettings({ ...settings, plaid_secret: e.target.value })}
            />
          </div>
          <div className="settings-group" style={{ flex: 1 }}>
            <label>Production Secret {sourceLabel('plaid_production_secret')}</label>
            <input
              type="password"
              placeholder="Production secret (optional)"
              value={settings.plaid_production_secret}
              onChange={(e) => setSettings({ ...settings, plaid_production_secret: e.target.value })}
            />
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-group" style={{ flex: 1 }}>
            <label>Environment {sourceLabel('plaid_env')}</label>
            <select
              value={settings.plaid_env}
              onChange={(e) => setSettings({ ...settings, plaid_env: e.target.value })}
              className="category-select"
            >
              <option value="sandbox">Sandbox</option>
              <option value="development">Development</option>
              <option value="production">Production</option>
            </select>
          </div>
          <div className="settings-group" style={{ flex: 1 }}>
            <label>Recovery Code {sourceLabel('plaid_recovery_code')}</label>
            <input
              type="password"
              placeholder="Plaid recovery code"
              value={settings.plaid_recovery_code}
              onChange={(e) => setSettings({ ...settings, plaid_recovery_code: e.target.value })}
            />
          </div>
        </div>

        <div className="settings-group">
          <label>Token Encryption Key {sourceLabel('plaid_token_encryption_key')}</label>
          <input
            type="password"
            placeholder="Auto-generated on first run if empty"
            value={settings.plaid_token_encryption_key}
            onChange={(e) => setSettings({ ...settings, plaid_token_encryption_key: e.target.value })}
          />
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Used to encrypt Plaid access tokens. Auto-generated if left empty.
          </p>
        </div>
      </div>

      {/* AI Configuration */}
      <div className="card">
        <div className="card-header">
          <h3><Key size={16} style={{ marginRight: 8 }} />AI Categorization</h3>
        </div>
        <div className="settings-group">
          <label>Anthropic API Key {sourceLabel('anthropic_api_key')}</label>
          <input
            type="password"
            placeholder="sk-ant-..."
            value={settings.anthropic_api_key}
            onChange={(e) => setSettings({ ...settings, anthropic_api_key: e.target.value })}
          />
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Used for Claude API categorization (Tier 3 fallback). Get yours at{' '}
            <a href="https://console.anthropic.com" target="_blank" rel="noreferrer"
              style={{ color: 'var(--accent)' }}>console.anthropic.com</a>
          </p>
        </div>
        <div className="settings-group">
          <label>Auto-confirm threshold</label>
          <input
            type="number"
            min="1"
            max="10"
            value={settings.auto_confirm_threshold}
            onChange={(e) => setSettings({ ...settings, auto_confirm_threshold: e.target.value })}
            style={{ width: 80 }}
          />
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Number of confirmations before a merchant is auto-categorized (default: 3)
          </p>
        </div>
      </div>

      {/* Email Notifications */}
      <div className="card">
        <div className="card-header">
          <h3><Mail size={16} style={{ marginRight: 8 }} />Email Notifications (Phase 3)</h3>
        </div>
        <div className="settings-group">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={settings.email_enabled}
              onChange={(e) => setSettings({ ...settings, email_enabled: e.target.checked })}
            />
            Enable email notifications for new transactions
          </label>
        </div>
        {settings.email_enabled && (
          <>
            <div className="settings-group">
              <label>Gmail Address</label>
              <input
                type="email"
                placeholder="you@gmail.com"
                value={settings.email_address}
                onChange={(e) => setSettings({ ...settings, email_address: e.target.value })}
              />
            </div>
            <div className="settings-group">
              <label>Gmail App Password</label>
              <input
                type="password"
                placeholder="xxxx xxxx xxxx xxxx"
                value={settings.email_app_password}
                onChange={(e) => setSettings({ ...settings, email_app_password: e.target.value })}
              />
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                Create an App Password at Google Account &gt; Security &gt; 2-Step Verification &gt; App Passwords
              </p>
            </div>
            <div className="settings-group">
              <label>Batch interval (minutes)</label>
              <input
                type="number"
                min="5"
                max="120"
                value={settings.batch_interval}
                onChange={(e) => setSettings({ ...settings, batch_interval: parseInt(e.target.value) })}
                style={{ width: 80 }}
              />
            </div>
          </>
        )}
      </div>

      {/* Database Info */}
      <div className="card">
        <div className="card-header">
          <h3><Database size={16} style={{ marginRight: 8 }} />Database</h3>
        </div>
        <div className="settings-group">
          <label>Database Location</label>
          <input
            type="text"
            value="~/BudgetApp/budget.db"
            disabled
            style={{ opacity: 0.6 }}
          />
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Your SQLite database. Back up by copying this file.
          </p>
        </div>
      </div>

      {/* Save Button */}
      <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <button
          className="btn btn-primary"
          onClick={handleSave}
          disabled={saving}
          style={{ padding: '10px 24px', fontSize: 14 }}
        >
          {saving ? (
            <><Loader size={14} className="spin" style={{ marginRight: 6 }} /> Saving...</>
          ) : saved ? (
            <><CheckCircle size={14} style={{ marginRight: 6 }} /> Saved!</>
          ) : (
            <><Save size={14} style={{ marginRight: 6 }} /> Save Settings</>
          )}
        </button>
        {saveError && (
          <span style={{ color: 'var(--red)', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
            <AlertCircle size={14} /> {saveError}
          </span>
        )}
      </div>

      {/* Deleted Transactions Link */}
      <div
        className="card settings-link-card"
        style={{ marginTop: 24, cursor: 'pointer' }}
        onClick={() => navigate('/deleted-transactions')}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Trash2 size={16} />
            <span style={{ fontWeight: 500 }}>Deleted Transactions</span>
            {deletedCount > 0 && (
              <span className="deleted-count-badge">{deletedCount}</span>
            )}
          </div>
          <ChevronRight size={16} style={{ color: 'var(--text-muted)' }} />
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '4px 0 0 26px' }}>
          View, restore, or permanently clear deleted transactions
        </p>
      </div>
    </div>
  )
}
