import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { useAuth } from '@clerk/clerk-react'
import i18n from './i18n'

type Lang = 'en' | 'he'
interface LanguageContextValue {
  lang: Lang
  dir: 'ltr' | 'rtl'
  setLang: (lang: Lang) => void
}

const LanguageContext = createContext<LanguageContextValue>({
  lang: 'en',
  dir: 'ltr',
  setLang: () => {},
})

export function useLanguage() {
  return useContext(LanguageContext)
}

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export function LanguageProvider({ children }: { children: ReactNode }) {
  const { getToken, isSignedIn } = useAuth()
  const [lang, setLangState] = useState<Lang>('en')

  // Apply dir/lang to <html> whenever lang changes
  useEffect(() => {
    const dir = lang === 'he' ? 'rtl' : 'ltr'
    document.documentElement.dir = dir
    document.documentElement.lang = lang
  }, [lang])

  // Fetch user preference on mount
  useEffect(() => {
    if (!isSignedIn) return
    let cancelled = false
    ;(async () => {
      try {
        const token = await getToken()
        const res = await fetch(`${API_BASE}/api/settings`, {
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        })
        if (!res.ok) return
        const data = await res.json()
        const saved = data?.preferences?.language
        if (!cancelled && (saved === 'en' || saved === 'he')) {
          setLangState(saved)
          i18n.changeLanguage(saved)
        }
      } catch {
        // ignore -- default to 'en'
      }
    })()
    return () => { cancelled = true }
  }, [isSignedIn, getToken])

  const setLang = useCallback(async (newLang: Lang) => {
    setLangState(newLang)
    i18n.changeLanguage(newLang)
    try {
      const token = await getToken()
      await fetch(`${API_BASE}/api/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ language: newLang }),
      })
    } catch {
      // preference saved locally even if API fails
    }
  }, [getToken])

  const dir = lang === 'he' ? 'rtl' : 'ltr'

  return (
    <LanguageContext.Provider value={{ lang, dir, setLang }}>
      {children}
    </LanguageContext.Provider>
  )
}
