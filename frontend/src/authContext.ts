import { createContext, useContext } from 'react'
import type { Role, User } from './api'

export interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth precisa estar dentro de AuthProvider')
  return value
}

export function homePathFor(role: Role): string {
  if (role === 'COMPANY') return '/empresa/vagas'
  if (role === 'WORKER') return '/vagas'
  return '/admin/'
}
