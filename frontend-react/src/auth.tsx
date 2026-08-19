import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setToken } from './api'
import type { AuthResponse, Role, User } from './types'

interface AuthValue { user: User | null; loading: boolean; login: (username: string, password: string) => Promise<void>; logout: () => void }
const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => { const raw = sessionStorage.getItem('mawos_user'); return raw ? JSON.parse(raw) : null })
  const [loading, setLoading] = useState(Boolean(sessionStorage.getItem('mawos_token')))
  useEffect(() => { if (!sessionStorage.getItem('mawos_token')) return setLoading(false); api.get<User>('/me').then(({ data }) => { setUser(data); sessionStorage.setItem('mawos_user', JSON.stringify(data)) }).catch(() => { setToken(null); setUser(null) }).finally(() => setLoading(false)) }, [])
  const value = useMemo<AuthValue>(() => ({
    user, loading,
    async login(username, password) { const { data } = await api.post<AuthResponse>('/auth/login', { username, password }); setToken(data.token); const next = { ...data.user, ai_mode: data.ai_mode }; setUser(next); sessionStorage.setItem('mawos_user', JSON.stringify(next)) },
    logout() { setToken(null); setUser(null); sessionStorage.removeItem('mawos_user') },
  }), [user, loading])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export const useAuth = () => { const context = useContext(AuthContext); if (!context) throw new Error('useAuth must be inside AuthProvider'); return context }
export const roleLabel = (role?: Role | string | null) => role ? role.charAt(0).toUpperCase() + role.slice(1) : 'User'
