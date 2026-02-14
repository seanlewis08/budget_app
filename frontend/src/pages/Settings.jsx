import React, { useState } from 'react'
import { Save, Mail, Key, Database } from 'lucide-react'

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    email_enabled: false,
    email_address: '',
    email_app_password: '',
    anthropic_api_key: '',
    batch_interval: 30,
    auto_confirm_threshold: 3,
  })
  const [saved, setSaved] = useState(false)

  const handleSave = async () => {
    // TODO: Save to backend settings endpoint
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  return (
    <div>
      <div className="page-header">
        <h2>Settings</h2>
        <p>Configure your Budget App</p>
      </div>

      {/* AI Configuration */}
      <div className="card">
        <div className="card-header">
          <h3><Key size={16} style={{ marginRight: 8 }} />AI Categorization</h3>
        </div>
        <div className="settings-group">
          <label>Anthropic API Key</label>
          <input
            type="password"
            placeholder="sk-ant-..."
            value={settings.anthropic_api_key}
            onChange={(e) => setSettings({ ...settings, anthropic_api_key: e.target.value })}
          />
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Used for Claude API categorization (Tier 3 fallback). Get yours at console.anthropic.com
          </p>
        </div>
        <div className="settings-group">
          <label>Auto-confirm threshold</label>
          <input
            type="number"
            min="1"
            max="10"
            value={settings.auto_confirm_threshold}
            onChange={(e) => setSettings({ ...settings, auto_confirm_threshold: parseInt(e.target.value) })}
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
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                How often to batch-send notifications (default: 30 min)
              </p>
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
      <div style={{ marginTop: 16 }}>
        <button className="btn btn-primary" onClick={handleSave} style={{ padding: '10px 24px', fontSize: 14 }}>
          <Save size={14} style={{ marginRight: 6 }} />
          {saved ? 'Saved!' : 'Save Settings'}
        </button>
      </div>
    </div>
  )
}
