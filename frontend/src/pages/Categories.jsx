import React, { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Plus, ChevronDown, ChevronRight, Pencil, Trash2, X, Check, FolderTree, ChevronsDownUp, ChevronsUpDown } from 'lucide-react'

/* ─── Inline Edit / Create Form ─── */
function CategoryForm({ initial, isSubcategory, onSave, onCancel }) {
  const [displayName, setDisplayName] = useState(initial?.display_name || '')
  const [shortDesc, setShortDesc] = useState(initial?.short_desc || '')
  const [color, setColor] = useState(initial?.color || '#60a5fa')
  const [isRecurring, setIsRecurring] = useState(initial?.is_recurring || false)
  const [isIncome, setIsIncome] = useState(initial?.is_income || false)
  const [autoSlug, setAutoSlug] = useState(!initial) // auto-generate short_desc for new categories

  const handleDisplayNameChange = (val) => {
    setDisplayName(val)
    if (autoSlug) {
      setShortDesc(val.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''))
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!displayName.trim() || !shortDesc.trim()) return
    onSave({ display_name: displayName.trim(), short_desc: shortDesc.trim(), color, is_recurring: isRecurring, is_income: isIncome })
  }

  return (
    <form className="cat-form" onSubmit={handleSubmit}>
      <div className="cat-form-row">
        <div className="cat-form-field">
          <label>Display Name</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => handleDisplayNameChange(e.target.value)}
            placeholder={isSubcategory ? 'e.g. Coffee Shops' : 'e.g. Food & Dining'}
            autoFocus
          />
        </div>
        <div className="cat-form-field">
          <label>Short Key</label>
          <input
            type="text"
            value={shortDesc}
            onChange={(e) => { setShortDesc(e.target.value); setAutoSlug(false) }}
            placeholder="e.g. coffee_shops"
          />
        </div>
        {!isSubcategory && (
          <div className="cat-form-field cat-form-color">
            <label>Color</label>
            <input type="color" value={color} onChange={(e) => setColor(e.target.value)} />
          </div>
        )}
      </div>
      <div className="cat-form-row">
        {isSubcategory && (
          <label className="cat-form-check">
            <input type="checkbox" checked={isRecurring} onChange={(e) => setIsRecurring(e.target.checked)} />
            Recurring
          </label>
        )}
        <label className="cat-form-check">
          <input type="checkbox" checked={isIncome} onChange={(e) => setIsIncome(e.target.checked)} />
          Income category
        </label>
        <div className="cat-form-actions">
          <button type="submit" className="btn btn-primary btn-sm" disabled={!displayName.trim() || !shortDesc.trim()}>
            <Check size={14} /> {initial ? 'Save' : 'Create'}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>
            <X size={14} /> Cancel
          </button>
        </div>
      </div>
    </form>
  )
}

/* ─── Move-to-Parent Picker (portal-based for proper positioning) ─── */
function MoveParentPicker({ categoryTree, currentParentId, onSelect, onCancel, anchorRef }) {
  const dropdownRef = useRef(null)
  const [pos, setPos] = useState(null)

  // Calculate fixed position from anchor element
  useEffect(() => {
    const updatePos = () => {
      if (!anchorRef?.current) return
      const rect = anchorRef.current.getBoundingClientRect()
      const dropdownWidth = 220
      const dropdownMaxHeight = 300

      let left = rect.left
      let top = rect.bottom + 4

      // Keep within viewport horizontally
      if (left + dropdownWidth > window.innerWidth - 16) {
        left = window.innerWidth - dropdownWidth - 16
      }
      if (left < 16) left = 16

      // If would go below viewport, position above
      if (top + dropdownMaxHeight > window.innerHeight - 16) {
        top = rect.top - dropdownMaxHeight - 4
        if (top < 16) top = 16
      }

      setPos({ top, left })
    }

    updatePos()
    window.addEventListener('scroll', updatePos, true)
    window.addEventListener('resize', updatePos)
    return () => {
      window.removeEventListener('scroll', updatePos, true)
      window.removeEventListener('resize', updatePos)
    }
  }, [anchorRef])

  // Click-outside handler
  useEffect(() => {
    const handler = (e) => {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target) &&
        anchorRef?.current && !anchorRef.current.contains(e.target)
      ) onCancel()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onCancel, anchorRef])

  const parents = categoryTree.filter(p => p.id !== currentParentId)

  if (!pos) return null

  const pickerContent = (
    <div className="move-picker" ref={dropdownRef} style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 9999 }}>
      <div className="move-picker-header">Move to...</div>
      {parents.map(p => (
        <div
          key={p.id}
          className="move-picker-item"
          onClick={() => onSelect(p.short_desc)}
        >
          <span className="cat-dot" style={{ background: p.color || 'var(--accent)' }} />
          {p.display_name}
        </div>
      ))}
      {parents.length === 0 && (
        <div className="move-picker-item" style={{ opacity: 0.5, cursor: 'default' }}>
          No other parents available
        </div>
      )}
    </div>
  )

  return createPortal(pickerContent, document.body)
}

