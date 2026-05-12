import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { useApiClient } from '../api/client'
import Icon from './Icon'

interface RedditPost {
  title?: string
  url?: string
  score?: number
  subreddit?: string
  created_at?: string
  snippet?: string
}

interface XPost {
  author?: string
  text?: string
  url?: string
  created_at?: string
  likes?: number
}

interface PublicViewData {
  symbol: string
  status: 'ready' | 'computing' | 'error'
  summary_md: string | null
  bullish_pct: number | null
  top_themes: string[]
  reddit_posts: RedditPost[]
  x_posts: XPost[]
  last_updated: string | null
  error_message: string | null
}

function renderMarkdown(md: string): string {
  let html = md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#fafaf9;font-weight:600">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^[-*]\s+(.+)$/gm, '<li style="margin-bottom:6px">$1</li>')
    .replace(/(<li.*?<\/li>\n?)+/g, '<ul style="padding-inline-start:20px;margin:8px 0">$&</ul>')
    .replace(/\n\n/g, '<br/>')
  return html
}

function relativeTime(iso: string | null): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Math.max(0, Date.now() - t)
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function PublicViewCard({ symbol }: { symbol: string }) {
  const api = useApiClient()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery<PublicViewData>({
    queryKey: ['public-view', symbol],
    queryFn: async () => {
      const res = await api.get(`/api/ticker/${symbol}/public-view`)
      if (!res.ok) throw new Error('Failed to load public view')
      return res.json()
    },
    refetchInterval: (q) => {
      const d = q.state.data as PublicViewData | undefined
      return d?.status === 'computing' ? 5000 : false
    },
  })

  const refreshMut = useMutation({
    mutationFn: async () => {
      const res = await api.post(`/api/ticker/${symbol}/public-view/refresh`, {})
      if (res.status === 429) throw new Error('Please wait a moment before refreshing again.')
      if (!res.ok) throw new Error('Refresh failed')
      return res.json()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['public-view', symbol] })
    },
  })

  const status = data?.status ?? 'computing'
  const summaryMd = data?.summary_md
  const bullish = data?.bullish_pct ?? null
  const themes = data?.top_themes ?? []
  const reddit = data?.reddit_posts ?? []
  const xPosts = data?.x_posts ?? []

  const cardStyle: React.CSSProperties = {
    background: '#1c1917',
    border: '1px solid #292524',
    borderRadius: 16,
    overflow: 'hidden',
  }

  const headerStyle: React.CSSProperties = {
    padding: '14px 20px',
    borderBottom: '1px solid #292524',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  }

  return (
    <div style={cardStyle}>
      <div style={headerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600 }}>
          <Icon name="forum" size={16} style={{ color: '#a8a29e' }} />
          Public View
          {data?.last_updated && (
            <span style={{ fontSize: 11, fontWeight: 400, color: '#78716c', marginInlineStart: 8 }}>
              · updated {relativeTime(data.last_updated)}
            </span>
          )}
        </div>
        <button
          onClick={() => refreshMut.mutate()}
          disabled={refreshMut.isPending || status === 'computing'}
          title="Refresh public view"
          style={{
            background: 'transparent',
            border: '1px solid #292524',
            color: '#a8a29e',
            borderRadius: 8,
            padding: '6px 10px',
            fontSize: 12,
            cursor: refreshMut.isPending || status === 'computing' ? 'wait' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Icon name="refresh" size={14} />
          Refresh
        </button>
      </div>

      <div style={{ padding: '18px 20px' }}>
        {(isLoading || status === 'computing') && (
          <div style={{ color: '#a8a29e', fontSize: 13 }}>
            Gathering community sentiment from Reddit and X…
          </div>
        )}

        {status === 'error' && (
          <div style={{ color: '#ef4444', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <span>Couldn't load public view{data?.error_message ? `: ${data.error_message}` : ''}.</span>
            <button
              onClick={() => refreshMut.mutate()}
              style={{ background: '#292524', color: '#fafaf9', border: 'none', borderRadius: 6, padding: '6px 12px', fontSize: 12, cursor: 'pointer' }}
            >
              Retry
            </button>
          </div>
        )}

        {status === 'ready' && (
          <>
            {summaryMd && (
              <div
                style={{ fontSize: 14, color: 'rgba(250,250,249,0.86)', lineHeight: 1.7, marginBottom: 14 }}
                dangerouslySetInnerHTML={{ __html: renderMarkdown(summaryMd) }}
              />
            )}

            {bullish !== null && (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 11, color: '#a8a29e', marginBottom: 6, display: 'flex', justifyContent: 'space-between' }}>
                  <span>Bullish {bullish}%</span>
                  <span>Bearish {100 - bullish}%</span>
                </div>
                <div style={{ display: 'flex', height: 6, borderRadius: 999, overflow: 'hidden', background: '#292524' }}>
                  <div style={{ width: `${bullish}%`, background: '#22c55e' }} />
                  <div style={{ width: `${100 - bullish}%`, background: '#ef4444' }} />
                </div>
              </div>
            )}

            {themes.length > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 18 }}>
                {themes.map((t, i) => (
                  <span
                    key={i}
                    style={{
                      fontSize: 11,
                      fontWeight: 500,
                      padding: '4px 10px',
                      borderRadius: 999,
                      border: '1px solid #292524',
                      color: '#d6d3d1',
                      background: '#0c0a09',
                    }}
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
              {/* Reddit column */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#a8a29e', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Icon name="reddit" size={14} /> Reddit ({reddit.length})
                </div>
                {reddit.length === 0 ? (
                  <div style={{ fontSize: 12, color: '#78716c' }}>No recent posts.</div>
                ) : (
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {reddit.slice(0, 10).map((p, i) => (
                      <li key={i}>
                        <a
                          href={p.url || '#'}
                          target="_blank"
                          rel="noreferrer"
                          style={{ textDecoration: 'none', color: 'inherit', display: 'block', padding: '8px 10px', borderRadius: 8, background: '#0c0a09', border: '1px solid #292524' }}
                        >
                          <div style={{ fontSize: 12, color: '#a8a29e', marginBottom: 2 }}>
                            {p.subreddit ? `r/${p.subreddit}` : ''} {p.score != null ? ` · ${p.score} ↑` : ''}
                          </div>
                          <div style={{ fontSize: 13, fontWeight: 500, color: '#fafaf9' }}>
                            {p.title || p.snippet || '(no title)'}
                          </div>
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* X column */}
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#a8a29e', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Icon name="bolt" size={14} /> X ({xPosts.length})
                </div>
                {xPosts.length === 0 ? (
                  <div style={{ fontSize: 12, color: '#78716c' }}>No recent tweets.</div>
                ) : (
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {xPosts.slice(0, 10).map((p, i) => (
                      <li key={i}>
                        <a
                          href={p.url || '#'}
                          target="_blank"
                          rel="noreferrer"
                          style={{ textDecoration: 'none', color: 'inherit', display: 'block', padding: '8px 10px', borderRadius: 8, background: '#0c0a09', border: '1px solid #292524' }}
                        >
                          <div style={{ fontSize: 12, color: '#a8a29e', marginBottom: 2 }}>
                            @{p.author || 'unknown'} {p.likes != null ? ` · ${p.likes} ♥` : ''}
                          </div>
                          <div style={{ fontSize: 13, color: '#fafaf9' }}>{p.text}</div>
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </>
        )}

        {refreshMut.isError && (
          <div style={{ marginTop: 10, fontSize: 12, color: '#ef4444' }}>
            {(refreshMut.error as Error)?.message || 'Refresh failed'}
          </div>
        )}
      </div>
    </div>
  )
}
