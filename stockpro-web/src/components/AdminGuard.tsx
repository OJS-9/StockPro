import { Navigate } from 'react-router'
import { useAdmin } from '../hooks/useAdmin'

export default function AdminGuard({ children }: { children: React.ReactNode }) {
  const { isAdmin, isLoading } = useAdmin()

  if (isLoading) {
    return (
      <div style={{ background: '#0c0a09', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ width: 32, height: 32, border: '3px solid #292524', borderTopColor: '#d6d3d1', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
      </div>
    )
  }

  if (!isAdmin) return <Navigate to="/home" replace />

  return <>{children}</>
}