/* ─── Child Row (needs ref for move-picker anchor) ─── */
function ChildRow({ child, parent, categoryTree, movingId, setMovingId, moveCategory, deleteCategory }) {
  const moveBtnRef = useRef(null)

  return (
    <div className="cat-tree-child-row">
      <span className="cat-tree-indent" />
      <span className="cat-tree-name">{child.display_name}</span>
      <span className="cat-tree-key">{child.short_desc}</span>
      {child.is_recurring && <span className="cat-recurring-badge">recurring</span>}
      <button
        ref={moveBtnRef}
        className="btn-icon"
        title="Move to different parent"
        onClick={() => setMovingId(movingId === child.id ? null : child.id)}
      >
        <FolderTree size={14} />
      </button>
      <button
        className="btn-icon danger"
        title="Delete subcategory"
        onClick={() => deleteCategory(child.short_desc, child.display_name)}
      >
        <Trash2 size={14} />
      </button>
      {movingId === child.id && (
        <MoveParentPicker
          categoryTree={categoryTree}
          currentParentId={parent.id}
          anchorRef={moveBtnRef}
          onSelect={(newParentShortDesc) => moveCategory(child.short_desc, newParentShortDesc)}
          onCancel={() => setMovingId(null)}
        />
      )}
    </div>
  )
}

