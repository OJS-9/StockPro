import { useAuth } from '@clerk/clerk-react'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

async function fetchWithAuth(url: string, options: RequestInit = {}, getToken: () => Promise<string | null>) {
  const token = await getToken()
  return fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
}

export function useApiClient() {
  const { getToken } = useAuth()

  return {
    get: (url: string) => fetchWithAuth(url, { method: 'GET' }, getToken),
    post: (url: string, body: unknown) =>
      fetchWithAuth(url, { method: 'POST', body: JSON.stringify(body) }, getToken),
    put: (url: string, body: unknown) =>
      fetchWithAuth(url, { method: 'PUT', body: JSON.stringify(body) }, getToken),
    patch: (url: string, body: unknown) =>
      fetchWithAuth(url, { method: 'PATCH', body: JSON.stringify(body) }, getToken),
    delete: (url: string) => fetchWithAuth(url, { method: 'DELETE' }, getToken),
  }
}
