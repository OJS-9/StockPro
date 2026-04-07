import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'
import { useAuth } from '@clerk/clerk-react'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  time: string
}

const SUGGESTIONS = [
  "What's the key growth driver?",
  'Explain the valuation multiples',
  'What are the biggest risks?',
  'Compare to main competitors',
]

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

export default function Chat() {
  const { reportId } = useParams()
  const api = useApiClient()
  const { getToken } = useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [stepText, setStepText] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

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
        time: 'Just now',
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
    setStepText('Thinking...')

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
            setStepText(data.message || 'Thinking...')

          } else if (data.type === 'done') {
            eventSource.close()
            setStepText('')
            setIsStreaming(false)
            setMessages(prev => [...prev, {
              id: (Date.now() + 1).toString(),
              role: 'assistant',
              content: data.assistant_message || '',
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
              content: data.message || 'An error occurred. Please try again.',
              time: 'Just now',
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
          content: 'Connection lost. Please try again.',
          time: 'Just now',
        }])
      }
    } catch {
      setStepText('')
      setIsStreaming(false)
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: 'Network error. Please check your connection and try again.',
        time: 'Just now',
      }])
    }
  }

  // Render markdown bold + line breaks
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
        <aside style={{ width: 280, flexShrink: 0, borderRight: '1px solid #292524', display: 'flex', flexDirection: 'column', background: '#0c0a09', overflow: 'hidden' }}>
          <div style={{ padding: '20px 20px 16px', borderBottom: '1px solid #292524' }}>
            <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 12 }}>Report context</div>
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
                View full report
              </Link>
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 10 }}>Ask about</div>
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
          <div style={{ padding: '16px 28px', borderBottom: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <AIAvatar />
              <div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>StockPro AI</div>
                <div style={{ fontSize: 12, color: '#a8a29e' }}>Grounded in report analysis</div>
              </div>
            </div>
            <button
              onClick={() => setMessages(rawReport ? [{ id: 'init-' + Date.now(), role: 'assistant', content: `I've loaded the research report for **${report.symbol}** (${report.type}). Feel free to ask me any questions!`, time: 'Just now' }] : [])}
              style={{ width: 30, height: 30, borderRadius: 7, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              title="Clear chat"
            >
              <Icon name="delete" size={15} />
            </button>
          </div>

          {/* MESSAGES */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '28px 28px 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
            {messages.map((msg) => (
              <div key={msg.id} style={{ display: 'flex', gap: 12, maxWidth: 680, alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
                {msg.role === 'assistant' ? <AIAvatar /> : <UserInitials />}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ fontSize: 11.5, fontWeight: 600, color: '#a8a29e', textAlign: msg.role === 'user' ? 'right' : 'left' }}>
                    {msg.role === 'assistant' ? 'StockPro AI' : 'You'}
                  </div>
                  <div style={{ padding: '14px 18px', borderRadius: msg.role === 'assistant' ? '4px 14px 14px 14px' : '14px 4px 14px 14px', fontSize: 14, lineHeight: 1.7, background: msg.role === 'assistant' ? '#1c1917' : '#d6d3d1', border: msg.role === 'assistant' ? '1px solid #292524' : 'none', color: msg.role === 'assistant' ? 'rgba(250,250,249,0.85)' : '#0c0a09', fontWeight: msg.role === 'user' ? 500 : 400 }}>
                    {renderContent(msg.content)}
                  </div>
                  <div style={{ fontSize: 11, color: '#a8a29e', marginTop: 2, textAlign: msg.role === 'user' ? 'right' : 'left' }}>{msg.time}</div>
                </div>
              </div>
            ))}

            {/* Streaming indicator */}
            {isStreaming && (
              <div style={{ display: 'flex', gap: 12, maxWidth: 680, alignSelf: 'flex-start' }}>
                <AIAvatar />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ fontSize: 11.5, fontWeight: 600, color: '#a8a29e' }}>StockPro AI</div>
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
          <div style={{ padding: '0 28px 12px', flexShrink: 0 }}>
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
          <div style={{ padding: '0 28px 24px', flexShrink: 0 }}>
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, display: 'flex', alignItems: 'flex-end', gap: 10, padding: '12px 14px' }}>
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) } }}
                placeholder="Ask anything about this report..."
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
