import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, type User } from './api'
import { AuthContext } from './authContext'

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    api<User>('/api/auth/me/')
      .then((me) => active && setUser(me))
      .catch((error: unknown) => {
        // 401/403 = visitante; outros erros também deixam o usuário deslogado
        if (!(error instanceof ApiError)) console.error(error)
      })
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    await api('/api/auth/csrf/')
    const me = await api<User>('/api/auth/login/', { method: 'POST', body: { email, password } })
    setUser(me)
    return me
  }, [])

  const logout = useCallback(async () => {
    await api('/api/auth/logout/', { method: 'POST' })
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
