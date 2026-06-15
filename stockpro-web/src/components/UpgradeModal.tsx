import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'

type Props = {
  message?: string
  onDismiss: () => void
}

/**
 * Full-screen, non-dismissible modal shown when a free-tier user hits the
 * monthly report limit (backend returns 403 limit_reached). Clicking the
 * backdrop does nothing — the user must pick Upgrade or Maybe later.
 */
export default function UpgradeModal({ message, onDismiss }: Props) {
  const navigate = useNavigate()
  const { t } = useTranslation()

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.7)',
        backdropFilter: 'blur(4px)',
        zIndex: 300,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <div
        style={{
          background: '#1c1917',
          border: '1px solid #292524',
          borderRadius: 18,
          padding: '36px 32px',
          maxWidth: 440,
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          gap: 16,
        }}
      >
        <div
          style={{
            width: 52,
            height: 52,
            borderRadius: 14,
            background: 'rgba(214,211,209,0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 28, color: '#d6d3d1' }}>
            workspace_premium
          </span>
        </div>

        <div style={{ fontSize: 20, fontWeight: 700, color: '#fafaf9', fontFamily: 'Nunito, "Secular One", Heebo, sans-serif' }}>
          {message || t('research.upgradeModal.title')}
        </div>

        <div style={{ fontSize: 14, color: '#a8a29e', lineHeight: 1.5 }}>
          {t('research.upgradeModal.body')}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, width: '100%', marginTop: 8 }}>
          <button
            onClick={() => navigate('/settings?section=plan')}
            style={{
              padding: '13px 24px',
              borderRadius: 100,
              background: '#d6d3d1',
              color: '#0c0a09',
              fontSize: 14.5,
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
              width: '100%',
            }}
          >
            {t('research.upgradeModal.upgrade')}
          </button>
          <button
            onClick={onDismiss}
            style={{
              padding: '11px 24px',
              borderRadius: 100,
              background: 'transparent',
              color: '#a8a29e',
              border: '1px solid #292524',
              cursor: 'pointer',
              fontSize: 13.5,
              width: '100%',
            }}
          >
            {t('research.upgradeModal.maybeLater')}
          </button>
        </div>
      </div>
    </div>
  )
}
