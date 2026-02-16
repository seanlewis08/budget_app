import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Sparkles, RefreshCw, Send, Loader, AlertCircle, User, Bot, FileText, Trash2 } from 'lucide-react'

/**
 * Simple markdown-ish renderer for the AI response.
 * Handles: ## headers, **bold**, bullet lists, $dollar amounts.
 */
function renderMarkdown(text) {
  if (!text) return null

  const lines = text.split('\n')
  const elements = []
  let listBuffer = []
  let key = 0

  const flushList = () => {
    if (listBuffer.length > 0) {
      elements.push(
        <ul key={key++} className="insights-list">
          {listBuffer.map((item, i) => <li key={i}>{formatInline(item)}</li>)}
        </ul>
      )
      listBuffer = []
    }
  }

  const formatInline = (line) => {
    const parts = []
    let remaining = line
    let idx = 0
    while (remaining.length > 0) {
      const boldStart = remaining.indexOf('**')
      if (boldStart === -1) {
        parts.push(<span key={idx++}>{highlightDollars(remaining)}</span>)
        break
      }
      if (boldStart > 0) {
        parts.push(<span key={idx++}>{highlightDollars(remaining.slice(0, boldStart))}</span>)
      }
      const boldEnd = remaining.indexOf('**', boldStart + 2)
      if (boldEnd === -1) {
        parts.push(<span key={idx++}>{highlightDollars(remaining.slice(boldStart))}</span>)
        break
      }
      parts.push(<strong key={idx++}>{highlightDollars(remaining.slice(boldStart + 2, boldEnd))}</strong>)
      remaining = remaining.slice(boldEnd + 2)
    }
    return parts
  }

  const highlightDollars = (text) => {
    const dollarRegex = /([+-]?\$[\d,]+\.?\d*%?)/g
    const parts = text.split(dollarRegex)
    return parts.map((part, i) => {
      if (dollarRegex.test(part)) {
        const isNegative = part.startsWith('-')
        const isPositive = part.startsWith('+')
        const cls = isNegative ? 'insights-amount loss' : isPositive ? 'insights-amount gain' : 'insights-amount'
        return <span key={i} className={cls}>{part}</span>
      }
      dollarRegex.lastIndex = 0
      return part
    })
  }

  for (const line of lines) {
    const trimmed = line.trim()

    if (trimmed.startsWith('## ')) {
      flushList()
      elements.push(
        <h3 key={key++} className="insights-section-header">{trimmed.slice(3)}</h3>
      )
      continue
    }

    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      listBuffer.push(trimmed.slice(2))
      continue
    }

    if (/^\d+\.\s/.test(trimmed)) {
      listBuffer.push(trimmed.replace(/^\d+\.\s/, ''))
      continue
    }

    if (trimmed === '') {
      flushList()
      elements.push(<div key={key++} className="insights-spacer" />)
      continue
    }

    flushList()
    elements.push(
      <p key={key++} className="insights-paragraph">{formatInline(trimmed)}</p>
    )
  }
  flushList()

  return elements
}

// ── LocalStorage helpers ──

const STORAGE_KEY = 'budget_app_insights'

function loadSavedInsight() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const data = JSON.parse(raw)
    // Validate structure
    if (data && data.analysis && data.timestamp) {
      return data
    }
  } catch { /* ignore */ }
  return null
}

function saveInsight(analysis, context, chatHistory) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      analysis,
      context: context || '',
      chatHistory: chatHistory || [],
      timestamp: Date.now(),
    }))
  } catch { /* ignore */ }
}

function clearSavedInsight() {
  try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
}


