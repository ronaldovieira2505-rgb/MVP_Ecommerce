import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, brl, formatShift, type VacancyCard } from '../api'
import { CATEGORIES } from '../categories'
import { Alert, Badge, Button, Card, Field, Loading, SelectField } from '../components/ui'

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
  return [v.district, v.city && v.state ? `${v.city}/${v.state}` : v.city].filter(Boolean).join(', ')
}

/** A lombada avisa o que é urgente; o resto fica no verde de "valor retido". */
function toneFor(v: VacancyCard): string {
  if (v.urgent) return 'row-colete'
  return v.payment_guaranteed ? 'row-carimbo' : ''
}

/** Uma vaga por ficha: o que o prestador recebe vem primeiro. */
function ResultRow({ vacancy }: { vacancy: VacancyCard }) {
  return (
    <li>
      <article className={`row ${toneFor(vacancy)}`}>
        <div>
          <h2 className="row-titulo">
            <Link to={`/vagas/${vacancy.id}`}>{vacancy.title}</Link>
            {vacancy.urgent && <Badge tone="warning">Urgente</Badge>}
            {vacancy.payment_guaranteed && <Badge tone="success">Pagamento garantido</Badge>}
          </h2>
          <p className="row-quando">{formatShift(vacancy.starts_at, vacancy.ends_at)}</p>
          <p className="row-quando">
            {vacancy.company_name} · {vacancy.category_label}
          </p>
          <p className="row-quando">
            {place(vacancy)}
            {vacancy.distance_km !== null && ` · ${vacancy.distance_km.toLocaleString('pt-BR')} km`}
          </p>
        </div>
        <div className="row-lado">
          <p className="recebe">Você recebe {brl(vacancy.net_cents)}</p>
          <small className="letra-miuda">
            Valor do turno {brl(vacancy.gross_cents)} · taxa {vacancy.fee_percent}% ·{' '}
            {vacancy.remaining_positions}{' '}
            {vacancy.remaining_positions === 1 ? 'vaga restante' : 'vagas restantes'}
          </small>
        </div>
      </article>
    </li>
  )
}

/** Buscar vagas: texto, filtros (US13), proximidade (US14) e valor líquido (US17). */
export default function VacancySearchPage() {
  const [draft, setDraft] = useState<Filters>(EMPTY)
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [origin, setOrigin] = useState<Origin>(null)
  const [results, setResults] = useState<VacancyCard[] | null>(null)
  const [error, setError] = useState('')
  // Consulta cujo resultado está na tela; se for diferente da atual, a busca está atualizando.
  const [loadedQuery, setLoadedQuery] = useState<string | null>(null)
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    if (!('geolocation' in navigator)) return
    navigator.geolocation.getCurrentPosition(
      (pos) => setOrigin({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => undefined, // sem permissão: ordena por data de início
    )
  }, [])

  const query = buildQuery(filters, origin)
  const loading = loadedQuery !== query

  useEffect(() => {
    let active = true
    api<{ results: VacancyCard[] }>(`/api/vacancies/${query}`)
      .then((data) => {
        if (!active) return
        setResults(data.results)
        setError('')
      })
      .catch((err: Error) => active && setError(err.message))
      .finally(() => active && setLoadedQuery(query))
    return () => {
      active = false
    }
  }, [query])

  function submit(event: FormEvent) {
    event.preventDefault()
    setFilters(draft)
  }

  function clear() {
    setDraft(EMPTY)
    setFilters(EMPTY)
  }

  // Filtros além do texto: no celular ficam recolhidos e o botão mostra quantos estão ativos.
  const activeExtras = [filters.category, filters.date_from, filters.date_to, filters.min_pay].filter(
    Boolean,
  ).length

  const hasAnyFilter = [draft, filters].some((f) => Object.values(f).some(Boolean))

  const set = (name: keyof Filters) => (e: { target: { value: string } }) =>
    setDraft({ ...draft, [name]: e.target.value })

  return (
    <>
      <Card tone="colete">
        <h1>Buscar vagas</h1>
        <form onSubmit={submit} role="search">
          <div className="filtros">
            <Field
              label="Buscar"
              type="search"
              value={draft.q}
              onChange={set('q')}
              placeholder="Ex.: limpeza, carga"
            />
            <div className={`filtros-extra ${showFilters ? 'aberto' : ''}`} id="filtros-extra">
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
            </div>
          </div>
          <div className="acoes">
            <Button type="submit" busy={loading && results !== null}>
              Buscar
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="so-celular"
              aria-expanded={showFilters}
              aria-controls="filtros-extra"
              onClick={() => setShowFilters((v) => !v)}
            >
              {showFilters ? 'Menos filtros' : `Filtros${activeExtras ? ` (${activeExtras})` : ''}`}
            </Button>
            {hasAnyFilter && (
              <Button type="button" variant="secondary" onClick={clear}>
                Limpar filtros
              </Button>
            )}
          </div>
        </form>
        <p className="sub">
          {origin
            ? 'Ordenadas da mais próxima para a mais distante.'
            : 'Ordenadas pela data de início. Libere a localização para ver as mais próximas.'}
        </p>
      </Card>

      {error && <Alert tone="error">{error}</Alert>}
      {!results && !error && <Loading />}
      {results && results.length === 0 && (
        <Card>
          <div className="vazio">
            <h2>Nenhuma vaga com esses filtros</h2>
            <p>
              Tente ampliar o período, baixar o valor mínimo ou limpar os filtros para ver todos os
              turnos abertos.
            </p>
          </div>
        </Card>
      )}
      {results && results.length > 0 && (
        <ul className="row-list" aria-busy={loading} data-atualizando={loading || undefined}>
          {results.map((v) => (
            <ResultRow key={v.id} vacancy={v} />
          ))}
        </ul>
      )}
    </>
  )
}
