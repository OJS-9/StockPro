import { useUser } from '@clerk/clerk-react'

export function useAdmin() {
  const { user, isLoaded } = useUser()
  const isAdmin = isLoaded && user?.publicMetadata?.role === 'admin'
  return { isAdmin, isLoading: !isLoaded }
}