export default function Insights() {
  // Load saved state on mount
  const saved = useRef(loadSavedInsight())

  const [analysis, setAnalysis] = useState(saved.current?.analysis || '')
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState(null)

  // Context box
  const [userContext, setUserContext] = useState(saved.current?.context || '')

  // Chat state
  const [chatHistory, setChatHistory] = useState(saved.current?.chatHistory || [])
  const [chatInput, setChatInput] = useState('')
  const [chatStreaming, setChatStreaming] = useState(false)
  const [chatStreamText, setChatStreamText] = useState('')

  const analysisRef = useRef(null)
  const chatEndRef = useRef(null)
  const inputRef = useRef(null)

  // Save to localStorage whenever analysis or chat changes
  useEffect(() => {
    if (analysis) {
      saveInsight(analysis, userContext, chatHistory)
    }
  }, [analysis, userContext, chatHistory])

  // Auto-scroll analysis as it streams
  useEffect(() => {
    if (analysisRef.current && analyzing) {
      analysisRef.current.scrollTop = analysisRef.current.scrollHeight
    }
  }, [analysis, analyzing])

  // Auto-scroll chat
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatHistory, chatStreamText])

  // ── Stream from SSE endpoint ──
  const streamFromEndpoint = useCallback(async (url, body, onToken, onDone, onError) => {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (data === '[DONE]') {
              onDone()
              return
            }
            try {
              const event = JSON.parse(data)
              if (event.type === 'text') {
                onToken(event.content)
              } else if (event.type === 'error') {
                onError(event.content)
                return
              }
            } catch (e) {
              // Skip malformed JSON
            }
          }
        }
      }
      onDone()
    } catch (err) {
      onError(err.message)
    }
  }, [])

  // ── Run Analysis ──
  const runAnalysis = useCallback(async () => {
    setAnalyzing(true)
    setAnalysis('')
    setError(null)
    setChatHistory([])
    setChatStreamText('')

    let fullText = ''
    await streamFromEndpoint(
      '/api/insights/analyze',
      { context: userContext },
      (token) => {
        fullText += token
        setAnalysis(fullText)
      },
      () => {
        setAnalyzing(false)
        setChatHistory([{ role: 'assistant', content: fullText }])
      },
      (errMsg) => {
        setError(errMsg)
        setAnalyzing(false)
      },
    )
  }, [streamFromEndpoint, userContext])

  // ── Clear saved analysis ──
  const handleClear = () => {
    setAnalysis('')
    setChatHistory([])
    setChatStreamText('')
    setError(null)
    clearSavedInsight()
  }

  // ── Send Chat Message ──
  const sendMessage = useCallback(async () => {
    const msg = chatInput.trim()
    if (!msg || chatStreaming) return

    setChatInput('')
    setChatStreaming(true)
    setChatStreamText('')

    const newHistory = [...chatHistory, { role: 'user', content: msg }]
    setChatHistory(newHistory)

    let responseText = ''
    await streamFromEndpoint(
      '/api/insights/chat',
      { message: msg, history: chatHistory, context: userContext },
      (token) => {
        responseText += token
        setChatStreamText(responseText)
      },
      () => {
        setChatStreaming(false)
        setChatStreamText('')
        setChatHistory(prev => [...prev, { role: 'assistant', content: responseText }])
      },
      (errMsg) => {
        setChatStreaming(false)
        setChatStreamText('')
        setChatHistory(prev => [...prev, { role: 'assistant', content: `Error: ${errMsg}` }])
      },
    )
  }, [chatInput, chatHistory, chatStreaming, streamFromEndpoint, userContext])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // Chat messages (skip the first assistant message which is the analysis)
  const chatMessages = chatHistory.slice(1)

  // Format saved timestamp
  const savedTimestamp = saved.current?.timestamp
  const lastRunLabel = analysis && !analyzing
    ? `Last run: ${new Date(savedTimestamp || Date.now()).toLocaleString()}`
    : null

  return (
    <div className="page-content insights-page">
      <div className="page-header">
        <h2><Sparkles size={22} /> Financial Insights</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {lastRunLabel && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{lastRunLabel}</span>
          )}
          {analysis && !analyzing && (
            <button className="btn btn-secondary" onClick={handleClear} title="Clear saved analysis">
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {/* ── Context + Trigger (shown when no analysis or user wants to re-run) ── */}
      {!analysis && !analyzing && (
        <div className="card insights-trigger-card">
          <div className="insights-trigger-header">
            <FileText size={20} />
            <div>
              <h3>Generate Financial Analysis</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: 13, margin: 0 }}>
                Your financial data will be analyzed with personalized advice toward your $20K savings goal.
              </p>
            </div>
          </div>

          <div className="insights-context-box">
            <label>Additional Context <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>(optional)</span></label>
            <textarea
              value={userContext}
              onChange={e => setUserContext(e.target.value)}
              placeholder={"Share anything that helps personalize the advice, e.g.:\n• I'm planning to buy a house next year\n• I want to pay off my credit card before saving\n• My rent is increasing by $200 next month\n• I got a raise to $85K starting in March"}
              rows={4}
            />
          </div>

          <button className="btn btn-primary insights-run-btn" onClick={runAnalysis}>
            <Sparkles size={16} />
            Run Analysis
          </button>
        </div>
      )}

      {/* ── Loading state ── */}
      {analyzing && !analysis && (
        <div className="card insights-analysis-card">
          <div className="insights-loading">
            <Loader size={20} className="spin" />
            <span>Gathering your financial data and generating analysis...</span>
          </div>
        </div>
      )}

      {/* ── Analysis Panel ── */}
      {analysis && (
        <div className="card insights-analysis-card" ref={analysisRef}>
          {error && (
            <div className="insights-error">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          <div className="insights-content">
            {renderMarkdown(analysis)}
            {analyzing && <span className="insights-cursor">|</span>}
          </div>

          {!analyzing && (
            <div className="insights-analysis-footer">
              <button className="btn btn-secondary" onClick={runAnalysis}>
                <RefreshCw size={14} />
                Re-run Analysis
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Chat Section ── */}
      {!analyzing && analysis && (
        <div className="card insights-chat-card">
          <div className="insights-chat-header">
            <h3>Ask a Follow-up</h3>
            <span className="insights-chat-hint">Ask about specific expenses, savings strategies, "what if" scenarios...</span>
          </div>

          {chatMessages.length > 0 && (
            <div className="insights-chat-thread">
              {chatMessages.map((msg, i) => (
                <div key={i} className={`insights-chat-msg ${msg.role}`}>
                  <div className="insights-chat-avatar">
                    {msg.role === 'user' ? <User size={14} /> : <Bot size={14} />}
                  </div>
                  <div className="insights-chat-bubble">
                    {msg.role === 'assistant' ? renderMarkdown(msg.content) : msg.content}
                  </div>
                </div>
              ))}

              {chatStreaming && chatStreamText && (
                <div className="insights-chat-msg assistant">
                  <div className="insights-chat-avatar"><Bot size={14} /></div>
                  <div className="insights-chat-bubble">
                    {renderMarkdown(chatStreamText)}
                    <span className="insights-cursor">|</span>
                  </div>
                </div>
              )}

              {chatStreaming && !chatStreamText && (
                <div className="insights-chat-msg assistant">
                  <div className="insights-chat-avatar"><Bot size={14} /></div>
                  <div className="insights-chat-bubble">
                    <Loader size={14} className="spin" /> Thinking...
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>
          )}

          <div className="insights-chat-input-row">
            <input
              ref={inputRef}
              type="text"
              className="insights-chat-input"
              placeholder="What if I cancel my streaming subscriptions?"
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={chatStreaming}
            />
            <button
              className="btn btn-primary insights-send-btn"
              onClick={sendMessage}
              disabled={!chatInput.trim() || chatStreaming}
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
