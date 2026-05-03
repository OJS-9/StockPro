import { Link } from 'react-router'

type Props = {
  resource?: string
  message?: string
  onDismiss?: () => void
}

/** Small banner shown when an API call returns 402 quota_exceeded. */
export default function UpgradeNudge({ resource, message, onDismiss }: Props) {
  const text =
    message ||
    (resource
      ? `You hit your ${resource.replace(/_/g, ' ')} limit. Upgrade for more.`
      : 'You hit your plan limit. Upgrade to keep going.')

  return (
    <div
      role="alert"
      style={{
        background: 'linear-gradient(135deg, rgba(214,211,209,0.08), rgba(214,211,209,0.03))',
        border: '1px solid #292524',
        borderRadius: 12,
        padding: '12px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        color: '#fafaf9',
        fontSize: 13.5,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span className="material-symbols-outlined" style={{ fontSize: 20, color: '#d6d3d1' }}>workspace_premium</span>
        <span>{text}</span>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Link
          to="/pricing"
          style={{
            padding: '6px 14px',
            borderRadius: 100,
            background: '#d6d3d1',
            color: '#0c0a09',
            fontSize: 12.5,
            fontWeight: 600,
            textDecoration: 'none',
            whiteSpace: 'nowrap',
          }}
        >
          See plans
        </Link>
        {onDismiss && (
          <button
            onClick={onDismiss}
            style={{
              padding: '6px 10px',
              borderRadius: 100,
              background: 'transparent',
              color: '#a8a29e',
              border: '1px solid #292524',
              cursor: 'pointer',
              fontSize: 12.5,
            }}
          >
            Dismiss
          </button>
        )}
      </div>
    </div>
  )
}
