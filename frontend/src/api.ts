export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function csrfFromCookie(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {}
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers['X-CSRFToken'] = csrfFromCookie()

  const response = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  })
  if (!response.ok) {
    let detail = 'Não foi possível concluir a operação.'
    try {
      const data = (await response.json()) as { detail?: string }
      if (data.detail) detail = data.detail
    } catch {
      // resposta sem JSON: mantém a mensagem padrão
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export type Role = 'COMPANY' | 'WORKER' | 'ADMIN'

export interface User {
  id: number
  name: string
  email: string
  role: Role
  verification_status: string | null
}

export interface CnpjData {
  legal_name: string
  trade_name: string
  registration_status: string
  street: string
  number: string
  complement: string
  district: string
  city: string
  state: string
  zip_code: string
}

export interface CnpjLookupResult {
  found: boolean
  available: boolean
  detail?: string
  data?: CnpjData
}

export interface AppNotification {
  id: number
  kind: string
  title: string
  message: string
  link: string
  read: boolean
  created_at: string
}

export interface NotificationList {
  unread_count: number
  results: AppNotification[]
}
