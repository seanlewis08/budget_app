import React, { useState, useEffect, useRef, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { ChevronRight, Plus, X } from 'lucide-react'

/* ─── Inline Quick-Add Form (inside picker) ─── */
export function QuickAddForm({ parentShortDesc, onCreated, onCancel }) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    const shortDesc = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
    try {
      const res = await fetch('/api/categories/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: name.trim(),
          short_desc: shortDesc,
          parent_short_desc: parentShortDesc || undefined,
        }),
      })
      if (res.ok) {
        onCreated(shortDesc)
      } else {
        const err = await res.json()
        alert(err.detail || 'Failed to create category')
      }
    } catch {
      alert('Network error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="cat-picker-quick-add" onSubmit={handleSubmit}>
      <input
        ref={inputRef}
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={parentShortDesc ? 'New subcategory name...' : 'New parent category...'}
        disabled={saving}
      />
      <button type="submit" className="btn btn-primary btn-sm" disabled={!name.trim() || saving}>
        {saving ? '...' : 'Add'}
      </button>
      <button type="button" className="btn-icon" onClick={onCancel}><X size={12} /></button>
    </form>
  )
}

/* ─── Cascading Category Picker (with search) ─── */
/* Uses a portal to render the dropdown at document.body level,
   so it's never clipped by parent overflow:hidden containers. */
export default function CategoryPicker({ categoryTree, onSelect, onCancel, onTreeChanged }) {
  const [selectedParent, setSelectedParent] = useState(null)
  const [showQuickAdd, setShowQuickAdd] = useState(false)
  const [search, setSearch] = useState('')
  const [pos, setPos] = useState(null)
  const anchorRef = useRef(null)
  const dropdownRef = useRef(null)
  const searchRef = useRef(null)

  // Calculate fixed position from anchor element
  useEffect(() => {
    const updatePos = () => {
      if (!anchorRef.current) return
      const rect = anchorRef.current.getBoundingClientRect()
      const dropdownWidth = 240
      const dropdownMaxHeight = 400

      let left = rect.left
      let top = rect.bottom + 4

      // Keep dropdown within viewport horizontally
      if (left + dropdownWidth > window.innerWidth - 16) {
        left = window.innerWidth - dropdownWidth - 16
      }
      if (left < 16) left = 16

      // If dropdown would go below viewport, position above the anchor
      if (top + dropdownMaxHeight > window.innerHeight - 16) {
        top = rect.top - dropdownMaxHeight - 4
        if (top < 16) top = 16
      }

      setPos({ top, left })
    }

    updatePos()

    // Reposition on scroll or resize
    window.addEventListener('scroll', updatePos, true)
    window.addEventListener('resize', updatePos)
    return () => {
      window.removeEventListener('scroll', updatePos, true)
      window.removeEventListener('resize', updatePos)
    }
  }, [])

  // Click-outside handler — check both anchor and dropdown
  useEffect(() => {
    const handler = (e) => {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target) &&
        anchorRef.current && !anchorRef.current.contains(e.target)
      ) {
        onCancel()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onCancel])

  // Focus search when picker opens or navigates back
  useEffect(() => {
    if (pos && !selectedParent) setTimeout(() => searchRef.current?.focus(), 0)
  }, [pos, selectedParent])

  const handleCreated = (shortDesc) => {
    setShowQuickAdd(false)
    if (onTreeChanged) onTreeChanged()
    if (selectedParent) {
      onSelect(shortDesc)
    }
  }

  // Build flat search results across all categories
  const searchResults = useMemo(() => {
    if (!search.trim()) return null
    const q = search.toLowerCase()
    const results = []
    for (const parent of categoryTree) {
      for (const child of (parent.children || [])) {
        if (child.display_name.toLowerCase().includes(q) ||
            parent.display_name.toLowerCase().includes(q)) {
          results.push({
            ...child,
            parentName: parent.display_name,
            parentColor: parent.color,
          })
        }
      }
    }
    return results
  }, [search, categoryTree])

  const pickerContent = (
    <div
      className="cat-picker"
      ref={dropdownRef}
      style={pos ? {
        position: 'fixed',
        top: pos.top,
        left: pos.left,
        zIndex: 10000,
      } : { visibility: 'hidden' }}
    >
      {searchResults ? (
        <div className="cat-picker-list">
          <input
            ref={searchRef}
            className="cat-picker-search"
            type="text"
            placeholder="Search categories..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {searchResults.length === 0 && (
            <div className="cat-picker-item" style={{ opacity: 0.5, pointerEvents: 'none' }}>
              No matches
            </div>
          )}
          {searchResults.map(child => (
            <div
              key={child.id}
              className="cat-picker-item"
              onClick={() => onSelect(child.short_desc)}
            >
              <span className="cat-dot" style={{ background: child.parentColor || 'var(--accent)' }} />
              <span className="cat-picker-label">
                <span style={{ opacity: 0.5, fontSize: '0.85em' }}>{child.parentName} ›</span> {child.display_name}
              </span>
            </div>
          ))}
        </div>
      ) : !selectedParent ? (
        <div className="cat-picker-list">
          <input
            ref={searchRef}
            className="cat-picker-search"
            type="text"
            placeholder="Search categories..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="cat-picker-header">Select Category</div>
          {categoryTree.map(parent => (
            <div
              key={parent.id}
              className="cat-picker-item parent"
              onClick={() => { setSelectedParent(parent); setShowQuickAdd(false) }}
            >
              <span
                className="cat-dot"
                style={{ background: parent.color || 'var(--accent)' }}
              />
              <span className="cat-picker-label">{parent.display_name}</span>
              <ChevronRight size={14} className="cat-picker-arrow" />
            </div>
          ))}
          {showQuickAdd ? (
            <QuickAddForm
              parentShortDesc={null}
              onCreated={handleCreated}
              onCancel={() => setShowQuickAdd(false)}
            />
          ) : (
            <div className="cat-picker-item cat-picker-add" onClick={() => setShowQuickAdd(true)}>
              <Plus size={14} />
              <span className="cat-picker-label">New Category</span>
            </div>
          )}
        </div>
      ) : (
        <div className="cat-picker-list">
          <div
            className="cat-picker-header clickable"
            onClick={() => { setSelectedParent(null); setShowQuickAdd(false) }}
          >
            ← {selectedParent.display_name}
          </div>
          {selectedParent.children.map(child => (
            <div
              key={child.id}
              className="cat-picker-item"
              onClick={() => onSelect(child.short_desc)}
            >
              <span className="cat-picker-label">{child.display_name}</span>
              {child.is_recurring && (
                <span className="cat-recurring-badge">recurring</span>
              )}
            </div>
          ))}
          {showQuickAdd ? (
            <QuickAddForm
              parentShortDesc={selectedParent.short_desc}
              onCreated={handleCreated}
              onCancel={() => setShowQuickAdd(false)}
            />
          ) : (
            <div className="cat-picker-item cat-picker-add" onClick={() => setShowQuickAdd(true)}>
              <Plus size={14} />
              <span className="cat-picker-label">New Subcategory</span>
            </div>
          )}
        </div>
      )}
    </div>
  )

  return (
    <>
      <span ref={anchorRef} className="cat-picker-anchor" />
      {createPortal(pickerContent, document.body)}
    </>
  )
}
