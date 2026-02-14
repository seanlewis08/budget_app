import React, { useState, useRef } from 'react'
import { Upload, FileText, CheckCircle, AlertCircle } from 'lucide-react'

export default function Accounts({ onUpdate }) {
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const [selectedBank, setSelectedBank] = useState('')
  const [autoDetect, setAutoDetect] = useState(true)
  const fileRef = useRef(null)

  const banks = [
    { value: 'discover', label: 'Discover Credit Card' },
    { value: 'sofi_checking', label: 'SoFi Checking' },
    { value: 'sofi_savings', label: 'SoFi Savings' },
    { value: 'wellsfargo', label: 'Wells Fargo Checking' },
  ]

  const handleUpload = async (file) => {
    setUploading(true)
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      let url = '/api/import/csv/auto-detect'
      if (!autoDetect && selectedBank) {
        url = `/api/import/csv?bank=${selectedBank}`
      }

      const res = await fetch(url, {
        method: 'POST',
        body: formData,
      })

      const data = await res.json()
      if (res.ok) {
        setResult({ type: 'success', data })
        onUpdate()
      } else {
        setResult({ type: 'error', message: data.detail || 'Upload failed' })
      }
    } catch (err) {
      setResult({ type: 'error', message: err.message })
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }

  const handleFileSelect = (e) => {
    const file = e.target.files[0]
    if (file) handleUpload(file)
  }

  return (
    <div>
      <div className="page-header">
        <h2>Accounts & Import</h2>
        <p>Import CSV files from your bank accounts</p>
      </div>

      {/* Account Cards */}
      <div className="stats-row">
        {banks.map(bank => (
          <div key={bank.value} className="stat-card">
            <div className="label">{bank.label}</div>
            <div className="value" style={{ fontSize: 16, color: 'var(--text-secondary)' }}>
              Connected via CSV
            </div>
          </div>
        ))}
      </div>

      {/* CSV Import */}
      <div className="card">
        <div className="card-header">
          <h3>Import Transactions</h3>
        </div>

        <div style={{ marginBottom: 16, display: 'flex', gap: 16, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 14, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={autoDetect}
              onChange={(e) => setAutoDetect(e.target.checked)}
            />
            Auto-detect bank format
          </label>

          {!autoDetect && (
            <select
              className="category-select"
              value={selectedBank}
              onChange={(e) => setSelectedBank(e.target.value)}
            >
              <option value="">Select bank...</option>
              {banks.map(bank => (
                <option key={bank.value} value={bank.value}>{bank.label}</option>
              ))}
            </select>
          )}
        </div>

        <div
          className="upload-zone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <input
            type="file"
            ref={fileRef}
            onChange={handleFileSelect}
            accept=".csv"
            style={{ display: 'none' }}
          />
          {uploading ? (
            <>
              <div className="icon" style={{ color: 'var(--accent)' }}>
                <FileText size={40} />
              </div>
              <p>Processing...</p>
            </>
          ) : (
            <>
              <div className="icon" style={{ color: 'var(--text-muted)' }}>
                <Upload size={40} />
              </div>
              <p>Drop a CSV file here or click to browse</p>
              <p style={{ fontSize: 12, marginTop: 4, color: 'var(--text-muted)' }}>
                Supports Discover, SoFi, and Wells Fargo formats
              </p>
            </>
          )}
        </div>

        {result && (
          <div style={{
            marginTop: 16,
            padding: 16,
            borderRadius: 'var(--radius)',
            background: result.type === 'success' ? 'var(--green-bg)' : 'var(--red-bg)',
            border: `1px solid ${result.type === 'success' ? 'rgba(52,211,153,0.3)' : 'rgba(248,113,113,0.3)'}`,
          }}>
            {result.type === 'success' ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle size={18} style={{ color: 'var(--green)' }} />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--green)' }}>
                    Import successful!
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                    {result.data.imported} new transactions imported,
                    {' '}{result.data.skipped_duplicates} duplicates skipped
                    {' '}({result.data.bank} format)
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertCircle size={18} style={{ color: 'var(--red)' }} />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--red)' }}>Import failed</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                    {result.message}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Plaid Section (Phase 2 placeholder) */}
      <div className="card" style={{ opacity: 0.6 }}>
        <div className="card-header">
          <h3>Bank Sync (Phase 2)</h3>
        </div>
        <div className="empty-state" style={{ padding: 30 }}>
          <p>
            Automatic bank syncing via Plaid will be available in Phase 2.
            For now, import your bank CSVs above.
          </p>
        </div>
      </div>
    </div>
  )
}
