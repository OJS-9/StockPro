import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'
import { useAuth } from '@clerk/clerk-react'
import { useBreakpoint } from '../hooks/useBreakpoint'

interface Source {
  index: number
  chunk_id: string | null
  section: string | null
  chunk_type: 'report' | 'research' | 'ir' | 'sec' | 'yfinance'
  similarity_score: number | null
  chunk_text: string
  url?: string | null
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  time: string
  sources?: Source[]
}

const SOURCE_TYPE_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  report: { bg: 'rgba(34,197,94,0.08)', color: '#22c55e', label: 'Report' },
  research: { bg: 'rgba(96,165,250,0.08)', color: '#60a5fa', label: 'Research' },
  sec: { bg: 'rgba(234,179,8,0.08)', color: '#eab308', label: 'SEC Filing' },
  ir: { bg: 'rgba(249,115,22,0.08)', color: '#f97316', label: 'IR' },
  yfinance: { bg: 'rgba(168,85,247,0.08)', color: '#a855f7', label: 'Yahoo Finance' },
}

function UserInitials() {
  return (
    <div style={{ width: 32, height: 32, borderRadius: 10, background: '#232120', border: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600, color: '#d6d3d1', fontFamily: 'Nunito, sans-serif', flexShrink: 0 }}>
      U
    </div>
  )
}

function AIAvatar() {
  return (
    <div style={{ width: 32, height: 32, borderRadius: 10, background: 'linear-gradient(135deg, rgba(34,197,94,0.12), rgba(96,165,250,0.12))', border: '1px solid rgba(34,197,94,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
      <Icon name="auto_awesome" size={18} filled />
    </div>
  )
}

function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', padding: '4px 0' }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{ width: 7, height: 7, borderRadius: '50%', background: '#a8a29e', animation: `typing 1.4s ${i * 200}ms infinite` }} />
      ))}
    </div>
  )
}

function CitationBadge({ label, type, onClick }: { label: string; type?: string; onClick: () => void }) {
  const isTag = type === 'ir' || type === 'yfinance'
  const styles = type ? SOURCE_TYPE_STYLES[type] : null
  return (
    <sup
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: isTag ? 'auto' : 18,
        height: 16,
        padding: isTag ? '0 5px' : '0 4px',
        borderRadius: 4,
        background: styles?.bg || 'rgba(96,165,250,0.15)',
        color: styles?.color || '#60a5fa',
        fontSize: 10,
        fontWeight: 600,
        cursor: 'pointer',
        verticalAlign: 'super',
        lineHeight: 1,
        marginInlineStart: 1,
        marginInlineEnd: 1,
        transition: 'opacity 0.15s',
      }}
    >
      {label}
    </sup>
  )
}