/* ─── Categories Page ─── */
export default function Categories() {
  const [categoryTree, setCategoryTree] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedParents, setExpandedParents] = useState(() => {
    const saved = sessionStorage.getItem('categoriesExpanded')
    return saved ? new Set(JSON.parse(saved)) : new Set()
  })
  const [addingParent, setAddingParent] = useState(false)
  const [addingChildOf, setAddingChildOf] = useState(null) // parent id
  const [editingId, setEditingId] = useState(null)
  const [renamingId, setRenamingId] = useState(null) // parent id being renamed
  const [renameValue, setRenameValue] = useState('')
  const [movingId, setMovingId] = useState(null) // child id currently showing move picker
  const [error, setError] = useState(null)

  useEffect(() => { fetchTree() }, [])

  // Persist expanded state
  useEffect(() => {
    sessionStorage.setItem('categoriesExpanded', JSON.stringify([...expandedParents]))
  }, [expandedParents])

  const fetchTree = async () => {
    try {
      const res = await fetch('/api/categories/tree')
      if (res.ok) {
        const data = await res.json()
        setCategoryTree(data)
      }
    } catch (err) {
      console.error('Failed to fetch categories:', err)
    } finally {
      setLoading(false)
    }
  }

  const toggleExpand = (parentId) => {
    setExpandedParents(prev => {
      const next = new Set(prev)
      next.has(parentId) ? next.delete(parentId) : next.add(parentId)
      return next
    })
  }

  const createCategory = async (data, parentShortDesc = null) => {
    setError(null)
    try {
      const body = { ...data }
      if (parentShortDesc) body.parent_short_desc = parentShortDesc

      const res = await fetch('/api/categories/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (res.ok) {
        setAddingParent(false)
        setAddingChildOf(null)
        await fetchTree()
        // Auto-expand the parent we just added to
        if (parentShortDesc) {
          const parent = categoryTree.find(p => p.short_desc === parentShortDesc)
          if (parent) {
            setExpandedParents(prev => new Set([...prev, parent.id]))
          }
        }
      } else {
        const err = await res.json()
        setError(err.detail || 'Failed to create category')
      }
    } catch (err) {
      setError('Network error creating category')
    }
  }

  const deleteCategory = async (shortDesc, displayName) => {
    if (!confirm(`Delete "${displayName}"? This cannot be undone.`)) return
    setError(null)
    try {
      const res = await fetch(`/api/categories/${shortDesc}`, { method: 'DELETE' })
      if (res.ok) {
        await fetchTree()
      } else {
        const err = await res.json()
        setError(err.detail || 'Failed to delete category')
      }
    } catch (err) {
      setError('Network error deleting category')
    }
  }

  const updateCategory = async (shortDesc, updates) => {
    setError(null)
    try {
      const res = await fetch(`/api/categories/${shortDesc}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      if (res.ok) {
        setRenamingId(null)
        setRenameValue('')
        await fetchTree()
      } else {
        const err = await res.json()
        setError(err.detail || 'Failed to update category')
      }
    } catch (err) {
      setError('Network error updating category')
    }
  }

  const startRename = (parent) => {
    setRenamingId(parent.id)
    setRenameValue(parent.display_name)
    setAddingParent(false)
    setAddingChildOf(null)
  }

  const submitRename = (shortDesc) => {
    const trimmed = renameValue.trim()
    if (!trimmed) return
    updateCategory(shortDesc, { display_name: trimmed })
  }

  const moveCategory = async (childShortDesc, newParentShortDesc) => {
    setError(null)
    setMovingId(null)
    try {
      const res = await fetch(`/api/categories/${childShortDesc}/move`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_parent_short_desc: newParentShortDesc }),
      })
      if (res.ok) {
        await fetchTree()
      } else {
        const err = await res.json()
        setError(err.detail || 'Failed to move category')
      }
    } catch (err) {
      setError('Network error moving category')
    }
  }

  const childCount = categoryTree.reduce((sum, p) => sum + p.children.length, 0)

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h2>Categories</h2>
          <p>Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h2>Categories</h2>
        <p>{categoryTree.length} parent categories, {childCount} subcategories</p>
      </div>

      {error && (
        <div className="error-banner">
          {error}
          <button className="btn-icon" onClick={() => setError(null)}><X size={14} /></button>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3>Category Tree</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setExpandedParents(new Set(categoryTree.map(p => p.id)))}
              title="Expand All"
            >
              <ChevronsUpDown size={14} style={{ marginRight: 4 }} />
              Expand All
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setExpandedParents(new Set())}
              title="Collapse All"
            >
              <ChevronsDownUp size={14} style={{ marginRight: 4 }} />
              Collapse All
            </button>
            <button className="btn btn-primary" onClick={() => { setAddingParent(true); setAddingChildOf(null); setEditingId(null) }}>
              <Plus size={14} style={{ marginRight: 4 }} />
              New Parent Category
            </button>
          </div>
        </div>

        {addingParent && (
          <div className="cat-tree-form-wrap">
            <CategoryForm
              isSubcategory={false}
              onSave={(data) => createCategory(data)}
              onCancel={() => setAddingParent(false)}
            />
          </div>
        )}

        <div className="cat-tree">
          {categoryTree.map(parent => (
            <div key={parent.id} className="cat-tree-parent">
              <div className="cat-tree-parent-row" onClick={() => renamingId !== parent.id && toggleExpand(parent.id)}>
                <span className="cat-tree-expand">
                  {expandedParents.has(parent.id) ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </span>
                <span className="cat-dot" style={{ background: parent.color || 'var(--accent)' }} />
                {renamingId === parent.id ? (
                  <form
                    className="cat-rename-form"
                    onSubmit={(e) => { e.preventDefault(); submitRename(parent.short_desc) }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="text"
                      className="cat-rename-input"
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      autoFocus
                      onKeyDown={(e) => { if (e.key === 'Escape') { setRenamingId(null); setRenameValue('') } }}
                    />
                    <button type="submit" className="btn-icon" title="Save" disabled={!renameValue.trim()}>
                      <Check size={14} />
                    </button>
                    <button type="button" className="btn-icon" title="Cancel" onClick={() => { setRenamingId(null); setRenameValue('') }}>
                      <X size={14} />
                    </button>
                  </form>
                ) : (
                  <>
                    <span className="cat-tree-name">{parent.display_name}</span>
                    <span className="cat-tree-key">{parent.short_desc}</span>
                    <span className="cat-tree-count">{parent.children.length} sub</span>
                  </>
                )}
                {renamingId !== parent.id && (
                  <>
                    <button
                      className="btn-icon"
                      title="Rename"
                      onClick={(e) => { e.stopPropagation(); startRename(parent) }}
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      className="btn-icon"
                      title="Add subcategory"
                      onClick={(e) => { e.stopPropagation(); setAddingChildOf(parent.id); setAddingParent(false); setEditingId(null); setExpandedParents(prev => new Set([...prev, parent.id])) }}
                    >
                      <Plus size={14} />
                    </button>
                    <button
                      className="btn-icon danger"
                      title="Delete parent category"
                      onClick={(e) => { e.stopPropagation(); deleteCategory(parent.short_desc, parent.display_name) }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
              </div>

              {expandedParents.has(parent.id) && (
                <div className="cat-tree-children">
                  {parent.children.map(child => (
                    <ChildRow
                      key={child.id}
                      child={child}
                      parent={parent}
                      categoryTree={categoryTree}
                      movingId={movingId}
                      setMovingId={setMovingId}
                      moveCategory={moveCategory}
                      deleteCategory={deleteCategory}
                    />
                  ))}

                  {addingChildOf === parent.id && (
                    <div className="cat-tree-form-wrap sub">
                      <CategoryForm
                        isSubcategory
                        onSave={(data) => createCategory(data, parent.short_desc)}
                        onCancel={() => setAddingChildOf(null)}
                      />
                    </div>
                  )}

                  {addingChildOf !== parent.id && (
                    <div
                      className="cat-tree-add-child"
                      onClick={() => { setAddingChildOf(parent.id); setAddingParent(false); setEditingId(null) }}
                    >
                      <Plus size={12} /> Add subcategory
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
