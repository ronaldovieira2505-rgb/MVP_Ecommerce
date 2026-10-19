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
  options: { method?: string; body?: unknown; form?: FormData } = {},
): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {}
  // Com FormData o navegador define o Content-Type (multipart) sozinho.
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers['X-CSRFToken'] = csrfFromCookie()

  const response = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
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

export interface ProfileStep {
  key: string
  label: string
  done: boolean
  status?: string
}

export interface WorkerProfile {
  id: number
  full_name: string
  cpf: string
  phone: string
  verification_status: string
  pix_key_type?: string
  pix_key?: string
  verification_message?: string
  profile_steps: ProfileStep[]
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

export interface Vacancy {
  id: number
  title: string
  category: string
  category_label: string
  description: string
  street: string
  city: string
  state: string
  latitude: string
  longitude: string
  starts_at: string
  ends_at: string
  pay_per_person_cents: number
  positions: number
  filled_positions: number
  total_cents: number
  retained_cents: number
  status: string
  status_label: string
  payment_method?: string
}

export interface VacancyList {
  total_retained_cents: number
  results: Vacancy[]
}

/** Card da busca de vagas do prestador (US12/US17). */
export interface VacancyCard {
  id: number
  title: string
  company_name: string
  category: string
  category_label: string
  starts_at: string
  ends_at: string
  district: string
  city: string
  state: string
  gross_cents: number
  fee_percent: number
  fee_cents: number
  net_cents: number
  remaining_positions: number
  payment_guaranteed: boolean
  urgent: boolean
  distance_km: number | null
}

export interface VacancyPublicDetail extends VacancyCard {
  description: string
  street: string
  number: string
  complement: string
  zip_code: string
  latitude: string
  longitude: string
  can_apply: boolean
  apply_blocker: string | null
  my_application: { id: number; status: string; status_label: string } | null
}

/** Item de "Meus trabalhos": uma candidatura ou uma alocação (US37/US38). */
export interface JobItem {
  kind: 'application' | 'assignment'
  id: number
  vacancy_id: number
  title: string
  company_name: string
  starts_at: string
  ends_at: string
  gross_cents: number
  net_cents: number
  status: string
  status_label: string
  can_withdraw: boolean
}

export type JobGroupKey = 'waiting' | 'upcoming' | 'in_progress' | 'completed' | 'closed'

export interface MyJobs {
  groups: Record<JobGroupKey, JobItem[]>
}

export function brl(cents: number): string {
  return (cents / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })
}

const TZ = 'America/Sao_Paulo'

/** Turno em uma linha: "3 de nov., 09:00 às 13:00" (ou com as duas datas). */
export function formatShift(startIso: string, endIso: string): string {
  const day = (iso: string) =>
    new Date(iso).toLocaleDateString('pt-BR', { timeZone: TZ, day: 'numeric', month: 'short' })
  const time = (iso: string) =>
    new Date(iso).toLocaleTimeString('pt-BR', { timeZone: TZ, hour: '2-digit', minute: '2-digit' })
  return day(startIso) === day(endIso)
    ? `${day(startIso)}, ${time(startIso)} às ${time(endIso)}`
    : `${day(startIso)} ${time(startIso)} até ${day(endIso)} ${time(endIso)}`
}
