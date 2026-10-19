import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, brl, formatDateTime, type VacancyCard } from '../api'
import { CATEGORIES } from '../categories'
import { Alert, Badge, Button, Card, Field, SelectField } from '../components/ui'

interface Filters {
  q: string
  category: string
  date_from: string
  date_to: string
  min_pay: string
}

const EMPTY: Filters = { q: '', category: '', date_from: '', date_to: '', min_pay: '' }

type Origin = { lat: number; lng: number } | null

function buildQuery(filters: Filters, origin: Origin): string {
  const params = new URLSearchParams()
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.category) params.set('category', filters.category)
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  if (filters.min_pay) params.set('min_pay', String(Math.round(Number(filters.min_pay) * 100)))
  if (origin) {
    params.set('lat', origin.lat.toFixed(6))
    params.set('lng', origin.lng.toFixed(6))
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

function place(v: VacancyCard): string {
  return [v.district, v.city && v.state ? `${v.city}/${v.state}` : v.city].filter(Boolean).join(' · ')
}

/** Buscar vagas: texto, filtros (US13), proximidade (US14) e valor líquido (US17). */
export default function VacancySearchPage() {
  const [draft, setDraft] = useState<Filters>(EMPTY)
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [origin, setOrigin] = useState<Origin>(null)
  const [results, setResults] = useState<VacancyCard[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!('geolocation' in navigator)) return
    navigator.geolocation.getCurrentPosition(
      (pos) => setOrigin({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => undefined, // sem permissão: ordena por data de início
    )
  }, [])

  useEffect(() => {
    let active = true
    api<{ results: VacancyCard[] }>(`/api/vacancies/${buildQuery(filters, origin)}`)
      .then((data) => {
        if (!active) return
        setResults(data.results)
        setError('')
      })
      .catch((err: Error) => active && setError(err.message))
    return () => {
      active = false
    }
  }, [filters, origin])

  function submit(event: FormEvent) {
    event.preventDefault()
    setFilters(draft)
  }

  function clear() {
    setDraft(EMPTY)
    setFilters(EMPTY)
  }

  const set = (name: keyof Filters) => (e: { target: { value: string } }) =>
    setDraft({ ...draft, [name]: e.target.value })

  return (
    <Card>
      <h1>Buscar vagas</h1>
      <form onSubmit={submit} role="search">
        <Field label="Buscar" type="search" value={draft.q} onChange={set('q')} placeholder="Ex.: limpeza, carga" />
        <SelectField label="Categoria" value={draft.category} onChange={set('category')}>
          <option value="">Todas</option>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </SelectField>
        <Field label="De" type="date" value={draft.date_from} onChange={set('date_from')} />
        <Field label="Até" type="date" value={draft.date_to} onChange={set('date_to')} />
        <Field
          label="Receber no mínimo (R$)"
          type="number"
          min="0"
          step="1"
          value={draft.min_pay}
          onChange={set('min_pay')}
        />
        <Button type="submit">Buscar</Button>{' '}
        <Button type="button" variant="ghost" onClick={clear}>
          Limpar filtros
        </Button>
      </form>
      <p>{origin ? 'Ordenadas da mais próxima para a mais distante.' : 'Ordenadas pela data de início.'}</p>
      {error && <Alert tone="error">{error}</Alert>}
      {!results && !error && <p role="status">Carregando...</p>}
      {results && results.length === 0 && <p>Nenhuma vaga encontrada com esses filtros.</p>}
      <ul className="vacancy-list">
        {results?.map((v) => (
          <li key={v.id}>
            <Link to={`/vagas/${v.id}`}>
              <strong>{v.title}</strong>
            </Link>{' '}
            {v.urgent && <Badge tone="warning">Urgente</Badge>}{' '}
            {v.payment_guaranteed && <Badge tone="success">Pagamento garantido</Badge>}
            <div>
              {v.company_name} · {v.category_label}
            </div>
            <div>
              {formatDateTime(v.starts_at)} – {formatDateTime(v.ends_at)}
            </div>
            <div>
              {place(v)}
              {v.distance_km !== null && ` · ${v.distance_km.toLocaleString('pt-BR')} km`}
            </div>
            <div>
              <strong>Você recebe {brl(v.net_cents)}</strong>
            </div>
            <small>
              Valor do turno {brl(v.gross_cents)} · taxa {v.fee_percent}% · {v.remaining_positions}{' '}
              {v.remaining_positions === 1 ? 'vaga restante' : 'vagas restantes'}
            </small>
          </li>
        ))}
      </ul>
    </Card>
  )
}