function SourceCard({
  source,
  messageId,
  isExpanded,
  isHighlighted,
  onToggle,
}: {
  source: Source
  messageId: string
  isExpanded: boolean
  isHighlighted: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()
  const typeStyle = SOURCE_TYPE_STYLES[source.chunk_type] || SOURCE_TYPE_STYLES.report
  const preview = source.chunk_text.length > 200 && !isExpanded
    ? source.chunk_text.slice(0, 200) + '...'
    : source.chunk_text

  return (
    <div
      id={`source-${messageId}-${source.index}`}
      style={{
        background: isHighlighted ? 'rgba(96,165,250,0.08)' : '#1c1917',
        border: `1px solid ${isHighlighted ? 'rgba(96,165,250,0.3)' : '#292524'}`,
        borderRadius: 8,
        padding: '10px 12px',
        transition: 'background 0.3s, border-color 0.3s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, color: '#60a5fa',
          background: 'rgba(96,165,250,0.12)', borderRadius: 3,
          padding: '1px 5px', lineHeight: '16px',
        }}>
          {source.chunk_type === 'ir' ? `IR` : source.chunk_type === 'yfinance' ? 'YF' : source.index}
        </span>
        {source.section && (
          <span style={{ fontSize: 12, fontWeight: 600, color: '#d6d3d1' }}>
            {source.section}
          </span>
        )}
        <span style={{
          fontSize: 10, fontWeight: 500, padding: '1px 6px',
          borderRadius: 999, border: `1px solid ${typeStyle.color}20`,
          background: typeStyle.bg, color: typeStyle.color,
        }}>
          {typeStyle.label}
        </span>
        {source.url && (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#a8a29e', display: 'flex', marginInlineStart: 'auto' }}
            title="Open source"
          >
            <Icon name="open_in_new" size={13} />
          </a>
        )}
      </div>
      <div style={{ fontSize: 12.5, color: '#a8a29e', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
        {preview}
      </div>
      {source.chunk_text.length > 200 && (
        <button
          onClick={onToggle}
          style={{
            background: 'none', border: 'none', color: '#60a5fa',
            fontSize: 11, fontWeight: 500, cursor: 'pointer', padding: '4px 0 0',
          }}
        >
          {isExpanded ? t('chat.showLess') : t('chat.showMore')}
        </button>
      )}
    </div>
  )
}

function SourcesPanel({
  sources,
  messageId,
  isOpen,
  onToggle,
  expandedChunks,
  onToggleChunk,
  highlightedSource,
}: {
  sources: Source[]
  messageId: string
  isOpen: boolean
  onToggle: () => void
  expandedChunks: Set<string>
  onToggleChunk: (key: string) => void
  highlightedSource: string | null
}) {
  const { t } = useTranslation()
  if (sources.length === 0) return null

  return (
    <div style={{ marginTop: 6, maxWidth: 680 }}>
      <button
        onClick={onToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'none', border: 'none', color: '#a8a29e',
          fontSize: 12, fontWeight: 500, cursor: 'pointer', padding: '4px 0',
        }}
      >
        <Icon name={isOpen ? 'expand_less' : 'expand_more'} size={16} />
        {t('chat.sources', { count: sources.length })}
      </button>
      {isOpen && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
          {sources.map(source => {
            const key = `${messageId}-${source.index}`
            return (
              <SourceCard
                key={key}
                source={source}
                messageId={messageId}
                isExpanded={expandedChunks.has(key)}
                isHighlighted={highlightedSource === key}
                onToggle={() => onToggleChunk(key)}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function Chat() {
  const { reportId } = useParams()
  const api = useApiClient()
  const { getToken } = useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [stepText, setStepText] = useState('')
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())
  const [expandedChunks, setExpandedChunks] = useState<Set<string>>(new Set())
  const [highlightedSource, setHighlightedSource] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { t } = useTranslation()
  const { isMobile } = useBreakpoint()
  const [asideOpen, setAsideOpen] = useState(false)

  const SUGGESTIONS = [
    t('chat.suggestion1'),
    t('chat.suggestion2'),
    t('chat.suggestion3'),
    t('chat.suggestion4'),
  ]

  const { data: reportData } = useQuery({
    queryKey: ['report', reportId],
    queryFn: async () => {
      const res = await api.get(`/api/report/${reportId}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
    enabled: !!reportId,
  })

  const rawReport = reportData?.report || reportData
  const report = rawReport ? {
    symbol: rawReport.ticker || rawReport.symbol || '?',
    type: rawReport.trade_type || rawReport.type || '',
    created_at: rawReport.created_at ? new Date(rawReport.created_at).toLocaleDateString() : '',
    word_count: rawReport.report_text ? Math.round(rawReport.report_text.split(/\s+/).length) : 0,
  } : { symbol: '', type: '', created_at: '', word_count: 0 }

  // Set initial greeting once report loads
  useEffect(() => {
    if (rawReport && messages.length === 0) {
      setMessages([{
        id: 'init',
        role: 'assistant',
        content: `I've loaded the research report for **${report.symbol}** (${report.type}). Feel free to ask me any questions about this analysis!`,
        time: t('chat.justNow'),
      }])
    }
  }, [rawReport])

  // Fetch sections for topic chips
  const { data: sectionsData } = useQuery({
    queryKey: ['report-sections', reportId],
    queryFn: async () => {
      const res = await api.get(`/api/report/${reportId}/sections`)
      if (!res.ok) return null
      return res.json()
    },
    enabled: !!reportId,
  })
  const topicChips: string[] = sectionsData?.sections?.length > 0
    ? sectionsData.sections
    : ['Business overview', 'Financial metrics', 'Valuation', 'Risks', 'Growth catalysts']

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, stepText])

  const handleCitationClick = useCallback((messageId: string, sourceIndex: number, _sources: Source[]) => {
    // Expand sources panel for this message
    setExpandedSources(prev => {
      const next = new Set(prev)
      next.add(messageId)
      return next
    })

    // Highlight the source card briefly
    const key = `${messageId}-${sourceIndex}`
    setHighlightedSource(key)
    setTimeout(() => setHighlightedSource(null), 1500)

    // Scroll to the source card
    setTimeout(() => {
      const el = document.getElementById(`source-${key}`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }, 50)
  }, [])

  const renderContentWithCitations = (text: string, sources: Source[] | undefined, messageId: string) => {
    if (!sources || sources.length === 0) {
      return renderContent(text)
    }

    // Build a set of valid source indices for validation
    const validIndices = new Set(sources.map(s => s.index))

    // Split on citation patterns: [1], [2], [IR], [YF]
    const parts = text.split(/(\[\d+\]|\[IR\]|\[YF\])/g)

    return (
      <span>
        {parts.map((part, i) => {
          // Check for numbered citation [1], [2], [100], [200], etc.
          const numMatch = part.match(/^\[(\d+)\]$/)
          if (numMatch) {
            const idx = parseInt(numMatch[1], 10)
            if (validIndices.has(idx)) {
              // Show friendly label for IR (100+) and YF (200+) sources
              const source = sources.find(s => s.index === idx)
              const type = source?.chunk_type
              const label = type === 'ir' ? 'IR' : type === 'sec' ? 'SEC' : type === 'yfinance' ? 'YF' : String(idx)
              return (
                <CitationBadge
                  key={i}
                  label={label}
                  type={type}
                  onClick={() => handleCitationClick(messageId, idx, sources)}
                />
              )
            }
          }

          // Check for [IR] tag
          if (part === '[IR]') {
            const irSource = sources.find(s => s.chunk_type === 'ir')
            if (irSource) {
              return (
                <CitationBadge
                  key={i}
                  label="IR"
                  type="ir"
                  onClick={() => handleCitationClick(messageId, irSource.index, sources)}
                />
              )
            }
          }

          // Check for [YF] tag
          if (part === '[YF]') {
            const yfSource = sources.find(s => s.chunk_type === 'yfinance')
            if (yfSource) {
              return (
                <CitationBadge
                  key={i}
                  label="YF"
                  type="yfinance"
                  onClick={() => handleCitationClick(messageId, yfSource.index, sources)}
                />
              )
            }
          }

          // Regular text — apply basic markdown formatting
          if (!part) return null
          const html = part
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#fafaf9">$1</strong>')
            .replace(/\n/g, '<br/>')
          return <span key={i} dangerouslySetInnerHTML={{ __html: html }} />
        })}
      </span>
    )
  }

  const sendMessage = async (text: string) => {
    if (!text.trim() || isStreaming) return

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsStreaming(true)
    setStepText(t('chat.thinking'))

    try {
      const token = await getToken()

      // POST /continue — sets report_chat_mode in Flask session and starts background agent
      const res = await fetch('/continue', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ report_id: reportId, message: text }),
        credentials: 'include',
      })

      if (!res.ok) throw new Error('Failed to send message')
      const initData = await res.json()
      const streamSessionId = initData.session_id

      // EventSource uses session cookie (set by /continue above) for auth
      const eventSource = new EventSource(`/stream/${streamSessionId}`)

      eventSource.onmessage = async (e) => {
        try {
          const data = JSON.parse(e.data)

          if (data.type === 'step') {
            // Progress update while agent is running
            setStepText(data.message || t('chat.thinking'))

          } else if (data.type === 'done') {
            eventSource.close()
            setStepText('')
            setIsStreaming(false)
            setMessages(prev => [...prev, {
              id: (Date.now() + 1).toString(),
              role: 'assistant',
              content: data.assistant_message || '',
              sources: data.sources || [],
              time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            }])

            // Persist conversation history back to Flask session for next turn
            try {
              await fetch('/commit_session', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({
                  conversation_history: data.conversation_history,
                  current_report_id: data.current_report_id,
                  report_text: data.report_text,
                }),
                credentials: 'include',
              })
            } catch {}

          } else if (data.type === 'error') {
            eventSource.close()
            setStepText('')
            setIsStreaming(false)
            setMessages(prev => [...prev, {
              id: Date.now().toString(),
              role: 'assistant',
              content: data.message || t('chat.errorOccurred'),
              time: t('chat.justNow'),
            }])
          }
        } catch {}
      }

      eventSource.onerror = () => {
        eventSource.close()
        setStepText('')
        setIsStreaming(false)
        setMessages(prev => [...prev, {
          id: Date.now().toString(),
          role: 'assistant',
          content: t('chat.connectionLost'),
          time: t('chat.justNow'),
        }])
      }
    } catch {
      setStepText('')
      setIsStreaming(false)
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: t('chat.networkError'),
        time: t('chat.justNow'),
      }])
    }
  }

  // Render markdown bold + line breaks (used for messages without sources)
  const renderContent = (text: string) => {
    const html = text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#fafaf9">$1</strong>')
      .replace(/\n/g, '<br/>')
    return <span dangerouslySetInnerHTML={{ __html: html }} />
  }

  return (
    <div style={{ background: '#0c0a09', color: '#fafaf9' }}>
      <style>{`@keyframes typing { 0%,100%{opacity:0.3} 50%{opacity:1} }`}</style>
      <AppNav />
      <div style={{ display: 'flex', height: 'calc(100vh - 60px)', overflow: 'hidden' }}>

        {/* CONTEXT PANEL */}
        {isMobile && asideOpen && (
          <div onClick={() => setAsideOpen(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 150 }} />
        )}
        <aside style={{
          width: 280,
          flexShrink: 0,
          borderInlineEnd: '1px solid #292524',
          display: 'flex',
          flexDirection: 'column',
          background: '#0c0a09',
          overflow: 'hidden',
          ...(isMobile ? {
            position: 'fixed',
            top: 60,
            bottom: 0,
            insetInlineStart: asideOpen ? 0 : -300,
            zIndex: 160,
            transition: 'inset-inline-start 0.25s',
          } : {}),
        }}>
          <div style={{ padding: '20px 20px 16px', borderBottom: '1px solid #292524' }}>
            <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 12 }}>{t('chat.reportContext')}</div>
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 10, padding: 14 }}>
              <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 16, fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                {report.symbol || '...'}
                {report.type && (
                  <span style={{ fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 999, background: 'rgba(34,197,94,0.08)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.2)' }}>
                    {report.type}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 12, color: '#a8a29e', lineHeight: 1.5 }}>
                {report.created_at && `${report.created_at} · `}{report.word_count > 0 ? `${report.word_count} words` : ''}
              </div>
              <Link
                to={`/report/${reportId}`}
                style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, border: '1px solid #292524', color: '#a8a29e', fontSize: 12, fontWeight: 500, padding: '7px 12px', borderRadius: 7, textDecoration: 'none', background: 'transparent' }}
              >
                <Icon name="open_in_new" size={14} />
                {t('chat.viewFullReport')}
              </Link>
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 10 }}>{t('chat.askAbout')}</div>
            {topicChips.map((label) => (
              <div
                key={label}
                onClick={() => sendMessage(`Tell me about ${label.toLowerCase()} from this report`)}
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderRadius: 8, fontSize: 12.5, color: '#a8a29e', cursor: isStreaming ? 'not-allowed' : 'pointer', marginBottom: 2, opacity: isStreaming ? 0.5 : 1 }}
              >
                <Icon name="article" size={15} />
                {label}
              </div>
            ))}
          </div>
        </aside>

        {/* CHAT PANEL */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: isMobile ? '12px 16px' : '16px 28px', borderBottom: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {isMobile && (
                <button onClick={() => setAsideOpen(o => !o)} style={{ background: 'none', border: '1px solid #292524', borderRadius: 8, padding: 6, color: '#a8a29e', cursor: 'pointer', display: 'flex' }}>
                  <Icon name="menu_book" size={18} />
                </button>
              )}
              <AIAvatar />
              <div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{t('chat.stockproAi')}</div>
                <div style={{ fontSize: 12, color: '#a8a29e' }}>{t('chat.groundedInReport')}</div>
              </div>
            </div>
            <button
              onClick={() => {
                setMessages(rawReport ? [{ id: 'init-' + Date.now(), role: 'assistant', content: `I've loaded the research report for **${report.symbol}** (${report.type}). Feel free to ask me any questions!`, time: t('chat.justNow') }] : [])
                setExpandedSources(new Set())
                setExpandedChunks(new Set())
                setHighlightedSource(null)
              }}
              style={{ width: 30, height: 30, borderRadius: 7, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              title={t('chat.clearChat')}
            >
              <Icon name="delete" size={15} />
            </button>
          </div>

          {/* MESSAGES */}
          <div style={{ flex: 1, overflowY: 'auto', padding: isMobile ? '16px 16px 12px' : '28px 28px 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
            {messages.map((msg) => (
              <div key={msg.id} style={{ display: 'flex', flexDirection: 'column', gap: 0, maxWidth: 680, alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div style={{ display: 'flex', gap: 12, flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
                  {msg.role === 'assistant' ? <AIAvatar /> : <UserInitials />}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ fontSize: 11.5, fontWeight: 600, color: '#a8a29e', textAlign: msg.role === 'user' ? 'end' : 'start' }}>
                      {msg.role === 'assistant' ? t('chat.stockproAi') : t('chat.you')}
                    </div>
                    <div style={{ padding: '14px 18px', borderRadius: msg.role === 'assistant' ? '4px 14px 14px 14px' : '14px 4px 14px 14px', fontSize: 14, lineHeight: 1.7, background: msg.role === 'assistant' ? '#1c1917' : '#d6d3d1', border: msg.role === 'assistant' ? '1px solid #292524' : 'none', color: msg.role === 'assistant' ? 'rgba(250,250,249,0.85)' : '#0c0a09', fontWeight: msg.role === 'user' ? 500 : 400 }}>
                      {msg.role === 'assistant' && msg.sources && msg.sources.length > 0
                        ? renderContentWithCitations(msg.content, msg.sources, msg.id)
                        : renderContent(msg.content)
                      }
                    </div>
                    <div style={{ fontSize: 11, color: '#a8a29e', marginTop: 2, textAlign: msg.role === 'user' ? 'end' : 'start' }}>{msg.time}</div>
                  </div>
                </div>
                {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                  <div style={{ marginInlineStart: 44 }}>
                    <SourcesPanel
                      sources={msg.sources}
                      messageId={msg.id}
                      isOpen={expandedSources.has(msg.id)}
                      onToggle={() => setExpandedSources(prev => {
                        const next = new Set(prev)
                        if (next.has(msg.id)) next.delete(msg.id)
                        else next.add(msg.id)
                        return next
                      })}
                      expandedChunks={expandedChunks}
                      onToggleChunk={(key) => setExpandedChunks(prev => {
                        const next = new Set(prev)
                        if (next.has(key)) next.delete(key)
                        else next.add(key)
                        return next
                      })}
                      highlightedSource={highlightedSource}
                    />
                  </div>
                )}
              </div>
            ))}

            {/* Streaming indicator */}
            {isStreaming && (
              <div style={{ display: 'flex', gap: 12, maxWidth: 680, alignSelf: 'flex-start' }}>
                <AIAvatar />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ fontSize: 11.5, fontWeight: 600, color: '#a8a29e' }}>{t('chat.stockproAi')}</div>
                  <div style={{ padding: '14px 18px', borderRadius: '4px 14px 14px 14px', background: '#1c1917', border: '1px solid #292524' }}>
                    {stepText && (
                      <div style={{ fontSize: 12, color: '#a8a29e', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                        <Icon name="autorenew" size={14} />
                        {stepText}
                      </div>
                    )}
                    <TypingDots />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* SUGGESTIONS */}
          <div style={{ padding: isMobile ? '0 16px 10px' : '0 28px 12px', flexShrink: 0 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  disabled={isStreaming}
                  style={{ padding: '6px 14px', borderRadius: 999, fontSize: 12.5, fontWeight: 500, border: '1px solid #292524', background: '#1c1917', color: '#a8a29e', cursor: isStreaming ? 'not-allowed' : 'pointer', opacity: isStreaming ? 0.5 : 1 }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* INPUT */}
          <div style={{ padding: isMobile ? '0 16px 16px' : '0 28px 24px', flexShrink: 0 }}>
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, display: 'flex', alignItems: 'flex-end', gap: 10, padding: '12px 14px' }}>
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) } }}
                placeholder={t('chat.askAnything')}
                rows={1}
                disabled={isStreaming}
                style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', resize: 'none', fontFamily: 'Inter, sans-serif', fontSize: 14, color: '#fafaf9', minHeight: 24, maxHeight: 120, lineHeight: 1.6 }}
              />
              <button
                onClick={() => sendMessage(input)}
                disabled={!input.trim() || isStreaming}
                style={{ width: 34, height: 34, borderRadius: 9, border: 'none', background: input.trim() && !isStreaming ? '#d6d3d1' : '#292524', color: input.trim() && !isStreaming ? '#0c0a09' : '#a8a29e', cursor: input.trim() && !isStreaming ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
              >
                <Icon name="send" size={18} filled />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
